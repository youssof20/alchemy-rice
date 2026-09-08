from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from alchemy.domain.capabilities import EnvironmentReport, SettingObservation
from alchemy.domain.panels import PANEL_SPACER
from alchemy.domain.rice import SCHEMA_URI, canonical_json_bytes, parse_rice_bytes
from alchemy.domain.sanitizer import SanitizationContext, SanitizationReport, scan_publication

CAPTURE_COMPONENTS = frozenset(
    {
        "colors",
        "fonts",
        "icons",
        "cursor",
        "plasma_theme",
        "application_style",
        "window_decoration",
        "kwin",
        "panels",
        "wallpaper",
        "effects",
        "apps",
    }
)

_SETTING_ALLOWLIST: dict[str, tuple[str, str, str]] = {
    "kdeglobals [General] ColorScheme": ("colors", "scheme", "text"),
    "kdeglobals [Icons] Theme": ("icons", "theme", "text"),
    "kdeglobals [General] font": ("fonts", "general", "text"),
    "kdeglobals [General] fixed": ("fonts", "fixed", "text"),
    "kdeglobals [General] smallestReadableFont": ("fonts", "small", "text"),
    "kdeglobals [General] toolBarFont": ("fonts", "toolbar", "text"),
    "kdeglobals [General] menuFont": ("fonts", "menu", "text"),
    "kdeglobals [WM] activeFont": ("fonts", "window_title", "text"),
    "kcminputrc [Mouse] cursorTheme": ("cursor", "theme", "text"),
    "kcminputrc [Mouse] cursorSize": ("cursor", "size", "integer"),
    "plasmarc [Theme] name": ("plasma_theme", "theme", "text"),
    "kdeglobals [KDE] widgetStyle": ("application_style", "theme", "text"),
    "kwinrc [org.kde.kdecoration2] theme": ("window_decoration", "theme", "text"),
    "kwinrc [org.kde.kdecoration2] library": ("window_decoration", "plugin", "text"),
    "kwinrc [org.kde.kdecoration2] BorderSize": (
        "window_decoration",
        "border_size",
        "text",
    ),
    "kwinrc [org.kde.kdecoration2] BorderSizeAuto": (
        "window_decoration",
        "border_auto",
        "boolean",
    ),
    "kwinrc [Windows] Placement": ("kwin", "placement", "text"),
    "kwinrc [Windows] BorderlessMaximizedWindows": (
        "kwin",
        "borderless_maximized",
        "boolean",
    ),
}


@dataclass(frozen=True, slots=True)
class CaptureFinding:
    code: str
    component: str
    detail: str
    blocking: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CaptureResult:
    manifest: dict[str, Any]
    included_components: tuple[str, ...]
    excluded_components: tuple[str, ...]
    findings: tuple[CaptureFinding, ...]
    sanitization: SanitizationReport

    @property
    def export_ready(self) -> bool:
        return self.sanitization.safe and not any(item.blocking for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_ready": self.export_ready,
            "included_components": list(self.included_components),
            "excluded_components": list(self.excluded_components),
            "findings": [finding.to_dict() for finding in self.findings],
            "sanitization": self.sanitization.to_dict(),
            "manifest": self.manifest if self.sanitization.safe else None,
            "summary": render_capture_summary(self) if self.sanitization.safe else None,
        }


def build_capture(
    metadata: dict[str, Any],
    report: EnvironmentReport,
    *,
    panel_state: dict[str, Any] | None,
    panel_error: str | None,
    excluded: frozenset[str],
    sanitizer_context: SanitizationContext,
) -> CaptureResult:
    unknown_exclusions = sorted(excluded - CAPTURE_COMPONENTS)
    if unknown_exclusions:
        raise ValueError("Unknown capture components: " + ", ".join(unknown_exclusions))

    components: dict[str, dict[str, Any]] = {}
    findings: list[CaptureFinding] = []
    for observation in report.settings:
        _capture_observation(observation, components, findings, excluded)
    findings.extend(_component_provenance_findings(components))

    if "panels" not in excluded:
        if panel_state is not None:
            panel_component, panel_findings = _capture_panels(panel_state)
            findings.extend(panel_findings)
            if panel_component is not None:
                components["panels"] = panel_component
        else:
            findings.append(
                CaptureFinding(
                    "panels_unavailable",
                    "panels",
                    panel_error or "Panel inspection was unavailable; panels were omitted",
                )
            )

    for component, detail in (
        ("wallpaper", "Wallpaper capture requires a reviewed HTTPS asset, hash, and license"),
        ("effects", "KWin effect capture is not in the reviewed visual allowlist yet"),
        ("apps", "Application settings require separate reviewed adapter capture"),
    ):
        if component not in excluded:
            findings.append(CaptureFinding("component_omitted", component, detail))

    if not components:
        findings.append(
            CaptureFinding(
                "no_visual_settings_captured",
                "capture",
                "No reviewed visual settings were available",
                True,
            )
        )

    manifest = _manifest(metadata, report, components)
    # The rice validator is the final structural boundary for generated output.
    parse_rice_bytes(canonical_json_bytes(manifest))
    sanitization = scan_publication(manifest, sanitizer_context)
    return CaptureResult(
        manifest,
        tuple(sorted(components)),
        tuple(sorted(excluded)),
        tuple(findings),
        sanitization,
    )


