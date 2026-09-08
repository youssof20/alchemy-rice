from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from alchemy.domain.capabilities import CapabilityMatrix
from alchemy.domain.panels import parse_panel_layout
from alchemy.domain.versioning import Version, VersionRange

SCHEMA_URI = (
    "https://raw.githubusercontent.com/youssof20/alchemy-rice/main/"
    "schemas/rice-v2.schema.json"
)
RICE_MAX_BYTES = 1024 * 1024
OVERRIDE_MAX_BYTES = 256 * 1024

_SEMVER_IDENTIFIER = r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    rf"(?:-({_SEMVER_IDENTIFIER}(?:\.{_SEMVER_IDENTIFIER})*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+-]{0,191}$")
_COMPONENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,191}$")
_VISUAL_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. +()_-]{0,191}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SPDX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-.+]{0,127}$")
_SOURCE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/-]{0,127}$")
_MUTABLE_RELEASES = frozenset({"main", "master", "head", "latest", "develop", "dev"})
_COMPONENT_KEYS = frozenset(
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
        "effects",
        "wallpaper",
        "apps",
    }
)


@dataclass(frozen=True, slots=True)
class RiceManifest:
    data: dict[str, Any]
    canonical_bytes: bytes
    sha256: str

    @property
    def identity(self) -> str:
        return f"{self.data['id']}@{self.data['version']}"


@dataclass(frozen=True, slots=True)
class RiceOverride:
    data: dict[str, Any]
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class ResolvedRice:
    base: RiceManifest
    override: RiceOverride
    data: dict[str, Any]
    canonical_bytes: bytes
    resolved_sha256: str
    provenance: dict[str, str]


@dataclass(frozen=True, slots=True)
class CompatibilityIssue:
    severity: str
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    status: str
    issues: tuple[CompatibilityIssue, ...]

    @property
    def compatible(self) -> bool | None:
        if self.status == "incompatible":
            return False
        if self.status == "unknown":
            return None
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "compatible": self.compatible,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def load_rice(path_value: str | Path, *, require_canonical: bool = True) -> RiceManifest:
    path = Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Rice input must be a regular file")
    raw = _read_limited(path, RICE_MAX_BYTES, "Rice")
    return parse_rice_bytes(raw, require_canonical=require_canonical)


def parse_rice_bytes(raw: bytes, *, require_canonical: bool = True) -> RiceManifest:
    if len(raw) > RICE_MAX_BYTES:
        raise ValueError("Rice exceeds the 1024 KiB input limit")
    parsed = _parse_json(raw, "Rice")
    _validate_tree_limits(parsed)
    canonical = canonical_json_bytes(parsed)
    normalized = _normalized(canonical)
    _validate_manifest(normalized)
    if require_canonical and raw != canonical:
        raise ValueError(
            "Rice file is not canonical JSON; export it with alchemy rice-export first"
        )
    return RiceManifest(normalized, canonical, hashlib.sha256(canonical).hexdigest())


def load_override(path_value: str | Path) -> RiceOverride:
    path = Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Override input must be a regular file")
    raw = _read_limited(path, OVERRIDE_MAX_BYTES, "Override")
    return parse_override_bytes(raw)


def parse_override_bytes(raw: bytes) -> RiceOverride:
    if len(raw) > OVERRIDE_MAX_BYTES:
        raise ValueError("Override exceeds the 256 KiB input limit")
    parsed = _parse_json(raw, "Override")
    _validate_tree_limits(parsed)
    canonical = canonical_json_bytes(parsed)
    normalized = _normalized(canonical)
    _validate_override(normalized)
    return RiceOverride(normalized, canonical, hashlib.sha256(canonical).hexdigest())


