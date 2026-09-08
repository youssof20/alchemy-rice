from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from alchemy.domain.rice import SCHEMA_URI, canonical_json_bytes, parse_rice_bytes
from alchemy.domain.sanitizer import SanitizationContext, scan_publication

MAX_REPOSITORY_FILES = 10_000
MAX_ANALYZED_FILE_BYTES = 1024 * 1024
MAX_ANALYZED_TOTAL_BYTES = 8 * 1024 * 1024
MAX_DEPENDENCY_CANDIDATES = 256

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_FORGE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._+:-]{0,191}$")
_VISUAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. +()_-]{0,191}$")
_COMPONENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,191}$")
_SCRIPT_NAMES = frozenset(
    {
        "bootstrap",
        "install",
        "installer",
        "setup",
        "uninstall",
        "update",
    }
)
_SCRIPT_SUFFIXES = frozenset({".bash", ".fish", ".nu", ".ps1", ".sh", ".zsh"})
_WALLPAPER_SUFFIXES = frozenset({".avif", ".jpeg", ".jpg", ".png", ".webp"})
_TEXT_SUFFIXES = frozenset(
    {
        "",
        ".bash",
        ".cfg",
        ".cnf",
        ".colors",
        ".conf",
        ".fish",
        ".ini",
        ".json",
        ".jsonc",
        ".kvconfig",
        ".list",
        ".md",
        ".nu",
        ".profile",
        ".ps1",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
        ".zsh",
    }
)
_SENSITIVE_BASENAMES = frozenset(
    {
        ".env",
        ".netrc",
        "credentials",
        "id_dsa",
        "id_ed25519",
        "id_ecdsa",
        "id_rsa",
        "known_hosts",
    }
)
_DEFERRED_CONFIGS: tuple[tuple[str, str], ...] = (
    ("kitty.conf", "Kitty configuration"),
    ("alacritty.toml", "Alacritty configuration"),
    ("alacritty.yml", "Alacritty configuration"),
    ("alacritty.yaml", "Alacritty configuration"),
    ("starship.toml", "Starship configuration"),
    ("fastfetch/config.jsonc", "fastfetch configuration"),
    ("fastfetch/config.json", "fastfetch configuration"),
    ("ghostty/config", "Ghostty configuration"),
)
_KCONFIG_MAPPINGS: dict[str, dict[tuple[str, str], tuple[str, str, str]]] = {
    "kdeglobals": {
        ("General", "ColorScheme"): ("colors", "scheme", "visual"),
        ("General", "font"): ("fonts", "general", "font"),
        ("General", "fixed"): ("fonts", "fixed", "font"),
        ("General", "smallestReadableFont"): ("fonts", "small", "font"),
        ("General", "toolBarFont"): ("fonts", "toolbar", "font"),
        ("General", "menuFont"): ("fonts", "menu", "font"),
        ("WM", "activeFont"): ("fonts", "window_title", "font"),
        ("Icons", "Theme"): ("icons", "theme", "visual"),
        ("KDE", "widgetStyle"): ("application_style", "theme", "visual"),
    },
    "kcminputrc": {
        ("Mouse", "cursorTheme"): ("cursor", "theme", "visual"),
        ("Mouse", "cursorSize"): ("cursor", "size", "integer"),
    },
    "plasmarc": {("Theme", "name"): ("plasma_theme", "theme", "visual")},
    "kwinrc": {
        ("org.kde.kdecoration2", "theme"): (
            "window_decoration",
            "theme",
            "visual",
        ),
        ("org.kde.kdecoration2", "library"): (
            "window_decoration",
            "plugin",
            "component_id",
        ),
        ("org.kde.kdecoration2", "BorderSize"): (
            "window_decoration",
            "border_size",
            "visual",
        ),
        ("org.kde.kdecoration2", "BorderSizeAuto"): (
            "window_decoration",
            "border_auto",
            "boolean",
        ),
        ("Windows", "Placement"): ("kwin", "placement", "component_id"),
        ("Windows", "BorderlessMaximizedWindows"): (
            "kwin",
            "borderless_maximized",
            "boolean",
        ),
    },
}


