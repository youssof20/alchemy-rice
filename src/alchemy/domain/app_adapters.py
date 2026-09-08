from __future__ import annotations

import json
import re
import tomllib
from decimal import Decimal
from pathlib import Path
from typing import Any

APP_CONFIG_MAX_BYTES = 256 * 1024
SUPPORTED_APPS = ("konsole", "kitty", "starship", "fastfetch")

_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. +()-]{0,127}$")
_PALETTE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_SAFE_FASTFETCH_MODULES = frozenset(
    {
        "battery",
        "break",
        "colors",
        "cpu",
        "de",
        "disk",
        "display",
        "font",
        "gpu",
        "icons",
        "kernel",
        "locale",
        "memory",
        "os",
        "packages",
        "poweradapter",
        "shell",
        "terminal",
        "terminalfont",
        "theme",
        "uptime",
        "wm",
    }
)
_SAFE_STARSHIP_MODULES = frozenset(
    {"directory", "git_branch", "git_status", "cmd_duration", "line_break", "character"}
)
_STARSHIP_CHARACTER = re.compile(r"^\[(.{1,8})\]\(bold (#[0-9A-Fa-f]{6})\)$")
_STARSHIP_SCHEMA = "https://starship.rs/config-schema.json"
_KITTY_KEYS = (
    "font_family",
    "font_size",
    "foreground",
    "background",
    "cursor",
    "cursor_shape",
    "background_opacity",
)


def validate_apps(value: Any) -> dict[str, dict[str, Any]]:
    apps = _object(value, "Apps")
    if not apps:
        raise ValueError("Apps must contain at least one reviewed adapter")
    unknown = sorted(set(apps) - set(SUPPORTED_APPS))
    if unknown:
        raise ValueError(f"Apps contains unsupported adapters: {', '.join(unknown)}")
    return {
        app: validate_app_settings(app, settings)
        for app, settings in apps.items()
    }


def validate_app_settings(app: str, value: Any) -> dict[str, Any]:
    if app not in SUPPORTED_APPS:
        raise ValueError(f"Unsupported application adapter: {app}")
    if app == "konsole":
        return _validate_konsole(value)
    if app == "kitty":
        return _validate_kitty(value)
    if app == "starship":
        return _validate_starship(value)
    return _validate_fastfetch(value)


def parse_app_settings_bytes(app: str, raw: bytes) -> dict[str, Any]:
    if len(raw) > APP_CONFIG_MAX_BYTES:
        raise ValueError("Application settings exceed the 256 KiB input limit")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Application settings must be valid UTF-8 JSON") from exc
    return validate_app_settings(app, value)


def load_app_settings(app: str, path_value: str | Path) -> dict[str, Any]:
    candidate = Path(path_value).expanduser().absolute()
    if candidate.is_symlink():
        raise ValueError("Application settings must be a regular, non-symlink file")
    path = candidate.resolve(strict=True)
    if not path.is_file():
        raise ValueError("Application settings must be a regular, non-symlink file")
    with path.open("rb") as stream:
        raw = stream.read(APP_CONFIG_MAX_BYTES + 1)
    return parse_app_settings_bytes(app, raw)


def canonical_app_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def parse_owned_config(app: str, raw: bytes) -> dict[str, Any]:
    if len(raw) > APP_CONFIG_MAX_BYTES:
        raise ValueError("Application config exceeds the 256 KiB ownership limit")
    if app == "konsole":
        return _parse_owned_konsole(raw)
    if app == "kitty":
        return _parse_owned_kitty(raw)
    if app == "starship":
        return _parse_owned_starship(raw)
    if app == "fastfetch":
        return _parse_owned_fastfetch(raw)
    raise ValueError(f"Unsupported application adapter: {app}")


def render_owned_config(app: str, settings: dict[str, Any]) -> bytes:
    normalized = validate_app_settings(app, settings)
    if app == "konsole":
        return _render_konsole(normalized)
    if app == "kitty":
        return _render_kitty(normalized)
    if app == "starship":
        return _render_starship(normalized)
    rendered = json.dumps(
        normalized_to_fastfetch(normalized), indent=2, ensure_ascii=False
    )
    return rendered.encode() + b"\n"


