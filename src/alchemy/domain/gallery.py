from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from alchemy.domain.rice import canonical_json_bytes
from alchemy.domain.versioning import Version, VersionRange

ENTRY_SCHEMA_URI = (
    "https://raw.githubusercontent.com/youssof20/alchemy-rice/main/"
    "schemas/gallery-entry-v1.schema.json"
)
SNAPSHOT_SCHEMA_URI = (
    "https://raw.githubusercontent.com/youssof20/alchemy-rice/main/"
    "schemas/gallery-v1.schema.json"
)
ENTRY_MAX_BYTES = 256 * 1024
SNAPSHOT_MAX_BYTES = 16 * 1024 * 1024
OWNERSHIP_MAX_BYTES = 16 * 1024
REMOTE_RICE_MAX_BYTES = 1024 * 1024
REMOTE_IMAGE_MAX_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 5000

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+-]{0,191}$")
_COMPONENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,191}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SEMVER_IDENTIFIER = r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    rf"(?:-({_SEMVER_IDENTIFIER}(?:\.{_SEMVER_IDENTIFIER})*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_SPDX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-.+]{0,127}$")
_RELEASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_FORGE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_MUTABLE_RELEASES = frozenset({"main", "master", "head", "latest", "develop", "dev"})
_COMPONENTS = frozenset(
    {
        "application_style",
        "apps",
        "colors",
        "cursor",
        "effects",
        "fonts",
        "icons",
        "kwin",
        "panels",
        "plasma_theme",
        "wallpaper",
        "window_decoration",
    }
)
_TAGS = frozenset(
    {
        "colorful",
        "dark",
        "gaming",
        "laptop",
        "light",
        "minimal",
        "multi-monitor",
        "productivity",
        "retro",
        "tiling",
        "ultrawide",
    }
)
_SOURCE_TYPES = frozenset(
    {"distro_package", "github_release", "kde_store", "manual"}
)
_COMPONENT_TYPES = frozenset({"asset", "config", "executable"})
_SESSIONS = frozenset({"wayland", "x11"})
_BADGE_LABELS = {
    "config_only_rice": "Config-only rice",
    "official_repo_dependencies_only": "Official-repo dependencies only",
    "pinned_source": "Pinned source",
    "schema_valid": "Schema valid",
    "third_party_code_dependency": "Third-party code dependency",
}


@dataclass(frozen=True, slots=True)
class GalleryEntry:
    data: dict[str, Any]
    canonical_bytes: bytes
    sha256: str

    @property
    def identity(self) -> str:
        return f"{self.data['id']}@{self.data['version']}"


@dataclass(frozen=True, slots=True)
class GallerySnapshot:
    data: dict[str, Any]
    canonical_bytes: bytes
    sha256: str

    @property
    def entries(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                **item["entry"],
                "community": item["community"],
                "badges": item["badges"],
            }
            for item in self.data["entries"]
        )


def load_gallery_entry(path_value: str | Path) -> GalleryEntry:
    candidate = Path(path_value).expanduser().absolute()
    if candidate.is_symlink():
        raise ValueError("Gallery entry must be a regular, non-symlink file")
    path = candidate.resolve(strict=True)
    if not path.is_file():
        raise ValueError("Gallery entry must be a regular, non-symlink file")
    return parse_gallery_entry_bytes(_read_limited(path, ENTRY_MAX_BYTES, "Gallery entry"))


def parse_gallery_entry_bytes(raw: bytes) -> GalleryEntry:
    parsed = _parse_json(raw, "Gallery entry", ENTRY_MAX_BYTES)
    _validate_tree(parsed)
    data = _normalized(parsed)
    _validate_entry(data)
    canonical = canonical_json_bytes(data)
    return GalleryEntry(data, canonical, hashlib.sha256(canonical).hexdigest())


def load_gallery_snapshot(path_value: str | Path) -> GallerySnapshot:
    candidate = Path(path_value).expanduser().absolute()
    if candidate.is_symlink():
        raise ValueError("Gallery snapshot must be a regular, non-symlink file")
    path = candidate.resolve(strict=True)
    if not path.is_file():
        raise ValueError("Gallery snapshot must be a regular, non-symlink file")
    return parse_gallery_snapshot_bytes(
        _read_limited(path, SNAPSHOT_MAX_BYTES, "Gallery snapshot")
    )