@dataclass(frozen=True, slots=True)
class RepositoryDocument:
    path: str
    mode: str
    object_type: str
    size: int | None
    data: bytes | None = None
    omitted_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ImportFinding:
    code: str
    path: str
    detail: str
    blocking: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RecognizedFile:
    path: str
    kind: str
    mapped_components: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "mapped_components": list(self.mapped_components),
        }


@dataclass(frozen=True, slots=True)
class UnsupportedFile:
    path: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RepositoryImportResult:
    repository: str
    commit: str
    manifest: dict[str, Any]
    recognized: tuple[RecognizedFile, ...]
    unsupported: tuple[UnsupportedFile, ...]
    findings: tuple[ImportFinding, ...]
    dependency_candidates: tuple[str, ...]
    manifest_safe: bool

    @property
    def export_ready(self) -> bool:
        return self.manifest_safe and bool(self.manifest["components"]) and not any(
            finding.blocking for finding in self.findings
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "commit": self.commit,
            "export_ready": self.export_ready,
            "recognized": [
                {
                    **item.to_dict(),
                    "source_url": repository_file_url(
                        self.repository, self.commit, item.path
                    ),
                }
                for item in self.recognized
            ],
            "unsupported": [
                {
                    **item.to_dict(),
                    "source_url": repository_file_url(
                        self.repository, self.commit, item.path
                    ),
                }
                for item in self.unsupported
            ],
            "findings": [item.to_dict() for item in self.findings],
            "dependency_candidates": list(self.dependency_candidates),
            "manifest": self.manifest if self.manifest_safe else None,
            "applied": False,
            "executed_repository_code": False,
        }


def validate_repository_source(url: str, commit: str) -> tuple[str, str, str]:
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("Repository import requires a full lowercase Git SHA-1")
    if not isinstance(url, str) or len(url) > 2048 or any(character.isspace() for character in url):
        raise ValueError("Repository import requires a public HTTPS Git URL")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() not in {"github.com", "codeberg.org"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.endswith("/")
    ):
        raise ValueError("Repository import requires a plain public HTTPS Git URL")
    parts = [unquote(part) for part in parsed.path.strip("/").split("/")]
    if len(parts) != 2 or any(_FORGE_SEGMENT.fullmatch(part) is None for part in parts):
        raise ValueError("Repository URL must identify one owner and repository")
    repository = parts[1].removesuffix(".git")
    if not repository:
        raise ValueError("Repository URL has an invalid repository name")
    if parsed.hostname not in {"github.com", "codeberg.org"}:
        raise ValueError("Repository import v1 supports public GitHub or Codeberg repositories")
    return parsed.hostname, parts[0], repository


def should_read_repository_blob(path: str) -> bool:
    """Return whether a regular blob can enter the bounded UTF-8 recognizer path."""
    pure = PurePosixPath(path.casefold())
    return (
        pure.name not in _SENSITIVE_BASENAMES
        and pure.suffix not in _WALLPAPER_SUFFIXES
        and _script_kind(path) is None
        and pure.suffix in _TEXT_SUFFIXES
    )


def repository_file_url(repository_url: str, commit: str, path: str) -> str | None:
    if path.startswith("<") or not _safe_repository_path(path):
        return None
    host, owner, repository = validate_repository_source(repository_url, commit)
    encoded_path = quote(path, safe="/")
    if host == "github.com":
        return f"https://github.com/{owner}/{repository}/blob/{commit}/{encoded_path}"
    return f"https://codeberg.org/{owner}/{repository}/src/commit/{commit}/{encoded_path}"


