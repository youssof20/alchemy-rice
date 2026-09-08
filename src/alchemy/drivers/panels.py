from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Protocol

from alchemy.domain.panels import (
    load_panel_layout,
    required_widget_plugins,
    resolve_panel_layout,
)
from alchemy.domain.transactions import Operation, VerificationResult

_MAX_CAPTURE_BYTES = 4 * 1024 * 1024
_DUMP_PREFIX = "var layout = "
_DUMP_SUFFIX = ";\n\nplasma.loadSerializedLayout(layout);"

_METADATA_SCRIPT = """
var result = {
    api_version: 1,
    screens: [],
    known_widget_types: Array.from(knownWidgetTypes),
    known_panel_types: Array.from(knownPanelTypes),
    panels: []
};
for (var screenIndex = 0; screenIndex < screenCount; ++screenIndex) {
    var geometry = screenGeometry(screenIndex);
    result.screens.push({
        x: geometry.x,
        y: geometry.y,
        width: geometry.width,
        height: geometry.height
    });
}
var currentPanels = panels();
for (var panelIndex = 0; panelIndex < currentPanels.length; ++panelIndex) {
    var panel = currentPanels[panelIndex];
    var widgets = panel.widgets();
    var widgetData = [];
    for (var widgetIndex = 0; widgetIndex < widgets.length; ++widgetIndex) {
        widgetData.push({plugin: widgets[widgetIndex].type, index: widgets[widgetIndex].index});
    }
    widgetData.sort(function(left, right) {
        if (left.index < 0 && right.index < 0) return 0;
        if (left.index < 0) return 1;
        if (right.index < 0) return -1;
        return left.index - right.index;
    });
    result.panels.push({
        panel_plugin: panel.type,
        screen: panel.screen,
        floating: panel.floating,
        floating_applets: panel.floatingApplets,
        height: panel.height,
        length: panel.length,
        minimum_length: panel.minimumLength,
        maximum_length: panel.maximumLength,
        offset: panel.offset,
        widgets: widgetData
    });
}
print(JSON.stringify(result));
""".strip()

_APPLY_SCRIPT = """
var layout = __LAYOUT__;
var availableWidgets = Array.from(knownWidgetTypes);
var availableWidgetMap = {};
for (var availableIndex = 0; availableIndex < availableWidgets.length; ++availableIndex) {
    availableWidgetMap[availableWidgets[availableIndex]] = true;
}
function requireWidget(plugin) {
    if (!availableWidgetMap[plugin]) throw new Error("Missing widget dependency: " + plugin);
}
function groupPath(encoded) {
    if (encoded === "/") return [];
    var parts = encoded.substring(1).split("/");
    for (var index = 0; index < parts.length; ++index) {
        parts[index] = decodeURIComponent(parts[index]);
    }
    return parts;
}
function applyConfig(target, config) {
    if (!config) return;
    var groups = Object.keys(config).sort();
    for (var groupIndex = 0; groupIndex < groups.length; ++groupIndex) {
        var group = groups[groupIndex];
        target.currentConfigGroup = groupPath(group);
        var values = config[group];
        var keys = Object.keys(values).sort();
        for (var keyIndex = 0; keyIndex < keys.length; ++keyIndex) {
            target.writeConfig(keys[keyIndex], values[keys[keyIndex]]);
        }
    }
}
function createPanel(data) {
    var panel = data.panel_plugin ? new Panel(data.panel_plugin) : new Panel;
    if (!panel || !panel.id) throw new Error("Plasma could not create a panel");
    panel.screen = data.screen;
    panel.location = data.location;
    panel.height = data.height;
    panel.lengthMode = data.length_mode;
    if (data.length !== null && data.length !== undefined) panel.length = data.length;
    if (data.minimum_length !== undefined) panel.minimumLength = data.minimum_length;
    if (data.maximum_length !== undefined) panel.maximumLength = data.maximum_length;
    if (data.offset !== undefined) panel.offset = data.offset;
    panel.alignment = data.alignment;
    panel.hiding = data.hiding;
    panel.opacity = data.opacity;
    panel.floating = data.floating;
    panel.floatingApplets = data.floating_applets;
    applyConfig(panel, data.config);
    for (var widgetIndex = 0; widgetIndex < data.widgets.length; ++widgetIndex) {
        var widgetData = data.widgets[widgetIndex];
        requireWidget(widgetData.plugin);
        var widget = panel.addWidget(widgetData.plugin);
        if (!widget || !widget.id) throw new Error("Could not create widget: " + widgetData.plugin);
        applyConfig(widget, widgetData.config);
    }
    return panel;
}
var previousPanels = panels();
var createdPanels = [];
for (var plannedIndex = 0; plannedIndex < layout.panels.length; ++plannedIndex) {
    createdPanels.push(createPanel(layout.panels[plannedIndex]));
}
for (var oldIndex = 0; oldIndex < previousPanels.length; ++oldIndex) {
    previousPanels[oldIndex].remove();
}
print(JSON.stringify({ok: true, panels: createdPanels.length}));
""".strip()