def parse_gallery_snapshot_bytes(raw: bytes) -> GallerySnapshot:
    parsed = _parse_json(raw, "Gallery snapshot", SNAPSHOT_MAX_BYTES)
    _validate_tree(parsed)
    data = _normalized(parsed)
    _strict(
        data,
        {"$schema", "snapshot_version", "source_digest", "entries"},
        {"$schema", "snapshot_version", "source_digest", "entries"},
        "Gallery snapshot",
    )
    if data["$schema"] != SNAPSHOT_SCHEMA_URI or data["snapshot_version"] != 1:
        raise ValueError("Gallery snapshot schema or version is unsupported")
    _sha256(data["source_digest"], "Gallery snapshot source_digest")
    entries = data["entries"]
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ValueError(f"Gallery snapshot entries must contain at most {MAX_ENTRIES} items")
    identities: set[str] = set()
    previous: tuple[str, str] | None = None
    source_entries: list[dict[str, Any]] = []
    for index, item in enumerate(entries):
        snapshot_entry = _object(item, f"Gallery snapshot entry {index}")
        source_entry, community, badges = _split_snapshot_entry(snapshot_entry, index)
        _validate_entry(source_entry)
        identity = source_entry["id"]
        if identity in identities:
            raise ValueError(f"Gallery snapshot contains duplicate entry id: {identity}")
        identities.add(identity)
        current = (identity, source_entry["version"])
        if previous is not None and current < previous:
            raise ValueError("Gallery snapshot entries are not in deterministic order")
        previous = current
        _validate_community(community, f"Gallery snapshot entry {identity}")
        expected_badges = derive_badges(source_entry, community)
        if badges != expected_badges:
            raise ValueError(f"Gallery snapshot badges do not match entry data: {identity}")
        source_entries.append(source_entry)
    expected_digest = entries_digest(source_entries)
    if data["source_digest"] != expected_digest:
        raise ValueError("Gallery snapshot source digest does not match its entries")
    canonical = canonical_json_bytes(data)
    return GallerySnapshot(data, canonical, hashlib.sha256(canonical).hexdigest())


def build_gallery_snapshot(
    entries: list[GalleryEntry], metrics: dict[str, dict[str, Any]] | None = None
) -> GallerySnapshot:
    metrics = metrics or {}
    by_id: dict[str, GalleryEntry] = {}
    for entry in entries:
        identity = entry.data["id"]
        if identity in by_id:
            raise ValueError(f"Gallery source contains duplicate entry id: {identity}")
        by_id[identity] = entry
    unknown_metrics = sorted(set(metrics) - set(by_id))
    if unknown_metrics:
        raise ValueError(f"Gallery metrics reference unknown entries: {', '.join(unknown_metrics)}")
    source_entries = [by_id[key].data for key in sorted(by_id)]
    snapshot_entries: list[dict[str, Any]] = []
    for source_entry in source_entries:
        community = metrics.get(source_entry["id"], default_community())
        _validate_community(community, f"Gallery metrics for {source_entry['id']}")
        snapshot_entries.append(
            {
                "entry": source_entry,
                "community": community,
                "badges": derive_badges(source_entry, community),
            }
        )
    data = {
        "$schema": SNAPSHOT_SCHEMA_URI,
        "snapshot_version": 1,
        "source_digest": entries_digest(source_entries),
        "entries": snapshot_entries,
    }
    return parse_gallery_snapshot_bytes(canonical_json_bytes(data))


def parse_metrics_bytes(raw: bytes) -> dict[str, dict[str, Any]]:
    parsed = _parse_json(raw, "Gallery metrics", ENTRY_MAX_BYTES)
    _validate_tree(parsed)
    data = _normalized(parsed)
    _strict(data, {"metrics_version", "entries"}, {"metrics_version", "entries"}, "Metrics")
    if data["metrics_version"] != 1:
        raise ValueError("Gallery metrics version is unsupported")
    entries = _object(data["entries"], "Gallery metrics entries")
    if len(entries) > MAX_ENTRIES:
        raise ValueError(f"Gallery metrics may contain at most {MAX_ENTRIES} entries")
    result: dict[str, dict[str, Any]] = {}
    for identity, community in entries.items():
        _identifier(identity, "Gallery metrics entry id")
        value = _object(community, f"Gallery metrics for {identity}")
        _validate_community(value, f"Gallery metrics for {identity}")
        result[identity] = value
    return result


def entries_digest(entries: list[dict[str, Any]]) -> str:
    return hashlib.sha256(canonical_json_bytes(entries)).hexdigest()