def analyze_repository(
    documents: tuple[RepositoryDocument, ...],
    metadata: dict[str, Any],
    *,
    repository_url: str,
    commit: str,
    sanitizer_context: SanitizationContext,
) -> RepositoryImportResult:
    validate_repository_source(repository_url, commit)
    _validate_metadata_binding(metadata, repository_url, commit)
    if len(documents) > MAX_REPOSITORY_FILES:
        raise ValueError(f"Repository contains more than {MAX_REPOSITORY_FILES} entries")

    components: dict[str, dict[str, Any]] = {}
    component_sources: dict[tuple[str, str], tuple[Any, str]] = {}
    recognized: list[RecognizedFile] = []
    unsupported: list[UnsupportedFile] = []
    findings: list[ImportFinding] = []
    dependency_candidates: list[str] = []

    for document in documents:
        display_path, path_findings = _safe_display_path(
            document.path, sanitizer_context
        )
        findings.extend(path_findings)
        if not _safe_repository_path(document.path):
            unsupported.append(UnsupportedFile(display_path, "unsafe repository path"))
            findings.append(
                ImportFinding(
                    "unsafe_repository_path",
                    display_path,
                    "The entry path is absolute, traversing, or not portable",
                    True,
                )
            )
            continue
        if document.object_type == "commit" or document.mode == "160000":
            recognized.append(RecognizedFile(display_path, "git_submodule"))
            findings.append(
                ImportFinding(
                    "submodule_not_followed",
                    display_path,
                    "Git submodules are listed but never fetched or analyzed",
                )
            )
            continue
        if document.mode == "120000":
            recognized.append(RecognizedFile(display_path, "symbolic_link"))
            findings.append(
                ImportFinding(
                    "symlink_not_followed",
                    display_path,
                    "Symbolic links are listed but never materialized or followed",
                )
            )
            continue
        if document.object_type != "blob" or document.mode not in {"100644", "100755"}:
            unsupported.append(UnsupportedFile(display_path, "unsupported Git object type"))
            continue
        if document.mode == "100755":
            script_kind = _script_kind(document.path)
            recognized.append(
                RecognizedFile(display_path, script_kind or "executable_file")
            )
            findings.append(
                ImportFinding(
                    "executable_not_analyzed",
                    display_path,
                    "Executable repository files are never run or trusted as configuration",
                )
            )
            continue
        basename = PurePosixPath(document.path).name
        lower_path = document.path.casefold()
        if basename.casefold() in _SENSITIVE_BASENAMES:
            findings.append(
                ImportFinding(
                    "sensitive_file_omitted",
                    display_path,
                    "A credential or identity file name was detected and its content was not read",
                    True,
                )
            )
            unsupported.append(UnsupportedFile(display_path, "sensitive file omitted"))
            continue
        if PurePosixPath(lower_path).suffix in _WALLPAPER_SUFFIXES:
            recognized.append(RecognizedFile(display_path, "wallpaper_asset"))
            findings.append(
                ImportFinding(
                    "wallpaper_license_review_required",
                    display_path,
                    "Wallpaper bytes are not copied; source, hash, and redistribution "
                    "rights need review",
                    True,
                )
            )
            continue
        script_kind = _script_kind(document.path)
        if script_kind is not None:
            recognized.append(RecognizedFile(display_path, script_kind))
            findings.append(
                ImportFinding(
                    "installer_or_script_not_executed",
                    display_path,
                    "Script presence is reported from its filename without reading or "
                    "executing its content",
                )
            )
            continue
        if document.data is None:
            unsupported.append(
                UnsupportedFile(display_path, document.omitted_reason or "content not analyzed")
            )
            continue
        try:
            text = _decode_text(document.data)
        except ValueError:
            unsupported.append(UnsupportedFile(display_path, "binary or non-UTF-8 content"))
            continue
        content_report = scan_publication(text, sanitizer_context)
        severe = {"private_key", "token_like_value"}
        for item in content_report.findings:
            findings.append(
                ImportFinding(
                    f"content_{item.code}",
                    display_path,
                    item.detail,
                    item.code in severe,
                )
            )
        if any(item.code in severe for item in content_report.findings):
            unsupported.append(
                UnsupportedFile(display_path, "credential-shaped content quarantined")
            )
            continue

        kconfig_name = basename.casefold()
        if kconfig_name in _KCONFIG_MAPPINGS:
            mapped, unsupported_keys, parse_error = _recognize_kconfig(
                text,
                kconfig_name,
                display_path,
                components,
                component_sources,
                findings,
            )
            recognized.append(
                RecognizedFile(display_path, "kde_kconfig", tuple(sorted(mapped)))
            )
            if parse_error:
                findings.append(
                    ImportFinding(
                        "malformed_kconfig",
                        display_path,
                        "The recognized KConfig file could not be parsed conservatively",
                        True,
                    )
                )
            elif unsupported_keys:
                findings.append(
                    ImportFinding(
                        "unsupported_kconfig_keys",
                        display_path,
                        f"{unsupported_keys} non-allowlisted KConfig key(s) were ignored",
                    )
                )
            continue

        if PurePosixPath(lower_path).suffix == ".colors":
            scheme_mapped = _recognize_color_scheme(
                text, display_path, components, component_sources, findings
            )
            recognized.append(
                RecognizedFile(
                    display_path,
                    "kde_color_scheme",
                    ("colors",) if scheme_mapped else (),
                )
            )
            if scheme_mapped:
                findings.append(
                    ImportFinding(
                        "dependency_metadata_required",
                        display_path,
                        "The color scheme needs a separate pinned source and license before apply",
                        True,
                    )
                )
            continue

        if PurePosixPath(lower_path).suffix == ".kvconfig":
            recognized.append(RecognizedFile(display_path, "kvantum_configuration"))
            findings.append(
                ImportFinding(
                    "dependency_metadata_required",
                    display_path,
                    "Kvantum configuration was recognized but is not copied into the rice",
                    True,
                )
            )
            continue

        deferred = _deferred_kind(lower_path)
        konsole_file = basename.casefold().endswith(".colorscheme") or (
            basename.casefold().endswith(".profile")
            and basename.casefold() != ".profile"
        )
        if deferred is not None or konsole_file:
            recognized.append(
                RecognizedFile(display_path, deferred or "Konsole profile or color scheme")
            )
            findings.append(
                ImportFinding(
                    "reviewed_adapter_pending",
                    display_path,
                    "This visual configuration is recognized but awaits a reviewed "
                    "application adapter",
                )
            )
            continue

        if _dependency_manifest_name(basename.casefold()):
            candidates = _package_candidates(text)
            for candidate in candidates:
                if candidate not in dependency_candidates:
                    dependency_candidates.append(candidate)
            recognized.append(RecognizedFile(display_path, "dependency_manifest"))
            if candidates:
                findings.append(
                    ImportFinding(
                        "dependency_candidates_unresolved",
                        display_path,
                        "Package names were identified but need capability, provenance, "
                        "and license review",
                        True,
                    )
                )
            continue

        unsupported.append(UnsupportedFile(display_path, "no reviewed recognizer"))

    components = {name: values for name, values in components.items() if values}
    _add_component_provenance_findings(components, findings)
    if not components:
        findings.append(
            ImportFinding(
                "no_supported_visual_settings",
                "/",
                "No settings matched the current reviewed rice mappings",
                True,
            )
        )
    manifest = {
        "$schema": SCHEMA_URI,
        "schema_version": 2,
        **metadata,
        "components": components,
        "dependencies": [],
        "gallery": {"screenshots": [], "reddit_url": None, "tip_url": None},
    }
    parsed = parse_rice_bytes(canonical_json_bytes(manifest))
    normalized = parsed.data
    manifest_report = scan_publication(normalized, sanitizer_context)
    for item in manifest_report.findings:
        findings.append(
            ImportFinding(
                f"draft_{item.code}",
                item.path,
                item.detail,
                True,
            )
        )
    return RepositoryImportResult(
        repository_url,
        commit,
        normalized,
        tuple(recognized),
        tuple(unsupported),
        tuple(_unique_findings(findings)),
        tuple(dependency_candidates[:MAX_DEPENDENCY_CANDIDATES]),
        manifest_report.safe,
    )