def render_capture_summary(result: CaptureResult) -> str:
    if not result.sanitization.safe:
        raise ValueError("A summary cannot be generated from an unsafe capture")
    manifest = result.manifest
    compatibility = manifest["compatibility"]
    lines = [
        f"# {manifest['name']}",
        "",
        f"Alchemy rice `{manifest['id']}` version `{manifest['version']}`.",
        "",
        "## Components",
        "",
    ]
    if result.included_components:
        lines.extend(
            _component_summary(component, manifest["components"][component])
            for component in result.included_components
        )
    else:
        lines.append("- No components captured")
    lines.extend(
        [
            "",
            "## Compatibility",
            "",
            f"- Plasma: `{compatibility['plasma']}`",
            f"- Session: {', '.join(compatibility['session'])}",
            "",
            "## Dependencies",
            "",
            (
                "- None declared"
                if not manifest["dependencies"]
                else f"- {len(manifest['dependencies'])} declared"
            ),
        ]
    )
    if result.findings:
        lines.extend(["", "## Capture notes", ""])
        lines.extend(f"- {finding.component}: {finding.detail}" for finding in result.findings)
    return "\n".join(lines) + "\n"


def _capture_observation(
    observation: SettingObservation,
    components: dict[str, dict[str, Any]],
    findings: list[CaptureFinding],
    excluded: frozenset[str],
) -> None:
    target = _SETTING_ALLOWLIST.get(observation.source)
    if target is None:
        findings.append(
            CaptureFinding(
                "setting_not_allowlisted",
                observation.component,
                "An observed setting was omitted because its source is not allowlisted",
            )
        )
        return
    component, key, converter = target
    if component in excluded:
        return
    if not observation.available or observation.value is None:
        findings.append(
            CaptureFinding(
                "setting_unavailable",
                component,
                f"{observation.label} was unavailable or inherited and was omitted",
            )
        )
        return
    try:
        captured = _convert(observation.value, converter)
    except ValueError:
        findings.append(
            CaptureFinding(
                "setting_value_unsupported",
                component,
                f"{observation.label} had an unsupported value and was omitted",
                True,
            )
        )
        return
    components.setdefault(component, {})[key] = captured


def _convert(value: str, converter: str) -> str | int | bool:
    if converter == "integer":
        converted = int(value)
        if not 0 <= converted <= 512:
            raise ValueError("out of range")
        return converted
    if converter == "boolean":
        lowered = value.casefold()
        if lowered not in {"true", "false"}:
            raise ValueError("not boolean")
        return lowered == "true"
    return value


def _capture_panels(
    state: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[CaptureFinding]]:
    findings: list[CaptureFinding] = []
    raw_panels = state.get("panels")
    if not isinstance(raw_panels, list) or not raw_panels:
        return None, [CaptureFinding("panels_empty", "panels", "No panels were observed")]
    captured: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_panels):
        if not isinstance(raw, dict) or raw.get("screen") != 0:
            return None, [
                CaptureFinding(
                    "panel_screen_intent_unknown",
                    "panels",
                    "A non-primary panel cannot be converted to a portable screen "
                    "role; exclude or edit panels",
                    True,
                )
            ]
        if raw.get("length_mode") == "custom":
            return None, [
                CaptureFinding(
                    "panel_custom_length_unavailable",
                    "panels",
                    "Current public panel inspection does not expose custom length; "
                    "exclude or edit panels",
                    True,
                )
            ]
        try:
            widget_specs, third_party = _capture_widgets(raw.get("widgets"))
        except ValueError:
            return None, [
                CaptureFinding(
                    "panel_widgets_unsupported",
                    "panels",
                    "Panel widget identifiers could not be represented safely",
                    True,
                )
            ]
        if third_party:
            findings.append(
                CaptureFinding(
                    "widget_provenance_unresolved",
                    "panels",
                    "A non-KDE widget requires explicit source and license metadata; "
                    "exclude or edit panels",
                    True,
                )
            )
        try:
            height = int(raw["height"])
        except (KeyError, TypeError, ValueError):
            return None, [
                CaptureFinding(
                    "panel_geometry_unsupported",
                    "panels",
                    "A panel height could not be represented safely",
                    True,
                )
            ]
        captured.append(
            {
                "logical_id": f"captured-{index + 1}-{raw.get('location', 'panel')}",
                "location": raw.get("location"),
                "alignment": raw.get("alignment"),
                "floating": raw.get("floating"),
                "height": {"unit": "pixels", "value": height},
                "screen_role": "primary",
                "length_mode": raw.get("length_mode"),
                "hiding": raw.get("hiding"),
                "opacity": raw.get("opacity"),
                "widgets": widget_specs,
            }
        )
    return {"panels": captured}, findings