def default_community() -> dict[str, Any]:
    return {
        "confirmed_reports": 0,
        "release_downloads": 0,
        "official_repo_dependencies_only": False,
        "known_broken": [],
    }


def derive_badges(entry: dict[str, Any], community: dict[str, Any]) -> list[dict[str, str]]:
    ids = ["schema_valid", "pinned_source", "config_only_rice"]
    dependencies = entry["dependencies"]
    if not dependencies or community["official_repo_dependencies_only"]:
        ids.append("official_repo_dependencies_only")
    if any(item["component_type"] == "executable" for item in dependencies):
        ids.append("third_party_code_dependency")
    badges = [{"id": badge_id, "label": _BADGE_LABELS[badge_id]} for badge_id in ids]
    for tested in entry["compatibility"]["tested"]:
        badges.append(
            {
                "id": "tested",
                "label": (
                    f"Tested on Plasma {tested['plasma']} / {tested['distro']} / "
                    f"{tested['session'].title()}"
                ),
            }
        )
    if community["confirmed_reports"]:
        count = community["confirmed_reports"]
        badges.append(
            {
                "id": "community_confirmed",
                "label": f"Community confirmed: {count} reports",
            }
        )
    for broken in community["known_broken"]:
        badges.append(
            {
                "id": "known_broken",
                "label": f"Known broken on Plasma {broken['plasma']}",
            }
        )
    return badges


def ownership_url(entry: GalleryEntry | dict[str, Any]) -> str:
    data = entry.data if isinstance(entry, GalleryEntry) else entry
    forge, owner, repository = source_coordinates(data["source"]["repo"])
    commit = data["source"]["commit"]
    if forge == "github":
        return (
            f"https://raw.githubusercontent.com/{owner}/{repository}/{commit}/"
            ".alchemy/manifest.json"
        )
    return (
        f"https://codeberg.org/{owner}/{repository}/raw/commit/{commit}/"
        ".alchemy/manifest.json"
    )


def validate_ownership_bytes(raw: bytes, entry: GalleryEntry) -> None:
    parsed = _parse_json(raw, "Ownership manifest", OWNERSHIP_MAX_BYTES)
    data = _normalized(parsed)
    _strict(data, {"entry_id", "challenge"}, {"entry_id", "challenge"}, "Ownership manifest")
    expected = entry.data["id"]
    if data["entry_id"] != expected or data["challenge"] != f"alchemy-gallery:{expected}":
        raise ValueError("Ownership manifest does not contain this entry's challenge")


def source_coordinates(repo_url: str) -> tuple[str, str, str]:
    parsed = urlsplit(repo_url)
    if parsed.scheme != "https" or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("Gallery source repo must be a plain HTTPS repository URL")
    parts = [unquote(part) for part in parsed.path.strip("/").split("/")]
    if len(parts) != 2 or any(_FORGE_SEGMENT.fullmatch(part) is None for part in parts):
        raise ValueError("Gallery source repo must identify one owner and repository")
    repository = parts[1].removesuffix(".git")
    if not repository:
        raise ValueError("Gallery source repository name is invalid")
    if parsed.hostname == "github.com":
        return "github", parts[0], repository
    if parsed.hostname == "codeberg.org":
        return "codeberg", parts[0], repository
    raise ValueError("Gallery v1 supports creator repositories on GitHub or Codeberg")


def resource_belongs_to_source(
    url: str, source: dict[str, Any], *, allow_raw: bool
) -> bool:
    forge, owner, repository = source_coordinates(source["repo"])
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return False
    parts = [unquote(part) for part in parsed.path.strip("/").split("/")]
    if any(not part or part in {".", ".."} or "/" in part or "\\" in part for part in parts):
        return False
    release_path = [owner, repository, "releases", "download", source["release"]]
    if parsed.hostname in {"github.com", "codeberg.org"}:
        expected_host = "github.com" if forge == "github" else "codeberg.org"
        if parsed.hostname == expected_host and parts[:5] == release_path and len(parts) == 6:
            return True
    if allow_raw and forge == "github" and parsed.hostname == "raw.githubusercontent.com":
        return parts[:3] == [owner, repository, source["commit"]] and len(parts) >= 4
    if allow_raw and forge == "codeberg" and parsed.hostname == "codeberg.org":
        raw_path = [owner, repository, "raw", "commit", source["commit"]]
        return parts[:5] == raw_path and len(parts) >= 6
    return False