class PanelShell(Protocol):
    def evaluate(self, script: str) -> str: ...

    def dump_layout(self) -> str: ...


class PanelDriver:
    name = "panels.layout"

    def __init__(self, shell: PanelShell, *, config_path: Path) -> None:
        self.shell = shell
        self.config_path = config_path

    async def inspect(self) -> dict[str, Any]:
        return self.public_state(await self._capture())

    async def plan(self, desired: str) -> tuple[Operation, ...]:
        layout = load_panel_layout(desired)
        before_state = await self._capture()
        resolved = resolve_panel_layout(layout, before_state["screens"])
        installed = frozenset(str(item) for item in before_state["known_widget_types"])
        missing = sorted(required_widget_plugins(resolved) - installed)
        if missing:
            raise RuntimeError(
                "Panel apply requires missing widget dependencies: " + ", ".join(missing)
            )
        before = _serialize(before_state)
        after = _serialize(resolved)
        if _panel_signature(before_state) == _panel_signature(resolved):
            return ()
        return (
            Operation(
                operation_id=str(uuid.uuid4()),
                driver=self.name,
                target="kde.panels.layout",
                description=(
                    f"Replace the Plasma panel layout with {len(resolved['panels'])} panel(s)"
                ),
                before=before,
                after=after,
                command=("org.kde.PlasmaShell.evaluateScript", "apply-panel-layout"),
                affected_paths=(str(self.config_path),),
            ),
        )

    async def apply(self, operation: Operation) -> None:
        await self._apply_serialized(operation.after)

    async def verify(
        self, operation: Operation, *, expected: str | None = None
    ) -> VerificationResult:
        wanted_serialized = operation.after if expected is None else expected
        try:
            wanted = json.loads(wanted_serialized)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Stored panel transaction state is malformed") from exc
        observed = await self._capture()
        exact = isinstance(wanted, dict) and wanted.get("mode") == "captured"
        matched = _panel_signature(observed, exact=exact) == _panel_signature(
            wanted, exact=exact
        )
        return VerificationResult(
            matched,
            _serialize(self.public_state(observed)),
            "Panel structure matches the planned layout"
            if matched
            else "Observed panel structure differs from the planned layout",
        )

    async def rollback(self, operation: Operation) -> None:
        if operation.before is None:
            raise RuntimeError("Previous panel state is unavailable")
        await self._apply_serialized(operation.before)

    async def refresh_after_snapshot(self) -> None:
        raise RuntimeError("Panel recovery requires a captured semantic panel state")

    @staticmethod
    def public_state(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "screen_count": len(state["screens"]),
            "screens": state["screens"],
            "panels": [
                {
                    "screen": panel["screen"],
                    "location": panel["location"],
                    "alignment": panel["alignment"],
                    "height": panel["height"],
                    "length_mode": panel["length_mode"],
                    "hiding": panel["hiding"],
                    "floating": panel["floating"],
                    "opacity": panel["opacity"],
                    "widgets": [widget["plugin"] for widget in panel["widgets"]],
                }
                for panel in state["panels"]
            ],
        }

    @staticmethod
    def public_plan(operation: Operation) -> dict[str, Any]:
        before = json.loads(operation.before or "{}")
        after = json.loads(operation.after)
        return {
            "operation_id": operation.operation_id,
            "driver": operation.driver,
            "description": operation.description,
            "confirmation_token": PanelDriver.confirmation_token(operation),
            "affected_paths": list(operation.affected_paths),
            "current": PanelDriver.public_state(before),
            "screen_mapping": after["mappings"],
            "planned_panels": after["panels"],
        }

    @staticmethod
    def confirmation_token(operation: Operation) -> str:
        material = f"{operation.before or ''}\0{operation.after}".encode()
        return hashlib.sha256(material).hexdigest()

    async def _capture(self) -> dict[str, Any]:
        dump_text = await asyncio.to_thread(self.shell.dump_layout)
        metadata_text = await asyncio.to_thread(self.shell.evaluate, _METADATA_SCRIPT)
        if len(dump_text.encode("utf-8")) > _MAX_CAPTURE_BYTES:
            raise RuntimeError("Plasma panel state exceeds the 4 MiB capture limit")
        serialized = _extract_layout(dump_text)
        try:
            official = json.loads(serialized)
            metadata = json.loads(metadata_text.strip())
        except json.JSONDecodeError as exc:
            raise RuntimeError("Plasma returned malformed panel state") from exc
        return _merge_capture(official, metadata)

    async def _apply_serialized(self, serialized: str) -> None:
        try:
            state = json.loads(serialized)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Stored panel transaction state is malformed") from exc
        panels = state.get("panels") if isinstance(state, dict) else None
        if not isinstance(panels, list):
            raise RuntimeError("Stored panel transaction has no panel list")
        script = _APPLY_SCRIPT.replace("__LAYOUT__", json.dumps(state, ensure_ascii=True))
        output = await asyncio.to_thread(self.shell.evaluate, script)
        try:
            result = json.loads(output.strip())
        except json.JSONDecodeError as exc:
            raise RuntimeError("Plasma returned malformed panel apply status") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("Plasma did not confirm the panel apply")