def resolve_override(base: RiceManifest, override: RiceOverride) -> ResolvedRice:
    binding = override.data["base"]
    expected = {
        "id": base.data["id"],
        "version": base.data["version"],
        "sha256": base.sha256,
    }
    if binding != expected:
        raise ValueError("Override base identity, version, or SHA-256 does not match the rice")
    merged = copy.deepcopy(base.data)
    merged["components"] = _merge_patch(merged["components"], override.data["components"])
    _validate_manifest(merged)
    canonical = canonical_json_bytes(merged)
    normalized = _normalized(canonical)
    provenance: dict[str, str] = {}
    _record_leaves(base.data["components"], "/components", "base", provenance)
    _record_leaves(override.data["components"], "/components", "override", provenance)
    return ResolvedRice(
        base,
        override,
        normalized,
        canonical,
        hashlib.sha256(canonical).hexdigest(),
        provenance,
    )


def verify_sha256(actual: str, expected: str | None) -> None:
    if expected is None:
        return
    normalized = expected.lower()
    if _HASH.fullmatch(normalized) is None:
        raise ValueError("Expected SHA-256 must contain 64 hexadecimal characters")
    if actual != normalized:
        raise ValueError(f"Rice SHA-256 mismatch: expected {normalized}, observed {actual}")


def evaluate_compatibility(
    manifest: RiceManifest | dict[str, Any], capability: CapabilityMatrix
) -> CompatibilityReport:
    data = manifest.data if isinstance(manifest, RiceManifest) else manifest
    rules = data["compatibility"]
    issues: list[CompatibilityIssue] = []
    if capability.host_os != "linux":
        issues.append(
            CompatibilityIssue("error", "host_os", "Rice application requires Linux")
        )
    desktop = capability.desktop.lower() if capability.desktop else None
    if desktop is None:
        issues.append(
            CompatibilityIssue("unknown", "desktop_unknown", "Desktop environment is unknown")
        )
    elif "kde" not in desktop and "plasma" not in desktop:
        issues.append(
            CompatibilityIssue("error", "desktop", "The active desktop is not KDE Plasma")
        )
    if capability.plasma_version is None:
        issues.append(
            CompatibilityIssue("unknown", "plasma_unknown", "Plasma version is unknown")
        )
    else:
        try:
            matches_plasma = VersionRange.parse(rules["plasma"]).matches(
                Version.parse(capability.plasma_version)
            )
        except ValueError:
            issues.append(
                CompatibilityIssue(
                    "unknown", "plasma_unparseable", "Detected Plasma version is unparseable"
                )
            )
        else:
            detected_version = Version.parse(capability.plasma_version)
            if not matches_plasma:
                issues.append(
                    CompatibilityIssue(
                        "error",
                        "plasma_range",
                        f"Plasma {capability.plasma_version} is outside {rules['plasma']}",
                    )
                )
            if not VersionRange.parse(">=6.6,<6.9").matches(detected_version):
                issues.append(
                    CompatibilityIssue(
                        "error",
                        "engine_plasma_range",
                        "This Alchemy build targets Plasma 6.6 through 6.8",
                    )
                )
    if capability.session is None:
        issues.append(CompatibilityIssue("unknown", "session_unknown", "Session is unknown"))
    elif capability.session not in rules["session"]:
        issues.append(
            CompatibilityIssue(
                "error",
                "session",
                f"Session {capability.session} is not declared compatible",
            )
        )
    distros = rules.get("distros")
    if distros:
        if capability.distro is None:
            issues.append(
                CompatibilityIssue("unknown", "distro_unknown", "Distribution is unknown")
            )
        elif capability.distro not in distros:
            issues.append(
                CompatibilityIssue(
                    "error",
                    "distro",
                    f"Distribution {capability.distro} is not declared compatible",
                )
            )
    if capability.plasma_manager.active:
        issues.append(
            CompatibilityIssue(
                "error",
                "state_owner",
                "plasma-manager owns the current Plasma configuration",
            )
        )
    if capability.mixed_scale and data["components"].get("panels"):
        issues.append(
            CompatibilityIssue(
                "warning",
                "mixed_scale_review",
                "Panel dimensions require a per-screen mapping preview on mixed-scale displays",
            )
        )
    style = data["components"].get("application_style", {}).get("style_engine")
    if style and style["type"] == "union":
        if capability.union.installed is False:
            issues.append(
                CompatibilityIssue(
                    "error", "union_missing", "The rice requires the Union style engine"
                )
            )
        elif capability.union.installed is None:
            issues.append(
                CompatibilityIssue(
                    "unknown",
                    "union_unknown",
                    "Union availability cannot be determined reliably",
                )
            )
    if data["dependencies"]:
        issues.append(
            CompatibilityIssue(
                "warning",
                "dependencies_unresolved",
                "Dependency availability has not been resolved by this compatibility check",
            )
        )
    if not _source_is_pinned(data["source"]):
        issues.append(
            CompatibilityIssue(
                "warning",
                "mutable_source",
                "Source release is mutable and is not eligible for trusted one-click apply",
            )
        )
    severities = {issue.severity for issue in issues}
    if "error" in severities:
        status = "incompatible"
    elif "unknown" in severities:
        status = "unknown"
    elif issues:
        status = "compatible_with_warnings"
    else:
        status = "compatible"
    return CompatibilityReport(status, tuple(issues))