def entry_matches_environment(
    entry: dict[str, Any], *, plasma: str | None, distro: str | None, session: str | None
) -> bool:
    compatibility = entry["compatibility"]
    if session is not None and session not in compatibility["session"]:
        return False
    distros = compatibility.get("distros")
    if distro is not None and distros and distro not in distros:
        return False
    if plasma is not None:
        try:
            if not VersionRange.parse(compatibility["plasma"]).matches(Version.parse(plasma)):
                return False
        except ValueError:
            return False
    return True


def _validate_entry(data: dict[str, Any]) -> None:
    required = {
        "$schema",
        "entry_version",
        "id",
        "name",
        "version",
        "summary",
        "author",
        "source",
        "rice",
        "compatibility",
        "components",
        "dependencies",
        "licenses",
        "screenshots",
        "tags",
        "published_at",
        "updated_at",
    }
    _strict(data, required, required, "Gallery entry")
    if data["$schema"] != ENTRY_SCHEMA_URI or data["entry_version"] != 1:
        raise ValueError("Gallery entry schema or version is unsupported")
    _identifier(data["id"], "Gallery entry id")
    _plain_text(data["name"], "Gallery entry name", 128)
    if not isinstance(data["version"], str) or _SEMVER.fullmatch(data["version"]) is None:
        raise ValueError("Gallery entry version must be a Semantic Version")
    _plain_text(data["summary"], "Gallery entry summary", 320)
    author = _object(data["author"], "Gallery entry author")
    _strict(author, {"name", "url"}, {"name", "url"}, "Gallery entry author")
    _plain_text(author["name"], "Gallery entry author name", 128)
    _https_url(author["url"], "Gallery entry author URL")
    source = _object(data["source"], "Gallery entry source")
    _strict(source, {"repo", "release", "commit"}, {"repo", "release", "commit"}, "Source")
    source_coordinates(_https_url(source["repo"], "Gallery entry source repo"))
    if (
        not isinstance(source["release"], str)
        or _RELEASE.fullmatch(source["release"]) is None
        or source["release"].lower() in _MUTABLE_RELEASES
    ):
        raise ValueError("Gallery entry source release must be an immutable release name")
    if not isinstance(source["commit"], str) or _COMMIT.fullmatch(source["commit"]) is None:
        raise ValueError("Gallery entry source commit must be a full lowercase commit hash")
    rice = _object(data["rice"], "Gallery rice artifact")
    _strict(rice, {"url", "sha256"}, {"url", "sha256"}, "Gallery rice artifact")
    _https_url(rice["url"], "Gallery rice URL")
    _sha256(rice["sha256"], "Gallery rice SHA-256")
    if not rice["url"].endswith(".rice") or not resource_belongs_to_source(
        rice["url"], source, allow_raw=False
    ):
        raise ValueError(
            "Gallery rice must be a .rice release asset owned by the source repository"
        )
    compatibility = _object(data["compatibility"], "Gallery compatibility")
    _validate_compatibility(compatibility)
    components = _string_list(data["components"], "Gallery components", _COMPONENTS, 12)
    if components != sorted(components):
        raise ValueError("Gallery components must be sorted")
    dependencies = data["dependencies"]
    if not isinstance(dependencies, list) or len(dependencies) > 256:
        raise ValueError("Gallery dependencies must be an array with at most 256 entries")
    dependency_ids: set[str] = set()
    dependency_order: list[str] = []
    for dependency in dependencies:
        item = _object(dependency, "Gallery dependency")
        _strict(
            item,
            {"id", "component_type", "source_type", "license"},
            {"id", "component_type", "source_type", "license"},
            "Gallery dependency",
        )
        identity = _identifier(item["id"], "Gallery dependency id")
        if identity in dependency_ids:
            raise ValueError("Gallery dependency ids must be unique")
        dependency_ids.add(identity)
        dependency_order.append(identity)
        if item["component_type"] not in _COMPONENT_TYPES:
            raise ValueError("Gallery dependency component_type is unsupported")
        if item["source_type"] not in _SOURCE_TYPES:
            raise ValueError("Gallery dependency source_type is unsupported")
        _spdx(item["license"], "Gallery dependency license")
    if dependency_order != sorted(dependency_order):
        raise ValueError("Gallery dependencies must be sorted by id")
    licenses = data["licenses"]
    if not isinstance(licenses, list) or len(licenses) > 256:
        raise ValueError("Gallery licenses must be an array with at most 256 entries")
    for license_data in licenses:
        _validate_license(_object(license_data, "Gallery license"))
    screenshots = data["screenshots"]
    if not isinstance(screenshots, list) or not 1 <= len(screenshots) <= 4:
        raise ValueError("Gallery screenshots must contain one through four images")
    screenshot_hashes: set[str] = set()
    for screenshot in screenshots:
        item = _object(screenshot, "Gallery screenshot")
        fields = {"url", "sha256", "alt", "license"}
        _strict(item, fields, fields, "Gallery screenshot")
        _https_url(item["url"], "Gallery screenshot URL")
        digest = _sha256(item["sha256"], "Gallery screenshot SHA-256")
        if digest in screenshot_hashes:
            raise ValueError("Gallery screenshot hashes must be unique")
        screenshot_hashes.add(digest)
        _plain_text(item["alt"], "Gallery screenshot alt text", 256)
        _spdx(item["license"], "Gallery screenshot license")
        if not resource_belongs_to_source(item["url"], source, allow_raw=True):
            raise ValueError(
                "Gallery screenshots must be immutable assets owned by the source repository"
            )
    tags = _string_list(data["tags"], "Gallery tags", _TAGS, 8, allow_empty=True)
    if tags != sorted(tags):
        raise ValueError("Gallery tags must be sorted")
    published = _iso_date(data["published_at"], "Gallery published_at")
    updated = _iso_date(data["updated_at"], "Gallery updated_at")
    if updated < published:
        raise ValueError("Gallery updated_at cannot be earlier than published_at")