def _extract_layout(script: str) -> str:
    start = script.find(_DUMP_PREFIX)
    if start < 0:
        raise RuntimeError("Plasma layout dump has an unsupported format")
    start += len(_DUMP_PREFIX)
    end = script.find(_DUMP_SUFFIX, start)
    if end < 0:
        raise RuntimeError("Plasma layout dump has an unsupported format")
    return script[start:end]


def _merge_capture(official: Any, metadata: Any) -> dict[str, Any]:
    if not isinstance(official, dict) or official.get("serializationFormatVersion") != "1":
        raise RuntimeError("Plasma returned an unsupported layout serialization")
    if not isinstance(metadata, dict) or metadata.get("api_version") != 1:
        raise RuntimeError("Plasma returned invalid panel metadata")
    official_panels = official.get("panels")
    metadata_panels = metadata.get("panels")
    screens = metadata.get("screens")
    known_widgets = metadata.get("known_widget_types")
    if (
        not isinstance(official_panels, list)
        or not isinstance(metadata_panels, list)
        or len(official_panels) != len(metadata_panels)
        or not isinstance(screens, list)
        or not isinstance(known_widgets, list)
    ):
        raise RuntimeError("Plasma returned inconsistent panel metadata")
    validated_screens = _validated_screens(screens)
    panels: list[dict[str, Any]] = []
    for index, (panel, extra) in enumerate(zip(official_panels, metadata_panels, strict=True)):
        if not isinstance(panel, dict) or not isinstance(extra, dict):
            raise RuntimeError(f"Plasma returned an invalid panel entry at index {index}")
        applets = panel.get("applets")
        extra_widgets = extra.get("widgets")
        if not isinstance(applets, list) or not isinstance(extra_widgets, list):
            raise RuntimeError("Plasma returned an invalid widget list")
        plugins = [item.get("plugin") for item in applets if isinstance(item, dict)]
        extra_plugins = [item.get("plugin") for item in extra_widgets if isinstance(item, dict)]
        if plugins != extra_plugins:
            raise RuntimeError("Panel changed while its state was being captured")
        panel_screen = _required_integer(extra, "screen")
        if not 0 <= panel_screen < len(validated_screens):
            raise RuntimeError("Plasma returned a panel with an invalid screen assignment")
        panels.append(
            {
                "panel_plugin": _required_string(extra, "panel_plugin"),
                "screen": panel_screen,
                "location": _choice(panel, "location", {"top", "bottom", "left", "right"}),
                "alignment": _choice(panel, "alignment", {"left", "center", "right"}),
                "floating": _required_boolean(extra, "floating"),
                "floating_applets": _required_boolean(extra, "floating_applets"),
                "height": _required_integer(extra, "height"),
                "length_mode": _choice(panel, "lengthMode", {"fill", "fit", "custom"}),
                "length": _required_integer(extra, "length"),
                "minimum_length": _required_integer(extra, "minimum_length"),
                "maximum_length": _required_integer(extra, "maximum_length"),
                "offset": _required_integer(extra, "offset"),
                "hiding": _normalize_hiding(
                    _choice(
                        panel,
                        "hiding",
                        {"normal", "none", "autohide", "dodgewindows", "windowsgobelow"},
                    )
                ),
                "opacity": _choice(panel, "opacity", {"adaptive", "opaque", "translucent"}),
                "config": _required_config(panel.get("config")),
                "widgets": [
                    {
                        "plugin": _required_string(applet, "plugin"),
                        "config": _required_config(applet.get("config")),
                    }
                    for applet in applets
                    if isinstance(applet, dict)
                ],
            }
        )
    return {
        "mode": "captured",
        "format_version": 1,
        "screens": validated_screens,
        "known_widget_types": [str(item) for item in known_widgets],
        "panels": panels,
    }