def canonical_json_bytes(value: Any) -> bytes:
    return _canonical(value).encode()


def _canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if len(str(abs(value))) > 100:
            raise ValueError("JSON integer is outside canonical limits")
        return str(value)
    if isinstance(value, (float, Decimal)):
        decimal = Decimal(str(value)) if isinstance(value, float) else value
        if (
            not decimal.is_finite()
            or abs(decimal.adjusted()) > 308
            or len(decimal.as_tuple().digits) > 100
        ):
            raise ValueError("JSON number is outside canonical limits")
        if decimal.is_zero():
            return "0"
        rendered = format(decimal, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return rendered
    if isinstance(value, str):
        try:
            value.encode()
        except UnicodeEncodeError as exc:
            raise ValueError("JSON strings may not contain lone Unicode surrogates") from exc
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        return "{" + ",".join(
            f"{_canonical(key)}:{_canonical(value[key])}" for key in sorted(value)
        ) + "}"
    raise ValueError(f"Unsupported JSON value type: {type(value).__name__}")


def _validate_manifest(value: Any) -> None:
    manifest = _object(value, "Rice")
    root_fields = {
        "$schema",
        "schema_version",
        "id",
        "name",
        "version",
        "author",
        "source",
        "compatibility",
        "components",
        "dependencies",
        "licenses",
        "gallery",
    }
    _strict(manifest, root_fields, root_fields, "Rice")
    if manifest["$schema"] != SCHEMA_URI or manifest["schema_version"] != 2:
        raise ValueError("Rice must use the supported v2 schema URI and schema_version 2")
    _identifier(manifest["id"], "Rice id")
    _plain_text(manifest["name"], "Rice name", maximum=128)
    if (
        not isinstance(manifest["version"], str)
        or len(manifest["version"]) > 128
        or _SEMVER.fullmatch(manifest["version"]) is None
    ):
        raise ValueError("Rice version must be a Semantic Version")
    _validate_author(manifest["author"])
    _validate_source(manifest["source"])
    _validate_compatibility(manifest["compatibility"])
    _validate_components(manifest["components"])
    _validate_dependencies(manifest["dependencies"])
    _validate_licenses(manifest["licenses"])
    _validate_gallery(manifest["gallery"])


def _validate_author(value: Any) -> None:
    author = _object(value, "Author")
    _strict(author, {"name"}, {"name", "url"}, "Author")
    _plain_text(author["name"], "Author name", maximum=128)
    if "url" in author:
        _https_url(author["url"], "Author URL")


def _validate_source(value: Any) -> None:
    source = _object(value, "Source")
    _strict(source, {"repo", "release", "commit"}, {"repo", "release", "commit"}, "Source")
    _https_url(source["repo"], "Source repository URL")
    _source_ref(source["release"], "Source release")
    if not isinstance(source["commit"], str) or _COMMIT.fullmatch(source["commit"]) is None:
        raise ValueError("Source commit must be a full lowercase Git SHA-1")


def _validate_compatibility(value: Any) -> None:
    compatibility = _object(value, "Compatibility")
    _strict(
        compatibility,
        {"plasma", "session", "tested"},
        {"plasma", "session", "distros", "tested"},
        "Compatibility",
    )
    if not isinstance(compatibility["plasma"], str):
        raise ValueError("Compatibility plasma range must be a string")
    VersionRange.parse(compatibility["plasma"])
    _string_list(compatibility["session"], "Compatibility sessions", {"wayland", "x11"}, 2)
    if "distros" in compatibility:
        _string_list(compatibility["distros"], "Compatibility distros", None, 32)
        for distro in compatibility["distros"]:
            _component_identifier(distro, "Compatibility distro")
    tested = compatibility["tested"]
    if not isinstance(tested, list) or len(tested) > 64:
        raise ValueError("Compatibility tested must be an array with at most 64 entries")
    for index, value in enumerate(tested):
        entry = _object(value, f"Tested environment {index}")
        fields = {"distro", "plasma", "session"}
        _strict(entry, fields, fields, f"Tested environment {index}")
        _component_identifier(entry["distro"], "Tested distro")
        Version.parse(entry["plasma"])
        if entry["session"] not in {"wayland", "x11"}:
            raise ValueError("Tested session must be wayland or x11")


def _validate_components(value: Any) -> None:
    components = _object(value, "Components")
    unknown = sorted(set(components) - _COMPONENT_KEYS)
    if unknown:
        raise ValueError(f"Components contains unknown fields: {', '.join(unknown)}")
    validators = {
        "colors": _validate_colors,
        "fonts": _validate_fonts,
        "icons": _validate_theme,
        "cursor": _validate_cursor,
        "plasma_theme": _validate_theme,
        "application_style": _validate_application_style,
        "window_decoration": _validate_decoration,
        "kwin": _validate_kwin,
        "panels": _validate_panels,
        "effects": _validate_effects,
        "wallpaper": _validate_wallpaper,
        "apps": _validate_apps,
    }
    for key, component in components.items():
        validators[key](component)


def _validate_colors(value: Any) -> None:
    item = _object(value, "Colors")
    _strict(item, set(), {"scheme"}, "Colors")
    if "scheme" in item:
        _visual_identifier(item["scheme"], "Color scheme")


def _validate_fonts(value: Any) -> None:
    item = _object(value, "Fonts")
    roles = {"general", "fixed", "small", "toolbar", "menu", "window_title"}
    _strict(item, set(), roles, "Fonts")
    for role, font in item.items():
        _plain_text(font, f"Font {role}", maximum=512)


def _validate_theme(value: Any) -> None:
    item = _object(value, "Theme")
    _strict(item, set(), {"theme"}, "Theme")
    if "theme" in item:
        _visual_identifier(item["theme"], "Theme identifier")


def _validate_cursor(value: Any) -> None:
    item = _object(value, "Cursor")
    _strict(item, set(), {"theme", "size"}, "Cursor")
    if "theme" in item:
        _visual_identifier(item["theme"], "Cursor theme")
    if "size" in item:
        _bounded_integer(item["size"], "Cursor size", 0, 512)


def _validate_application_style(value: Any) -> None:
    item = _object(value, "Application style")
    _strict(item, set(), {"theme", "style_engine"}, "Application style")
    if "theme" in item:
        _visual_identifier(item["theme"], "Application style theme")
    if "style_engine" in item:
        engine = _object(item["style_engine"], "Style engine")
        _strict(
            engine,
            {"type", "min_version", "experimental"},
            {"type", "min_version", "experimental"},
            "Style engine",
        )
        if engine["type"] not in {"breeze", "kvantum", "union", "other"}:
            raise ValueError("Style engine type is unsupported")
        if engine["min_version"] is not None:
            Version.parse(engine["min_version"])
        if not isinstance(engine["experimental"], bool):
            raise ValueError("Style engine experimental must be a boolean")


def _validate_decoration(value: Any) -> None:
    item = _object(value, "Window decoration")
    _strict(item, set(), {"plugin", "theme", "border_size", "border_auto"}, "Window decoration")
    if "plugin" in item:
        _component_identifier(item["plugin"], "Window decoration plugin")
    for key in ("theme", "border_size"):
        if key in item:
            _visual_identifier(item[key], f"Window decoration {key}")
    if "border_auto" in item and not isinstance(item["border_auto"], bool):
        raise ValueError("Window decoration border_auto must be a boolean")


def _validate_kwin(value: Any) -> None:
    item = _object(value, "KWin")
    _strict(item, set(), {"placement", "borderless_maximized"}, "KWin")
    if "placement" in item:
        _component_identifier(item["placement"], "KWin placement")
    if "borderless_maximized" in item and not isinstance(item["borderless_maximized"], bool):
        raise ValueError("KWin borderless_maximized must be a boolean")


def _validate_panels(value: Any) -> None:
    item = _object(value, "Panels")
    _strict(item, {"panels"}, {"panels"}, "Panels")
    parse_panel_layout({"format_version": 1, "panels": item["panels"]})


def _validate_effects(value: Any) -> None:
    item = _object(value, "Effects")
    _strict(item, set(), {"enabled", "disabled"}, "Effects")
    enabled = (
        _string_list(item["enabled"], "Enabled effects", None, 128)
        if "enabled" in item
        else []
    )
    disabled = (
        _string_list(item["disabled"], "Disabled effects", None, 128)
        if "disabled" in item
        else []
    )
    for effect in (*enabled, *disabled):
        _component_identifier(effect, "Effect identifier")
    overlap = sorted(set(enabled) & set(disabled))
    if overlap:
        raise ValueError(f"Effects cannot be enabled and disabled together: {', '.join(overlap)}")


def _validate_wallpaper(value: Any) -> None:
    item = _object(value, "Wallpaper")
    _strict(
        item,
        {"url", "sha256", "license"},
        {"url", "sha256", "license", "fill_mode"},
        "Wallpaper",
    )
    _https_url(item["url"], "Wallpaper URL")
    _sha256(item["sha256"], "Wallpaper SHA-256")
    _spdx(item["license"], "Wallpaper license")
    if item.get("fill_mode", "preserveAspectCrop") not in {
        "stretch",
        "preserveAspectFit",
        "preserveAspectCrop",
        "pad",
    }:
        raise ValueError("Wallpaper fill_mode is unsupported")


def _validate_apps(value: Any) -> None:
    item = _object(value, "Apps")
    if item:
        raise ValueError("App adapter settings are not supported by the v2 implementation yet")


def _validate_dependencies(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 256:
        raise ValueError("Dependencies must be an array with at most 256 entries")
    identifiers: set[str] = set()
    for index, raw in enumerate(value):
        item = _object(raw, f"Dependency {index}")
        fields = {"id", "capability", "component_type", "source", "license"}
        _strict(item, fields, fields, f"Dependency {index}")
        identifier = _identifier(item["id"], f"Dependency {index} id")
        if identifier in identifiers:
            raise ValueError(f"Duplicate dependency id: {identifier}")
        identifiers.add(identifier)
        _component_identifier(item["capability"], f"Dependency {index} capability")
        if item["component_type"] not in {"config", "asset", "executable"}:
            raise ValueError(f"Dependency {index} component_type is unsupported")
        _spdx(item["license"], f"Dependency {index} license")
        _validate_dependency_source(item["source"], index)


def _validate_dependency_source(value: Any, index: int) -> None:
    source = _object(value, f"Dependency {index} source")
    allowed = {"type", "package", "url", "version", "release", "commit", "sha256"}
    _strict(source, {"type"}, allowed, f"Dependency {index} source")
    if source["type"] not in {"distro_package", "kde_store", "github_release", "manual"}:
        raise ValueError(f"Dependency {index} source type is unsupported")
    if "package" in source:
        _component_identifier(source["package"], f"Dependency {index} package")
    if "url" in source:
        _https_url(source["url"], f"Dependency {index} URL")
    if "version" in source:
        _source_ref(source["version"], f"Dependency {index} version")
    if "release" in source:
        _source_ref(source["release"], f"Dependency {index} release")
    if "commit" in source and (
        not isinstance(source["commit"], str) or _COMMIT.fullmatch(source["commit"]) is None
    ):
        raise ValueError(f"Dependency {index} commit must be a full lowercase Git SHA-1")
    if "sha256" in source:
        _sha256(source["sha256"], f"Dependency {index} SHA-256")
    if source["type"] == "distro_package" and "package" not in source:
        raise ValueError(f"Dependency {index} distro package source requires package")
    if source["type"] != "distro_package" and "url" not in source:
        raise ValueError(f"Dependency {index} external source requires an HTTPS URL")


def _validate_licenses(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 256:
        raise ValueError("Licenses must be an array with at most 256 entries")
    for index, raw in enumerate(value):
        item = _object(raw, f"License {index}")
        _strict(item, {"id", "applies_to", "url"}, {"id", "applies_to", "url"}, f"License {index}")
        _spdx(item["id"], f"License {index} id")
        applies_to = _string_list(item["applies_to"], f"License {index} applies_to", None, 256)
        for target in applies_to:
            _identifier(target, f"License {index} target")
        _https_url(item["url"], f"License {index} URL")


def _validate_gallery(value: Any) -> None:
    gallery = _object(value, "Gallery")
    fields = {"screenshots", "reddit_url", "tip_url"}
    _strict(gallery, fields, fields, "Gallery")
    screenshots = gallery["screenshots"]
    if not isinstance(screenshots, list) or len(screenshots) > 32:
        raise ValueError("Gallery screenshots must be an array with at most 32 entries")
    for index, raw in enumerate(screenshots):
        item = _object(raw, f"Screenshot {index}")
        _strict(item, {"url", "sha256", "alt"}, {"url", "sha256", "alt"}, f"Screenshot {index}")
        _https_url(item["url"], f"Screenshot {index} URL")
        _sha256(item["sha256"], f"Screenshot {index} SHA-256")
        _plain_text(item["alt"], f"Screenshot {index} alt text", maximum=256)
    for key in ("reddit_url", "tip_url"):
        if gallery[key] is not None:
            _https_url(gallery[key], f"Gallery {key}")


def _validate_override(value: Any) -> None:
    override = _object(value, "Override")
    fields = {"override_version", "base", "components"}
    _strict(override, fields, fields, "Override")
    if override["override_version"] != 1:
        raise ValueError("Override version must be 1")
    base = _object(override["base"], "Override base")
    _strict(base, {"id", "version", "sha256"}, {"id", "version", "sha256"}, "Override base")
    _identifier(base["id"], "Override base id")
    if (
        not isinstance(base["version"], str)
        or len(base["version"]) > 128
        or _SEMVER.fullmatch(base["version"]) is None
    ):
        raise ValueError("Override base version must be a Semantic Version")
    _sha256(base["sha256"], "Override base SHA-256")
    components = _object(override["components"], "Override components")
    if not components:
        raise ValueError("Override components must not be empty")
    unknown = sorted(set(components) - _COMPONENT_KEYS)
    if unknown:
        raise ValueError(f"Override components contains unknown fields: {', '.join(unknown)}")
    if any(item is not None and not isinstance(item, dict) for item in components.values()):
        raise ValueError("Override component values must be objects or null")


def _parse_json(raw: bytes, context: str) -> Any:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{context} JSON must not contain a UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
        _precheck_nesting(text)
        return json.loads(
            text,
            object_pairs_hook=_no_duplicate_keys,
            parse_float=Decimal,
            parse_int=int,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{context} must be valid UTF-8 JSON") from exc


def _precheck_nesting(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > 32:
                raise ValueError("JSON document exceeds the 32-level nesting limit")
        elif character in "]}":
            depth -= 1


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is forbidden: {value}")


def _validate_tree_limits(value: Any, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > 10_000:
        raise ValueError("JSON document exceeds the 10,000-node limit")
    if depth > 32:
        raise ValueError("JSON document exceeds the 32-level nesting limit")
    if isinstance(value, str):
        if len(value) > 4096:
            raise ValueError("JSON string exceeds the 4,096-character limit")
        return
    if isinstance(value, list):
        if len(value) > 2048:
            raise ValueError("JSON array exceeds the 2,048-item limit")
        for item in value:
            _validate_tree_limits(item, depth=depth + 1, counter=counter)
    elif isinstance(value, dict):
        if len(value) > 256:
            raise ValueError("JSON object exceeds the 256-key limit")
        for key, item in value.items():
            if len(key) > 256:
                raise ValueError("JSON object key exceeds the 256-character limit")
            _validate_tree_limits(item, depth=depth + 1, counter=counter)


def _normalized(canonical: bytes) -> dict[str, Any]:
    value = json.loads(canonical)
    if not isinstance(value, dict):
        raise ValueError("JSON document root must be an object")
    return value


def _merge_patch(base: Any, patch: Any) -> Any:
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    result = copy.deepcopy(base) if isinstance(base, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = _merge_patch(result.get(key), value)
    return result


def _record_leaves(value: Any, path: str, origin: str, output: dict[str, str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            _record_leaves(item, f"{path}/{escaped}", origin, output)
    elif isinstance(value, list):
        output[path] = origin
    else:
        output[path] = origin


def _source_is_pinned(source: dict[str, Any]) -> bool:
    return source["release"].lower() not in _MUTABLE_RELEASES and bool(
        _COMMIT.fullmatch(source["commit"])
    )


def _read_limited(path: Path, limit: int, context: str) -> bytes:
    if path.stat().st_size > limit:
        raise ValueError(f"{context} exceeds the {limit // 1024} KiB input limit")
    return path.read_bytes()


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _strict(
    value: dict[str, Any], required: set[str], allowed: set[str], context: str
) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"{context} is missing required fields: {', '.join(missing)}")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unknown fields: {', '.join(unknown)}")


def _identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{context} contains unsupported characters")
    return value


def _component_identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or _COMPONENT_ID.fullmatch(value) is None:
        raise ValueError(f"{context} contains unsupported characters")
    return value


def _visual_identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or _VISUAL_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{context} contains unsupported characters")
    return value


def _plain_text(value: Any, context: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{context} is invalid")
    return value


def _https_url(value: Any, context: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{context} must be an HTTPS URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError(f"{context} must be an HTTPS URL without credentials or fragments")
    return value


def _sha256(value: Any, context: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{context} must be 64 lowercase hexadecimal characters")
    return value


def _spdx(value: Any, context: str) -> str:
    if not isinstance(value, str) or _SPDX.fullmatch(value) is None:
        raise ValueError(f"{context} must be an SPDX license identifier")
    return value


def _source_ref(value: Any, context: str) -> str:
    if not isinstance(value, str) or _SOURCE_REF.fullmatch(value) is None:
        raise ValueError(f"{context} contains unsupported characters")
    return value


def _bounded_integer(value: Any, context: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{context} must be an integer from {minimum} through {maximum}")
    return value


def _string_list(
    value: Any, context: str, allowed: set[str] | None, maximum: int
) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise ValueError(f"{context} must be a non-empty array with at most {maximum} entries")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{context} must contain only strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{context} must not contain duplicates")
    if allowed is not None and any(item not in allowed for item in value):
        raise ValueError(f"{context} contains an unsupported value")
    return value