def _validate_compatibility(data: dict[str, Any]) -> None:
    allowed = {"plasma", "session", "distros", "tested"}
    _strict(data, {"plasma", "session", "tested"}, allowed, "Gallery compatibility")
    if not isinstance(data["plasma"], str) or len(data["plasma"]) > 128:
        raise ValueError("Gallery Plasma compatibility range is invalid")
    VersionRange.parse(data["plasma"])
    _string_list(data["session"], "Gallery sessions", _SESSIONS, 2)
    if "distros" in data:
        _string_list(data["distros"], "Gallery distros", None, 32)
        for distro in data["distros"]:
            _component_identifier(distro, "Gallery distro")
    tested = data["tested"]
    if not isinstance(tested, list) or len(tested) > 64:
        raise ValueError("Gallery tested declarations must contain at most 64 entries")
    for declaration in tested:
        item = _object(declaration, "Gallery tested declaration")
        fields = {"distro", "plasma", "session"}
        _strict(item, fields, fields, "Gallery tested declaration")
        _component_identifier(item["distro"], "Gallery tested distro")
        Version.parse(item["plasma"])
        if item["session"] not in _SESSIONS:
            raise ValueError("Gallery tested session is unsupported")


def _validate_license(data: dict[str, Any]) -> None:
    _strict(data, {"id", "applies_to", "url"}, {"id", "applies_to", "url"}, "Gallery license")
    _spdx(data["id"], "Gallery license id")
    _string_list(data["applies_to"], "Gallery license applies_to", None, 256)
    for identity in data["applies_to"]:
        _identifier(identity, "Gallery license applies_to item")
    _https_url(data["url"], "Gallery license URL")


def _validate_community(data: dict[str, Any], context: str) -> None:
    fields = {
        "confirmed_reports",
        "release_downloads",
        "official_repo_dependencies_only",
        "known_broken",
    }
    _strict(data, fields, fields, context)
    _bounded_integer(data["confirmed_reports"], f"{context} confirmed_reports", 0, 2**63 - 1)
    _bounded_integer(data["release_downloads"], f"{context} release_downloads", 0, 2**63 - 1)
    if not isinstance(data["official_repo_dependencies_only"], bool):
        raise ValueError(f"{context} official_repo_dependencies_only must be boolean")
    broken = data["known_broken"]
    if not isinstance(broken, list) or len(broken) > 64:
        raise ValueError(f"{context} known_broken must contain at most 64 entries")
    broken_versions: set[str] = set()
    for item_value in broken:
        item = _object(item_value, f"{context} known_broken item")
        _strict(item, {"plasma", "reports"}, {"plasma", "reports"}, f"{context} known_broken item")
        Version.parse(item["plasma"])
        if item["plasma"] in broken_versions:
            raise ValueError(f"{context} known_broken Plasma versions must be unique")
        broken_versions.add(item["plasma"])
        _bounded_integer(item["reports"], f"{context} known_broken reports", 1, 2**31 - 1)