def _validate_metadata_binding(
    metadata: dict[str, Any], repository_url: str, commit: str
) -> None:
    required = {"id", "name", "version", "author", "source", "compatibility", "licenses"}
    if set(metadata) != required:
        raise ValueError(
            "Repository metadata must contain exactly: " + ", ".join(sorted(required))
        )
    source = metadata.get("source")
    if not isinstance(source, dict):
        raise ValueError("Repository metadata source must be an object")
    if source.get("repo") != repository_url or source.get("commit") != commit:
        raise ValueError("Repository metadata source must match the requested URL and commit")


def _safe_repository_path(path: str) -> bool:
    if not path or "\\" in path or path.startswith("/") or "\x00" in path:
        return False
    pure = PurePosixPath(path)
    return not pure.is_absolute() and all(part not in {"", ".", ".."} for part in pure.parts)


def _safe_display_path(
    path: str, context: SanitizationContext
) -> tuple[str, list[ImportFinding]]:
    report = scan_publication(path, context)
    if report.safe:
        return path, []
    digest = hashlib.sha256(path.encode("utf-8", errors="replace")).hexdigest()[:12]
    display = f"<redacted-path:{digest}>"
    findings = [
        ImportFinding(f"path_{item.code}", display, item.detail, True)
        for item in report.findings
    ]
    return display, findings


