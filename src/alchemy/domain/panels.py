from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_LAYOUT_BYTES = 256 * 1024
MAX_PANELS = 16
MAX_WIDGETS = 128
MAX_SCREENS = 32
PANEL_SPACER = "org.kde.plasma.panelspacer"

_LOGICAL_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_PLUGIN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,191}$")
_LOCATIONS = frozenset({"top", "bottom", "left", "right"})
_ALIGNMENTS = frozenset({"left", "center", "right"})
_SLOTS = frozenset({"left", "center", "right"})
_SCREEN_ROLES = frozenset({"primary", "all"})
_LENGTH_MODES = frozenset({"fill", "fit", "custom"})
_HIDING = frozenset({"none", "autohide", "dodgewindows", "windowsgobelow"})
_OPACITY = frozenset({"adaptive", "opaque", "translucent"})


@dataclass(frozen=True, slots=True)
class Dimension:
    unit: str
    value: float
    min_px: int
    max_px: int

    def resolve(self, available_pixels: int) -> int:
        raw = self.value if self.unit == "pixels" else available_pixels * self.value / 100
        return min(self.max_px, max(self.min_px, round(raw)))


@dataclass(frozen=True, slots=True)
class WidgetSpec:
    plugin: str
    slot: str


@dataclass(frozen=True, slots=True)
class PanelSpec:
    logical_id: str
    location: str
    alignment: str
    floating: bool
    height: Dimension
    screen_role: str
    widgets: tuple[WidgetSpec, ...]
    length_mode: str
    length: Dimension | None
    hiding: str
    opacity: str


@dataclass(frozen=True, slots=True)
class PanelLayout:
    panels: tuple[PanelSpec, ...]


def load_panel_layout(path_value: str) -> PanelLayout:
    path = Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Panel layout must be a regular JSON file")
    if path.stat().st_size > MAX_LAYOUT_BYTES:
        raise ValueError("Panel layout exceeds the 256 KiB input limit")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Panel layout must be valid UTF-8 JSON") from exc
    return parse_panel_layout(payload)


def parse_panel_layout(payload: Any) -> PanelLayout:
    root = _object(payload, "Panel layout")
    _only_keys(root, {"format_version", "panels"}, "Panel layout")
    if root.get("format_version") != 1:
        raise ValueError("Panel layout format_version must be 1")
    panels_value = root.get("panels")
    if not isinstance(panels_value, list) or not panels_value:
        raise ValueError("Panel layout must contain at least one panel")
    if len(panels_value) > MAX_PANELS:
        raise ValueError(f"Panel layout may contain at most {MAX_PANELS} panels")
    panels = tuple(_parse_panel(value, index) for index, value in enumerate(panels_value))
    identifiers = [panel.logical_id for panel in panels]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Panel logical_id values must be unique")
    widget_count = sum(len(panel.widgets) for panel in panels)
    if widget_count > MAX_WIDGETS:
        raise ValueError(f"Panel layout may contain at most {MAX_WIDGETS} widgets")
    return PanelLayout(panels)


def resolve_panel_layout(
    layout: PanelLayout, screens: list[dict[str, int]]
) -> dict[str, Any]:
    if not screens:
        raise RuntimeError("Plasma reported no screens")
    if len(screens) > MAX_SCREENS:
        raise RuntimeError(f"Plasma reported more than {MAX_SCREENS} screens")
    normalized_screens = [_screen(screen, index) for index, screen in enumerate(screens)]
    resolved: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    occupied: set[tuple[int, str]] = set()
    for panel in layout.panels:
        screen_indexes = range(len(normalized_screens)) if panel.screen_role == "all" else (0,)
        for screen_index in screen_indexes:
            screen = normalized_screens[screen_index]
            edge = (screen_index, panel.location)
            if edge in occupied:
                raise ValueError(
                    f"More than one panel maps to screen {screen_index} {panel.location}"
                )
            occupied.add(edge)
            horizontal = panel.location in {"top", "bottom"}
            cross_axis = screen["height"] if horizontal else screen["width"]
            along_axis = screen["width"] if horizontal else screen["height"]
            height = panel.height.resolve(cross_axis)
            length = panel.length.resolve(along_axis) if panel.length is not None else None
            instance_id = (
                panel.logical_id
                if panel.screen_role == "primary"
                else f"{panel.logical_id}@screen-{screen_index}"
            )
            compiled_widgets = _compile_widgets(panel.widgets)
            if len(resolved) >= MAX_PANELS:
                raise ValueError(
                    f"Resolved panel layout may contain at most {MAX_PANELS} panels"
                )
            resolved_widget_count = sum(
                len(item["widgets"]) for item in resolved
            ) + len(compiled_widgets)
            if resolved_widget_count > MAX_WIDGETS:
                raise ValueError(
                    f"Resolved panel layout may contain at most {MAX_WIDGETS} widgets"
                )
            resolved.append(
                {
                    "logical_id": instance_id,
                    "screen": screen_index,
                    "location": panel.location,
                    "alignment": panel.alignment,
                    "floating": panel.floating,
                    "floating_applets": False,
                    "height": height,
                    "length_mode": panel.length_mode,
                    "length": length,
                    "hiding": panel.hiding,
                    "opacity": panel.opacity,
                    "widgets": compiled_widgets,
                }
            )
            mappings.append(
                {
                    "logical_id": panel.logical_id,
                    "instance_id": instance_id,
                    "screen_role": panel.screen_role,
                    "screen": screen_index,
                    "geometry": screen,
                }
            )
    return {
        "mode": "resolved",
        "format_version": 1,
        "screen_count": len(normalized_screens),
        "mappings": mappings,
        "panels": resolved,
    }