def _component_provenance_findings(
    components: dict[str, dict[str, Any]],
) -> list[CaptureFinding]:
    findings: list[CaptureFinding] = []
    if components.get("fonts"):
        findings.append(
            CaptureFinding(
                "component_provenance_unresolved",
                "fonts",
                "Font names were captured, but installed package provenance is unresolved",
            )
        )
    for component, key in (
        ("colors", "scheme"),
        ("icons", "theme"),
        ("cursor", "theme"),
        ("plasma_theme", "theme"),
        ("application_style", "theme"),
        ("window_decoration", "plugin"),
        ("window_decoration", "theme"),
    ):
        value = components.get(component, {}).get(key)
        if isinstance(value, str) and not _known_platform_component(value):
            finding = CaptureFinding(
                "component_provenance_unresolved",
                component,
                "A captured component name may require explicit package, source, "
                "and license metadata",
            )
            if finding not in findings:
                findings.append(finding)
    return findings


def _known_platform_component(value: str) -> bool:
    normalized = re.sub(r"[\s_-]+", "", value.casefold())
    return (
        normalized == "default"
        or normalized.startswith("breeze")
        or value.casefold().startswith("org.kde.breeze")
    )


def _capture_widgets(value: Any) -> tuple[list[dict[str, str]], bool]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("Panel widgets must be public plugin identifiers")
    plugins = [str(item) for item in value]
    spacer_indexes = [index for index, plugin in enumerate(plugins) if plugin == PANEL_SPACER]
    widgets: list[dict[str, str]] = []
    for index, plugin in enumerate(plugins):
        if plugin == PANEL_SPACER:
            continue
        if not spacer_indexes or index < spacer_indexes[0]:
            slot = "left"
        elif len(spacer_indexes) > 1 and index < spacer_indexes[1]:
            slot = "center"
        else:
            slot = "right"
        widgets.append({"plugin": plugin, "slot": slot})
    third_party = any(not widget["plugin"].startswith("org.kde.plasma.") for widget in widgets)
    return widgets, third_party


def _component_summary(component: str, value: dict[str, Any]) -> str:
    label = component.replace("_", " ").title()
    if component == "panels":
        panels = value.get("panels", [])
        widget_count = sum(len(panel.get("widgets", [])) for panel in panels)
        return f"- {label}: {len(panels)} panel(s), {widget_count} widget(s)"
    details: list[str] = []
    for key, item in value.items():
        if isinstance(item, (str, int, bool)):
            rendered = str(item).lower() if isinstance(item, bool) else item
            details.append(f"{key.replace('_', ' ')} `{rendered}`")
    return f"- {label}: {', '.join(details)}" if details else f"- {label}"


def _manifest(
    metadata: dict[str, Any], report: EnvironmentReport, components: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    required = {"id", "name", "version", "author", "source"}
    if set(metadata) != required:
        raise ValueError("Capture metadata must contain exactly: " + ", ".join(sorted(required)))
    capability = report.capabilities
    assert capability.plasma_version is not None
    major, minor, *_ = (int(part) for part in capability.plasma_version.split("."))
    compatibility: dict[str, Any] = {
        "plasma": f">={major}.{minor},<{major}.{minor + 1}",
        "session": [capability.session],
        "tested": [],
    }
    if capability.distro:
        compatibility["distros"] = [capability.distro]
        compatibility["tested"] = [
            {
                "distro": capability.distro,
                "plasma": capability.plasma_version,
                "session": capability.session,
            }
        ]
    return {
        "$schema": SCHEMA_URI,
        "schema_version": 2,
        **metadata,
        "compatibility": compatibility,
        "components": components,
        "dependencies": [],
        "licenses": [],
        "gallery": {"screenshots": [], "reddit_url": None, "tip_url": None},
    }