def _decode_text(data: bytes) -> str:
    if b"\x00" in data:
        raise ValueError("binary")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("non-UTF-8") from exc
    if len(text) > MAX_ANALYZED_FILE_BYTES:
        raise ValueError("oversized")
    return text


def _script_kind(path: str) -> str | None:
    pure = PurePosixPath(path.casefold())
    if pure.suffix in _SCRIPT_SUFFIXES:
        return "installer_script" if pure.stem in _SCRIPT_NAMES else "script"
    if pure.name in _SCRIPT_NAMES:
        return "installer_script"
    return None


def _deferred_kind(path: str) -> str | None:
    for suffix, label in _DEFERRED_CONFIGS:
        if path.endswith(suffix.casefold()):
            return label
    return None


def _dependency_manifest_name(name: str) -> bool:
    return name in {
        "dependencies.txt",
        "packages",
        "packages.txt",
        "pkglist.txt",
    }


def _package_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or any(character.isspace() for character in stripped)
        ):
            continue
        if _PACKAGE.fullmatch(stripped) and stripped not in candidates:
            candidates.append(stripped)
        if len(candidates) >= MAX_DEPENDENCY_CANDIDATES:
            break
    return candidates


def _parse_ini(text: str) -> tuple[dict[tuple[str, str], str], bool]:
    values: dict[tuple[str, str], str] = {}
    section: str | None = None
    try:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if line.startswith("[") and line.endswith("]") and len(line) > 2:
                section = line[1:-1]
                continue
            if section is None or "=" not in raw_line:
                continue
            key, value = raw_line.split("=", 1)
            identity = (section, key.strip())
            if not identity[1] or identity in values:
                return {}, True
            values[identity] = value.strip()
    except (TypeError, ValueError):
        return {}, True
    return values, False