def required_widget_plugins(resolved: dict[str, Any]) -> frozenset[str]:
    return frozenset(
        str(widget["plugin"])
        for panel in resolved["panels"]
        for widget in panel["widgets"]
    )


def _parse_panel(value: Any, index: int) -> PanelSpec:
    context = f"Panel {index}"
    panel = _object(value, context)
    allowed = {
        "logical_id",
        "location",
        "alignment",
        "floating",
        "height",
        "screen_role",
        "widgets",
        "length_mode",
        "length",
        "hiding",
        "opacity",
    }
    _only_keys(panel, allowed, context)
    logical_id = _string_choice(panel.get("logical_id"), _LOGICAL_ID, f"{context} logical_id")
    location = _choice(panel.get("location"), _LOCATIONS, f"{context} location")
    alignment = _choice(panel.get("alignment", "center"), _ALIGNMENTS, f"{context} alignment")
    floating = panel.get("floating", True)
    if not isinstance(floating, bool):
        raise ValueError(f"{context} floating must be a boolean")
    height = _dimension(panel.get("height"), f"{context} height", 24, 160)
    screen_role = _choice(
        panel.get("screen_role", "primary"), _SCREEN_ROLES, f"{context} screen_role"
    )
    widgets_value = panel.get("widgets", [])
    if not isinstance(widgets_value, list):
        raise ValueError(f"{context} widgets must be an array")
    if len(widgets_value) > 64:
        raise ValueError(f"{context} may contain at most 64 widgets")
    widgets = tuple(_parse_widget(item, context) for item in widgets_value)
    length_mode = _choice(
        panel.get("length_mode", "fill"), _LENGTH_MODES, f"{context} length_mode"
    )
    length_value = panel.get("length")
    if length_mode == "custom" and length_value is None:
        raise ValueError(f"{context} custom length_mode requires length")
    if length_mode != "custom" and length_value is not None:
        raise ValueError(f"{context} length is only valid for custom length_mode")
    length = (
        _dimension(length_value, f"{context} length", 100, 16_384)
        if length_value is not None
        else None
    )
    hiding = _choice(panel.get("hiding", "none"), _HIDING, f"{context} hiding")
    opacity = _choice(panel.get("opacity", "adaptive"), _OPACITY, f"{context} opacity")
    return PanelSpec(
        logical_id,
        location,
        alignment,
        floating,
        height,
        screen_role,
        widgets,
        length_mode,
        length,
        hiding,
        opacity,
    )


def _parse_widget(value: Any, panel_context: str) -> WidgetSpec:
    widget = _object(value, f"{panel_context} widget")
    _only_keys(widget, {"plugin", "slot"}, f"{panel_context} widget")
    plugin = _string_choice(widget.get("plugin"), _PLUGIN_ID, "Widget plugin")
    if plugin == PANEL_SPACER:
        raise ValueError("Panel spacer placement is derived from slots and cannot be declared")
    slot = _choice(widget.get("slot"), _SLOTS, "Widget slot")
    return WidgetSpec(plugin, slot)


def _dimension(value: Any, context: str, default_min: int, default_max: int) -> Dimension:
    item = _object(value, context)
    _only_keys(item, {"unit", "value", "min_px", "max_px"}, context)
    unit = _choice(item.get("unit"), frozenset({"pixels", "screen_percent"}), f"{context} unit")
    number = item.get("value")
    if (
        isinstance(number, bool)
        or not isinstance(number, (int, float))
        or not math.isfinite(number)
    ):
        raise ValueError(f"{context} value must be a finite number")
    if number <= 0 or (unit == "screen_percent" and number > 100):
        raise ValueError(f"{context} value is outside its supported range")
    minimum = item.get("min_px", default_min)
    maximum = item.get("max_px", default_max)
    if (
        isinstance(minimum, bool)
        or isinstance(maximum, bool)
        or not isinstance(minimum, int)
        or not isinstance(maximum, int)
        or minimum < 1
        or maximum > 16_384
        or minimum > maximum
    ):
        raise ValueError(f"{context} min_px/max_px bounds are invalid")
    return Dimension(unit, float(number), minimum, maximum)


def _compile_widgets(widgets: tuple[WidgetSpec, ...]) -> list[dict[str, Any]]:
    slots = {slot: [widget.plugin for widget in widgets if widget.slot == slot] for slot in _SLOTS}
    output: list[dict[str, Any]] = []
    output.extend({"plugin": plugin, "slot": "left"} for plugin in slots["left"])
    if slots["center"]:
        output.append(_spacer())
        output.extend({"plugin": plugin, "slot": "center"} for plugin in slots["center"])
        output.append(_spacer())
    elif slots["right"]:
        output.append(_spacer())
    output.extend({"plugin": plugin, "slot": "right"} for plugin in slots["right"])
    return output


def _spacer() -> dict[str, Any]:
    return {
        "plugin": PANEL_SPACER,
        "slot": "generated",
        "config": {"/General": {"expanding": "true"}},
    }


def _screen(value: Any, index: int) -> dict[str, int]:
    screen = _object(value, f"Screen {index}")
    output: dict[str, int] = {}
    for key in ("x", "y", "width", "height"):
        item = screen.get(key)
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise RuntimeError(f"Plasma returned an invalid screen {key}")
        output[key] = round(item)
    if output["width"] <= 0 or output["height"] <= 0:
        raise RuntimeError("Plasma returned a screen with invalid dimensions")
    return output


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _only_keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unknown fields: {', '.join(unknown)}")


def _choice(value: Any, allowed: frozenset[str], context: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{context} must be one of: {', '.join(sorted(allowed))}")
    return value


def _string_choice(value: Any, pattern: re.Pattern[str], context: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{context} contains unsupported characters")
    return value