def extract_repository_app(app: str, raw: bytes) -> tuple[dict[str, Any] | None, int]:
    """Extract reviewed visual fields while counting ignored repository settings."""
    if len(raw) > APP_CONFIG_MAX_BYTES:
        return None, 1
    try:
        if app == "konsole":
            return _extract_konsole(raw)
        if app == "kitty":
            return _extract_kitty(raw)
        if app == "starship":
            return _extract_starship(raw)
        if app == "fastfetch":
            return _extract_fastfetch(raw)
    except (UnicodeDecodeError, ValueError, tomllib.TOMLDecodeError):
        return None, 1
    raise ValueError(f"Unsupported application adapter: {app}")


def normalized_to_fastfetch(settings: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    logo = settings.get("logo")
    if logo is not None:
        result["logo"] = dict(logo)
    display: dict[str, Any] = {}
    for source, target in (
        ("separator", "separator"),
        ("bright_color", "brightColor"),
    ):
        if source in settings:
            display[target] = settings[source]
    colors = {
        target: settings[source]
        for source, target in (
            ("key_color", "keys"),
            ("title_color", "title"),
            ("output_color", "output"),
        )
        if source in settings
    }
    if colors:
        display["color"] = colors
    if display:
        result["display"] = display
    if "modules" in settings:
        result["modules"] = settings["modules"]
    return result


def _validate_konsole(value: Any) -> dict[str, Any]:
    item = _object(value, "Konsole settings")
    allowed = {
        "format_version",
        "color_scheme",
        "font_family",
        "font_size",
        "bold_intense",
        "line_spacing",
        "cursor_shape",
    }
    _strict(item, {"format_version"}, allowed, "Konsole settings")
    result: dict[str, Any] = {"format_version": _format_version(item)}
    for key in ("color_scheme", "font_family"):
        if key in item:
            result[key] = _name(item[key], f"Konsole {key}")
    if ("font_family" in item) != ("font_size" in item):
        raise ValueError("Konsole font_family and font_size must be provided together")
    if "font_size" in item:
        result["font_size"] = _number(item["font_size"], "Konsole font size", 4, 96)
    if "bold_intense" in item:
        result["bold_intense"] = _boolean(item["bold_intense"], "Konsole bold_intense")
    if "line_spacing" in item:
        result["line_spacing"] = _integer(item["line_spacing"], "Konsole line spacing", 0, 10)
    if "cursor_shape" in item:
        result["cursor_shape"] = _choice(
            item["cursor_shape"], "Konsole cursor shape", {"block", "underline", "ibeam"}
        )
    return _require_visual(result, "Konsole")


def _validate_kitty(value: Any) -> dict[str, Any]:
    item = _object(value, "Kitty settings")
    allowed = {"format_version", *_KITTY_KEYS, "palette"}
    _strict(item, {"format_version"}, allowed, "Kitty settings")
    result: dict[str, Any] = {"format_version": _format_version(item)}
    if "font_family" in item:
        result["font_family"] = _name(item["font_family"], "Kitty font family")
    if "font_size" in item:
        result["font_size"] = _number(item["font_size"], "Kitty font size", 4, 96)
    for key in ("foreground", "background", "cursor"):
        if key in item:
            result[key] = _color(item[key], f"Kitty {key}")
    if "cursor_shape" in item:
        result["cursor_shape"] = _choice(
            item["cursor_shape"], "Kitty cursor shape", {"block", "beam", "underline"}
        )
    if "background_opacity" in item:
        result["background_opacity"] = _number(
            item["background_opacity"], "Kitty background opacity", 0, 1
        )
    if "palette" in item:
        palette = item["palette"]
        if not isinstance(palette, list) or len(palette) != 16:
            raise ValueError("Kitty palette must contain exactly 16 colors")
        result["palette"] = [_color(color, "Kitty palette color") for color in palette]
    return _require_visual(result, "Kitty")


def _validate_starship(value: Any) -> dict[str, Any]:
    item = _object(value, "Starship settings")
    allowed = {
        "format_version",
        "add_newline",
        "palette",
        "modules",
        "character_symbol",
        "character_color",
        "directory_color",
        "git_branch_color",
    }
    _strict(item, {"format_version"}, allowed, "Starship settings")
    result: dict[str, Any] = {"format_version": _format_version(item)}
    if "add_newline" in item:
        result["add_newline"] = _boolean(item["add_newline"], "Starship add_newline")
    if "palette" in item:
        palette = _object(item["palette"], "Starship palette")
        if not palette or len(palette) > 32:
            raise ValueError("Starship palette must contain 1 through 32 colors")
        normalized: dict[str, str] = {}
        for name, color in palette.items():
            if _PALETTE_NAME.fullmatch(name) is None:
                raise ValueError("Starship palette name contains unsupported characters")
            normalized[name] = _color(color, f"Starship palette {name}")
        result["palette"] = normalized
    if "modules" in item:
        modules = item["modules"]
        if (
            not isinstance(modules, list)
            or not modules
            or len(modules) > len(_SAFE_STARSHIP_MODULES)
            or not all(isinstance(module, str) for module in modules)
            or len(set(modules)) != len(modules)
            or any(module not in _SAFE_STARSHIP_MODULES for module in modules)
        ):
            raise ValueError("Starship modules contain an unsafe or unsupported module")
        result["modules"] = list(modules)
    if "character_symbol" in item:
        symbol = _plain(
            item["character_symbol"], "Starship character symbol", 8
        )
        if any(character in "[]()\\" for character in symbol):
            raise ValueError("Starship character symbol contains formatting markup")
        result["character_symbol"] = symbol
    for key in ("character_color", "directory_color", "git_branch_color"):
        if key in item:
            result[key] = _color(item[key], f"Starship {key}")
    if ("character_symbol" in item) != ("character_color" in item):
        raise ValueError(
            "Starship character_symbol and character_color must be provided together"
        )
    return _require_visual(result, "Starship")


def _validate_fastfetch(value: Any) -> dict[str, Any]:
    item = _object(value, "fastfetch settings")
    allowed = {
        "format_version",
        "logo",
        "separator",
        "key_color",
        "title_color",
        "output_color",
        "bright_color",
        "modules",
    }
    _strict(item, {"format_version"}, allowed, "fastfetch settings")
    result: dict[str, Any] = {"format_version": _format_version(item)}
    if "logo" in item:
        logo = _object(item["logo"], "fastfetch logo")
        _strict(logo, {"type", "source"}, {"type", "source"}, "fastfetch logo")
        result["logo"] = {
            "type": _choice(logo["type"], "fastfetch logo type", {"builtin", "small"}),
            "source": _name(logo["source"], "fastfetch built-in logo"),
        }
    if "separator" in item:
        result["separator"] = _plain(item["separator"], "fastfetch separator", 32)
    for key in ("key_color", "title_color", "output_color"):
        if key in item:
            result[key] = _name(item[key], f"fastfetch {key}")
    if "bright_color" in item:
        result["bright_color"] = _boolean(item["bright_color"], "fastfetch bright_color")
    if "modules" in item:
        modules = item["modules"]
        if (
            not isinstance(modules, list)
            or not modules
            or len(modules) > 32
            or not all(isinstance(module, str) for module in modules)
            or len(set(modules)) != len(modules)
            or any(module not in _SAFE_FASTFETCH_MODULES for module in modules)
        ):
            raise ValueError("fastfetch modules contain an unsafe or unsupported module")
        result["modules"] = list(modules)
    return _require_visual(result, "fastfetch")


def _parse_owned_konsole(raw: bytes) -> dict[str, Any]:
    sections = _parse_ini(raw.decode("utf-8"))
    allowed = {
        "General": {"Name", "Parent"},
        "Appearance": {"ColorScheme", "Font", "BoldIntense", "LineSpacing"},
        "Cursor Options": {"CursorShape"},
    }
    _refuse_unknown_ini(sections, allowed, "Konsole")
    general = sections.get("General", {})
    if general != {"Name": "Alchemy", "Parent": "FALLBACK/"}:
        raise ValueError("Konsole adapter owns only the Alchemy profile")
    settings, _ = _konsole_settings(sections)
    if settings is None:
        raise ValueError("Konsole profile has no supported visual settings")
    return settings


def _parse_owned_kitty(raw: bytes) -> dict[str, Any]:
    values = _parse_kitty(raw.decode("utf-8"))
    unknown = set(values) - ({*_KITTY_KEYS, *(f"color{i}" for i in range(16))})
    if unknown:
        raise ValueError("Kitty config contains settings outside the adapter allowlist")
    settings, _ = _kitty_settings(values)
    if settings is None:
        raise ValueError("Kitty config has no supported visual settings")
    return settings


def _parse_owned_starship(raw: bytes) -> dict[str, Any]:
    parsed = tomllib.loads(raw.decode("utf-8"))
    if set(parsed) - {
        "$schema",
        "add_newline",
        "palette",
        "palettes",
        "format",
        "character",
        "directory",
        "git_branch",
    }:
        raise ValueError("Starship config contains settings outside the adapter allowlist")
    palettes = parsed.get("palettes", {})
    if not isinstance(palettes, dict) or set(palettes) - {"alchemy"}:
        raise ValueError("Starship config contains an unmanaged palette")
    settings, ignored = _starship_settings(parsed)
    if settings is None or ignored:
        raise ValueError("Starship config is not fully owned by the adapter")
    return settings


def _parse_owned_fastfetch(raw: bytes) -> dict[str, Any]:
    parsed = _jsonc_object(raw)
    settings, ignored = _fastfetch_settings(parsed)
    if settings is None or ignored:
        raise ValueError("fastfetch config contains settings outside the adapter allowlist")
    return settings


def _extract_konsole(raw: bytes) -> tuple[dict[str, Any] | None, int]:
    sections = _parse_ini(raw.decode("utf-8"))
    settings, used = _konsole_settings(sections)
    total = sum(len(values) for values in sections.values())
    return settings, total - used


def _extract_kitty(raw: bytes) -> tuple[dict[str, Any] | None, int]:
    values = _parse_kitty(raw.decode("utf-8"))
    settings, used = _kitty_settings(values)
    return settings, len(values) - used


def _extract_starship(raw: bytes) -> tuple[dict[str, Any] | None, int]:
    parsed = tomllib.loads(raw.decode("utf-8"))
    return _starship_settings(parsed)


def _extract_fastfetch(raw: bytes) -> tuple[dict[str, Any] | None, int]:
    return _fastfetch_settings(_jsonc_object(raw))


def _konsole_settings(
    sections: dict[str, dict[str, str]],
) -> tuple[dict[str, Any] | None, int]:
    result: dict[str, Any] = {"format_version": 1}
    used = 0
    appearance = sections.get("Appearance", {})
    if "ColorScheme" in appearance:
        result["color_scheme"] = appearance["ColorScheme"]
        used += 1
    if "Font" in appearance:
        parts = appearance["Font"].split(",", 2)
        if len(parts) < 2:
            raise ValueError("Konsole font is malformed")
        result["font_family"] = parts[0]
        result["font_size"] = float(parts[1])
        used += 1
    if "BoldIntense" in appearance:
        result["bold_intense"] = _parse_bool(appearance["BoldIntense"])
        used += 1
    if "LineSpacing" in appearance:
        result["line_spacing"] = int(appearance["LineSpacing"])
        used += 1
    cursor = sections.get("Cursor Options", {})
    if "CursorShape" in cursor:
        result["cursor_shape"] = {"0": "block", "1": "underline", "2": "ibeam"}[
            cursor["CursorShape"]
        ]
        used += 1
    return (validate_app_settings("konsole", result), used) if used else (None, 0)


def _kitty_settings(values: dict[str, str]) -> tuple[dict[str, Any] | None, int]:
    result: dict[str, Any] = {"format_version": 1}
    used = 0
    for key in _KITTY_KEYS:
        if key not in values:
            continue
        raw = values[key]
        if key in {"font_size", "background_opacity"}:
            result[key] = float(raw)
        else:
            result[key] = raw
        used += 1
    palette_keys = [f"color{index}" for index in range(16)]
    present = [key for key in palette_keys if key in values]
    if present:
        if len(present) != 16:
            raise ValueError("Kitty palette must define all 16 ANSI colors")
        result["palette"] = [values[key] for key in palette_keys]
        used += 16
    return (validate_app_settings("kitty", result), used) if used else (None, 0)


def _starship_settings(parsed: dict[str, Any]) -> tuple[dict[str, Any] | None, int]:
    result: dict[str, Any] = {"format_version": 1}
    used: set[str] = set()
    if "add_newline" in parsed:
        result["add_newline"] = parsed["add_newline"]
        used.add("add_newline")
    selected = parsed.get("palette")
    palettes = parsed.get("palettes")
    if isinstance(selected, str) and isinstance(palettes, dict):
        colors = palettes.get(selected)
        if isinstance(colors, dict) and colors:
            result["palette"] = colors
            used.update({"palette", "palettes"})
    format_value = parsed.get("format")
    if isinstance(format_value, str):
        modules = re.findall(r"\$([A-Za-z_]+)", format_value)
        if (
            modules
            and "".join(f"${module}" for module in modules) == format_value
            and len(set(modules)) == len(modules)
            and set(modules) <= _SAFE_STARSHIP_MODULES
        ):
            result["modules"] = modules
            used.add("format")
    character = parsed.get("character")
    if isinstance(character, dict) and set(character) == {"success_symbol", "error_symbol"}:
        success = character["success_symbol"]
        error = character["error_symbol"]
        match = _STARSHIP_CHARACTER.fullmatch(success) if isinstance(success, str) else None
        if match is not None and error == success:
            result["character_symbol"] = match.group(1)
            result["character_color"] = match.group(2)
            used.add("character")
    for table, target in (
        ("directory", "directory_color"),
        ("git_branch", "git_branch_color"),
    ):
        value = parsed.get(table)
        if isinstance(value, dict) and set(value) == {"style"}:
            style = value["style"]
            if isinstance(style, str) and re.fullmatch(r"bold #[0-9A-Fa-f]{6}", style):
                result[target] = style.removeprefix("bold ")
                used.add(table)
    if parsed.get("$schema") == _STARSHIP_SCHEMA:
        used.add("$schema")
    ignored = len(set(parsed) - used)
    if len(result) == 1:
        return None, ignored
    return validate_app_settings("starship", result), ignored


def _fastfetch_settings(parsed: dict[str, Any]) -> tuple[dict[str, Any] | None, int]:
    result: dict[str, Any] = {"format_version": 1}
    used_top: set[str] = set()
    logo = parsed.get("logo")
    if (
        isinstance(logo, dict)
        and set(logo) <= {"type", "source"}
        and logo.get("type") in {"builtin", "small"}
        and isinstance(logo.get("source"), str)
    ):
        result["logo"] = logo
        used_top.add("logo")
    display = parsed.get("display")
    if isinstance(display, dict):
        used_display: set[str] = set()
        if "separator" in display:
            result["separator"] = display["separator"]
            used_display.add("separator")
        if "brightColor" in display:
            result["bright_color"] = display["brightColor"]
            used_display.add("brightColor")
        colors = display.get("color")
        if isinstance(colors, dict) and set(colors) <= {"keys", "title", "output"}:
            for source, target in (
                ("keys", "key_color"),
                ("title", "title_color"),
                ("output", "output_color"),
            ):
                if source in colors:
                    result[target] = colors[source]
            used_display.add("color")
        if set(display) == used_display:
            used_top.add("display")
    modules = parsed.get("modules")
    if isinstance(modules, list) and modules and all(
        isinstance(module, str) and module in _SAFE_FASTFETCH_MODULES for module in modules
    ):
        result["modules"] = modules
        used_top.add("modules")
    if "$schema" in parsed:
        used_top.add("$schema")
    ignored = len(set(parsed) - used_top)
    if isinstance(display, dict) and "display" not in used_top:
        ignored += 1
    if len(result) == 1:
        return None, ignored
    return validate_app_settings("fastfetch", result), ignored


def _render_konsole(settings: dict[str, Any]) -> bytes:
    lines = ["[Appearance]"]
    if "color_scheme" in settings:
        lines.append(f"ColorScheme={settings['color_scheme']}")
    if "font_family" in settings:
        lines.append(f"Font={settings['font_family']},{_number_text(settings['font_size'])}")
    if "bold_intense" in settings:
        lines.append(f"BoldIntense={_bool_text(settings['bold_intense'])}")
    if "line_spacing" in settings:
        lines.append(f"LineSpacing={settings['line_spacing']}")
    if "cursor_shape" in settings:
        cursor_shape = {"block": 0, "underline": 1, "ibeam": 2}[
            settings["cursor_shape"]
        ]
        lines.extend(
            [
                "",
                "[Cursor Options]",
                f"CursorShape={cursor_shape}",
            ]
        )
    lines.extend(["", "[General]", "Name=Alchemy", "Parent=FALLBACK/", ""])
    return "\n".join(lines).encode()


def _render_kitty(settings: dict[str, Any]) -> bytes:
    lines = ["# Managed by Alchemy's Kitty adapter (format 1)."]
    for key in _KITTY_KEYS:
        if key in settings:
            lines.append(f"{key} {_number_text(settings[key])}")
    for index, color in enumerate(settings.get("palette", [])):
        lines.append(f"color{index} {color}")
    return ("\n".join(lines) + "\n").encode()


def _render_starship(settings: dict[str, Any]) -> bytes:
    lines = [
        '# Managed by Alchemy\'s Starship adapter (format 1).',
        f'"$schema" = "{_STARSHIP_SCHEMA}"',
    ]
    if "add_newline" in settings:
        lines.append(f"add_newline = {_bool_text(settings['add_newline'])}")
    if "palette" in settings:
        lines.append('palette = "alchemy"')
    if "modules" in settings:
        module_format = "".join(f"${module}" for module in settings["modules"])
        lines.append(f'format = "{module_format}"')
    if "palette" in settings:
        lines.extend(["", "[palettes.alchemy]"])
        for name, color in sorted(settings["palette"].items()):
            lines.append(f'{name} = "{color}"')
    if "character_symbol" in settings:
        rendered = f"[{settings['character_symbol']}](bold {settings['character_color']})"
        quoted = json.dumps(rendered, ensure_ascii=False)
        lines.extend(
            ["", "[character]", f"success_symbol = {quoted}", f"error_symbol = {quoted}"]
        )
    for table, key in (
        ("directory", "directory_color"),
        ("git_branch", "git_branch_color"),
    ):
        if key in settings:
            lines.extend(["", f"[{table}]", f'style = "bold {settings[key]}"'])
    return ("\n".join(lines) + "\n").encode()


def _parse_ini(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if not section or section in sections:
                raise ValueError("Config contains a duplicate or invalid section")
            sections[section] = {}
            continue
        if section is None or "=" not in raw_line:
            raise ValueError("Config contains a malformed line")
        key, raw_value = raw_line.split("=", 1)
        key = key.strip()
        if not key or key in sections[section]:
            raise ValueError("Config contains a duplicate or invalid key")
        sections[section][key] = raw_value.strip()
    return sections


def _parse_kitty(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or parts[0] in values:
            raise ValueError("Kitty config contains a malformed or duplicate key")
        values[parts[0]] = parts[1].strip()
    return values


def _jsonc_object(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8")
    stripped = _strip_jsonc(text)
    try:
        value = json.loads(stripped, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError("fastfetch config must be valid JSONC") from exc
    return _object(value, "fastfetch config")


def _strip_jsonc(text: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
        elif char == "/" and following == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
        elif char == "/" and following == "*":
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("fastfetch config has an unterminated comment")
            output.append(" ")
            index = end + 2
        else:
            output.append(char)
            index += 1
    return _remove_trailing_commas("".join(output))


def _remove_trailing_commas(text: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        character = text[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
        if character == ",":
            following = index + 1
            while following < len(text) and text[following].isspace():
                following += 1
            if following < len(text) and text[following] in "}]":
                index += 1
                continue
        output.append(character)
        index += 1
    return "".join(output)


def _refuse_unknown_ini(
    sections: dict[str, dict[str, str]], allowed: dict[str, set[str]], context: str
) -> None:
    if set(sections) - set(allowed):
        raise ValueError(f"{context} config contains a non-visual section")
    if any(set(values) - allowed[name] for name, values in sections.items()):
        raise ValueError(f"{context} config contains settings outside the adapter allowlist")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be an object")
    return value


def _strict(
    value: dict[str, Any], required: set[str], allowed: set[str], context: str
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ValueError(f"{context} is missing: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{context} contains unsupported fields: {', '.join(unknown)}")


def _format_version(value: dict[str, Any]) -> int:
    if value.get("format_version") != 1 or isinstance(value.get("format_version"), bool):
        raise ValueError("Application adapter format_version must be 1")
    return 1


def _require_visual(value: dict[str, Any], context: str) -> dict[str, Any]:
    if len(value) == 1:
        raise ValueError(f"{context} settings must contain at least one visual field")
    return value


def _plain(value: Any, context: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{context} contains unsupported text")
    return value


def _name(value: Any, context: str) -> str:
    result = _plain(value, context, 128)
    if _NAME.fullmatch(result) is None:
        raise ValueError(f"{context} contains unsupported characters")
    return result


def _color(value: Any, context: str) -> str:
    if not isinstance(value, str) or _COLOR.fullmatch(value) is None:
        raise ValueError(f"{context} must be a #RRGGBB color")
    return value.lower()


def _number(value: Any, context: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{context} must be a number")
    converted = float(value)
    if not minimum <= converted <= maximum:
        raise ValueError(f"{context} must be from {minimum:g} through {maximum:g}")
    return converted


def _integer(value: Any, context: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{context} must be an integer from {minimum} through {maximum}")
    return value


def _boolean(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context} must be a boolean")
    return value


def _choice(value: Any, context: str, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{context} is unsupported")
    return value


def _parse_bool(value: str) -> bool:
    lowered = value.casefold()
    if lowered not in {"true", "false"}:
        raise ValueError("Config boolean is malformed")
    return lowered == "true"


def _bool_text(value: object) -> str:
    return "true" if value is True else "false"


def _number_text(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