def _recognize_kconfig(
    text: str,
    name: str,
    path: str,
    components: dict[str, dict[str, Any]],
    sources: dict[tuple[str, str], tuple[Any, str]],
    findings: list[ImportFinding],
) -> tuple[set[str], int, bool]:
    values, failed = _parse_ini(text)
    if failed:
        return set(), 0, True
    mappings = _KCONFIG_MAPPINGS[name]
    mapped: set[str] = set()
    for identity, value in values.items():
        target = mappings.get(identity)
        if target is None:
            continue
        component, key, converter = target
        try:
            converted = _convert_value(value, converter)
        except ValueError:
            findings.append(
                ImportFinding(
                    "unsupported_setting_value",
                    path,
                    "A recognized visual setting had an unsupported value and was omitted",
                    True,
                )
            )
            continue
        _merge_component(components, sources, component, key, converted, path, findings)
        if component == "application_style" and key == "theme":
            engine_type = _style_engine(str(converted))
            _merge_component(
                components,
                sources,
                component,
                "style_engine",
                {
                    "type": engine_type,
                    "min_version": None,
                    "experimental": engine_type == "union",
                },
                path,
                findings,
            )
        mapped.add(component)
    return mapped, len(set(values) - set(mappings)), False


def _recognize_color_scheme(
    text: str,
    path: str,
    components: dict[str, dict[str, Any]],
    sources: dict[tuple[str, str], tuple[Any, str]],
    findings: list[ImportFinding],
) -> bool:
    values, failed = _parse_ini(text)
    name = values.get(("General", "Name")) if not failed else None
    if name is None:
        findings.append(
            ImportFinding(
                "malformed_color_scheme",
                path,
                "The color scheme lacked a unique General/Name value",
                True,
            )
        )
        return False
    try:
        converted = _convert_value(name, "visual")
    except ValueError:
        findings.append(
            ImportFinding(
                "unsupported_setting_value",
                path,
                "The color scheme name could not be represented safely",
                True,
            )
        )
        return False
    _merge_component(components, sources, "colors", "scheme", converted, path, findings)
    return True


def _convert_value(value: str, converter: str) -> str | int | bool:
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
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("control character")
    if converter == "font":
        if not 1 <= len(value) <= 512:
            raise ValueError("invalid font")
        return value
    matcher = _COMPONENT_ID if converter == "component_id" else _VISUAL
    if matcher.fullmatch(value) is None:
        raise ValueError("invalid visual identifier")
    return value


def _merge_component(
    components: dict[str, dict[str, Any]],
    sources: dict[tuple[str, str], tuple[Any, str]],
    component: str,
    key: str,
    value: Any,
    path: str,
    findings: list[ImportFinding],
) -> None:
    identity = (component, key)
    previous = sources.get(identity)
    if previous is not None and previous[0] != value:
        findings.append(
            ImportFinding(
                "conflicting_setting",
                path,
                f"Multiple repository files disagree about {component}.{key}",
                True,
            )
        )
        components.get(component, {}).pop(key, None)
        return
    if previous is None:
        sources[identity] = value, path
        components.setdefault(component, {})[key] = value


def _style_engine(value: str) -> str:
    normalized = re.sub(r"[\s_-]+", "", value.casefold())
    if normalized.startswith("breeze"):
        return "breeze"
    if normalized.startswith("kvantum"):
        return "kvantum"
    if normalized.startswith("union"):
        return "union"
    return "other"


def _add_component_provenance_findings(
    components: dict[str, dict[str, Any]], findings: list[ImportFinding]
) -> None:
    for component, key in (
        ("colors", "scheme"),
        ("icons", "theme"),
        ("cursor", "theme"),
        ("plasma_theme", "theme"),
        ("application_style", "theme"),
        ("window_decoration", "theme"),
    ):
        value = components.get(component, {}).get(key)
        if isinstance(value, str) and not _known_platform_component(value):
            findings.append(
                ImportFinding(
                    "component_provenance_unresolved",
                    "/components/" + component,
                    "A mapped component needs pinned package, source, and license metadata",
                    True,
                )
            )


def _known_platform_component(value: str) -> bool:
    normalized = re.sub(r"[\s_-]+", "", value.casefold())
    return (
        normalized == "default"
        or normalized.startswith("breeze")
        or value.casefold().startswith("org.kde.breeze")
    )


def _unique_findings(findings: list[ImportFinding]) -> list[ImportFinding]:
    result: list[ImportFinding] = []
    for finding in findings:
        if finding not in result:
            result.append(finding)
    return result