def _panel_signature(state: Any, *, exact: bool = False) -> list[dict[str, Any]]:
    if not isinstance(state, dict) or not isinstance(state.get("panels"), list):
        raise RuntimeError("Panel state has no panel list")
    signature: list[dict[str, Any]] = []
    for value in state["panels"]:
        if not isinstance(value, dict):
            raise RuntimeError("Panel state contains an invalid panel")
        item: dict[str, Any] = {
            "screen": value.get("screen"),
            "location": value.get("location"),
            "alignment": value.get("alignment"),
            "floating": value.get("floating"),
            "floating_applets": value.get("floating_applets", False),
            "height": value.get("height"),
            "length_mode": value.get("length_mode"),
            "hiding": _normalize_hiding(value.get("hiding")),
            "opacity": value.get("opacity"),
            "widgets": [
                {
                    "plugin": widget.get("plugin"),
                    **({"config": widget.get("config", {})} if exact else {}),
                }
                for widget in value.get("widgets", [])
                if isinstance(widget, dict)
            ],
        }
        if value.get("length_mode") == "custom":
            item["length"] = value.get("length")
        if exact:
            item.update(
                panel_plugin=value.get("panel_plugin"),
                minimum_length=value.get("minimum_length"),
                maximum_length=value.get("maximum_length"),
                offset=value.get("offset"),
                config=value.get("config", {}),
            )
        signature.append(item)
    return signature


def _serialize(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise RuntimeError(f"Plasma panel field {key} is invalid")
    return item


def _required_integer(value: dict[str, Any], key: str) -> int:
    return _integer(value.get(key), key)


def _integer(value: Any, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"Plasma panel field {key} is invalid")
    return round(value)


def _required_boolean(value: dict[str, Any], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise RuntimeError(f"Plasma panel field {key} is invalid")
    return item


def _choice(value: dict[str, Any], key: str, allowed: set[str]) -> str:
    item = value.get(key)
    if not isinstance(item, str) or item not in allowed:
        raise RuntimeError(f"Plasma panel field {key} is invalid")
    return item


def _required_config(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise RuntimeError("Plasma returned an invalid configuration tree")
    output: dict[str, dict[str, Any]] = {}
    for group, entries in value.items():
        if not isinstance(group, str) or not group.startswith("/") or not isinstance(entries, dict):
            raise RuntimeError("Plasma returned an invalid configuration group")
        output[group] = {str(key): item for key, item in entries.items()}
    return output


def _validated_screens(values: list[Any]) -> list[dict[str, int]]:
    if not values or len(values) > 32:
        raise RuntimeError("Plasma returned an unsupported screen count")
    screens: list[dict[str, int]] = []
    for value in values:
        if not isinstance(value, dict):
            raise RuntimeError("Plasma returned invalid screen geometry")
        screen = {key: _required_integer(value, key) for key in ("x", "y", "width", "height")}
        if screen["width"] <= 0 or screen["height"] <= 0:
            raise RuntimeError("Plasma returned invalid screen dimensions")
        screens.append(screen)
    return screens


def _normalize_hiding(value: Any) -> Any:
    return "none" if value == "normal" else value