def _split_snapshot_entry(
    data: dict[str, Any], index: int
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    _strict(
        data,
        {"entry", "community", "badges"},
        {"entry", "community", "badges"},
        f"Gallery snapshot entry {index}",
    )
    source = _object(data["entry"], f"Gallery snapshot entry {index} source")
    community = _object(data["community"], f"Gallery snapshot entry {index} community")
    badges_value = data["badges"]
    if not isinstance(badges_value, list) or len(badges_value) > 256:
        raise ValueError(f"Gallery snapshot entry {index} badges are invalid")
    badges: list[dict[str, str]] = []
    for value in badges_value:
        item = _object(value, f"Gallery snapshot entry {index} badge")
        _strict(item, {"id", "label"}, {"id", "label"}, "Gallery badge")
        _component_identifier(item["id"], "Gallery badge id")
        _plain_text(item["label"], "Gallery badge label", 256)
        badges.append(item)
    return source, community, badges


def _parse_json(raw: bytes, context: str, maximum: int) -> Any:
    if len(raw) > maximum:
        raise ValueError(f"{context} exceeds its {maximum // 1024} KiB input limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{context} must be UTF-8 JSON") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{context} is not valid JSON") from exc


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is not allowed: {value}")


def _validate_tree(value: Any) -> None:
    nodes = 0
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > 100_000:
            raise ValueError("Gallery JSON exceeds the node limit")
        if depth > 32:
            raise ValueError("Gallery JSON exceeds the nesting limit")
        if isinstance(current, dict):
            if len(current) > 10_000:
                raise ValueError("Gallery JSON object exceeds the member limit")
            for key, child in current.items():
                if not isinstance(key, str) or len(key) > 256:
                    raise ValueError("Gallery JSON object key is invalid")
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            if len(current) > 10_000:
                raise ValueError("Gallery JSON array exceeds the item limit")
            stack.extend((child, depth + 1) for child in current)
        elif isinstance(current, str) and len(current) > 4096:
            raise ValueError("Gallery JSON string exceeds the length limit")
        elif isinstance(current, int) and len(str(abs(current))) > 100:
            raise ValueError("Gallery JSON integer exceeds the length limit")


def _normalized(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Gallery document root must be an object")
    normalized = json.loads(canonical_json_bytes(value))
    if not isinstance(normalized, dict):
        raise ValueError("Gallery document root must be an object")
    return normalized


def _read_limited(path: Path, maximum: int, context: str) -> bytes:
    if path.stat().st_size > maximum:
        raise ValueError(f"{context} exceeds its {maximum // 1024} KiB input limit")
    with path.open("rb") as stream:
        return stream.read(maximum + 1)


def _strict(data: dict[str, Any], required: set[str], allowed: set[str], context: str) -> None:
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"{context} is missing required fields: {', '.join(missing)}")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unknown fields: {', '.join(unknown)}")


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _plain_text(value: Any, context: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(unicodedata.category(character).startswith("C") for character in value)
        or "<" in value
        or ">" in value
    ):
        raise ValueError(f"{context} must be bounded plain text")
    return value


def _https_url(value: Any, context: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or any(character.isspace() for character in value)
    ):
        raise ValueError(f"{context} must be an HTTPS URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError(f"{context} must be an HTTPS URL without credentials or fragments")
    return value


def _identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{context} contains unsupported characters")
    return value


def _component_identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or _COMPONENT_ID.fullmatch(value) is None:
        raise ValueError(f"{context} contains unsupported characters")
    return value


def _sha256(value: Any, context: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{context} must be 64 lowercase hexadecimal characters")
    return value


def _spdx(value: Any, context: str) -> str:
    if not isinstance(value, str) or _SPDX.fullmatch(value) is None:
        raise ValueError(f"{context} must be an SPDX license identifier")
    return value


def _string_list(
    value: Any,
    context: str,
    allowed: frozenset[str] | None,
    maximum: int,
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum or (not value and not allow_empty):
        raise ValueError(f"{context} must be an array with at most {maximum} entries")
    if not all(isinstance(item, str) for item in value) or len(set(value)) != len(value):
        raise ValueError(f"{context} must contain unique strings")
    if allowed is not None and any(item not in allowed for item in value):
        raise ValueError(f"{context} contains an unsupported value")
    return value


def _iso_date(value: Any, context: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError(f"{context} must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{context} must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{context} must use YYYY-MM-DD")
    return parsed


def _bounded_integer(value: Any, context: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{context} must be an integer from {minimum} through {maximum}")
    return int(value)
