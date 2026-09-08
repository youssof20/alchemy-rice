from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from alchemy.domain.versioning import Version, VersionRange

DATABASE_MAX_BYTES = 256 * 1024
COMPATIBILITY_STATUSES = frozenset(
    {
        "confirmed_working",
        "confirmed_broken",
        "unknown",
        "upstream_unsupported",
        "user_report_only",
    }
)
PACKAGE_PROVIDERS = frozenset({"pacman", "aur", "dnf", "apt", "zypper"})
REPOSITORY_CLASSES = frozenset({"official", "community"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")


@dataclass(frozen=True, slots=True)
class CompatibilityEntry:
    capability: str
    plasma: str
    status: str
    evidence: str
    checked_on: str

    def to_dict(self) -> dict[str, str]:
        return {
            "capability": self.capability,
            "plasma": self.plasma,
            "status": self.status,
            "evidence": self.evidence,
            "checked_on": self.checked_on,
        }


@dataclass(frozen=True, slots=True)
class PlasmaEntry:
    plasma: str
    status: str
    evidence: str
    checked_on: str

    def to_dict(self) -> dict[str, str]:
        return {
            "plasma": self.plasma,
            "status": self.status,
            "evidence": self.evidence,
            "checked_on": self.checked_on,
        }


@dataclass(frozen=True, slots=True)
class PackageMapping:
    capability: str
    distro: str
    provider: str
    package: str
    repository: str
    source_url: str
    status: str
    checked_on: str


@dataclass(frozen=True, slots=True)
class CompatibilityDatabase:
    plasma_entries: tuple[PlasmaEntry, ...]
    component_entries: tuple[CompatibilityEntry, ...]
    package_mappings: tuple[PackageMapping, ...]

    @classmethod
    def load(cls, root: Path) -> CompatibilityDatabase:
        plasma = _load_document(root / "plasma.json")
        components = _load_document(root / "components.json")
        packages = _load_document(root / "distro-packages.json")
        return cls(
            tuple(_plasma_entry(value) for value in plasma),
            tuple(_component_entry(value) for value in components),
            tuple(_package_mapping(value) for value in packages),
        )

    def plasma_status(self, plasma_version: str | None) -> str:
        return _most_conservative(
            [item.status for item in self.plasma_evidence(plasma_version)]
        )

    def plasma_evidence(self, plasma_version: str | None) -> tuple[PlasmaEntry, ...]:
        if plasma_version is None:
            return ()
        version = Version.parse(plasma_version)
        return tuple(
            item
            for item in self.plasma_entries
            if VersionRange.parse(item.plasma).matches(version)
        )

    def component_status(self, capability: str, plasma_version: str | None) -> str:
        return _most_conservative(
            [item.status for item in self.component_evidence(capability, plasma_version)]
        )

    def component_evidence(
        self, capability: str, plasma_version: str | None
    ) -> tuple[CompatibilityEntry, ...]:
        if plasma_version is None:
            return ()
        version = Version.parse(plasma_version)
        return tuple(
            item
            for item in self.component_entries
            if item.capability == capability and VersionRange.parse(item.plasma).matches(version)
        )

    def package_mapping(self, capability: str, distro: str | None) -> PackageMapping | None:
        matches = [
            item
            for item in self.package_mappings
            if item.capability == capability and item.distro == distro
        ]
        if len(matches) > 1:
            raise ValueError(
                f"Compatibility database has duplicate package mappings for {capability}"
            )
        return matches[0] if matches else None


def _load_document(path: Path) -> list[Any]:
    if not path.is_file():
        raise ValueError(f"Compatibility database file is missing: {path.name}")
    if path.stat().st_size > DATABASE_MAX_BYTES:
        raise ValueError(f"Compatibility database file exceeds 256 KiB: {path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Compatibility database file is invalid: {path.name}") from exc
    root = _object(payload, path.name)
    _exact_fields(root, {"format_version", "entries"}, path.name)
    if root["format_version"] != 1 or not isinstance(root["entries"], list):
        raise ValueError(f"Compatibility database file has unsupported format: {path.name}")
    if len(root["entries"]) > 1024:
        raise ValueError(f"Compatibility database file has too many entries: {path.name}")
    return root["entries"]


def _plasma_entry(value: Any) -> PlasmaEntry:
    item = _object(value, "Plasma compatibility entry")
    fields = {"plasma", "status", "evidence", "checked_on"}
    _exact_fields(item, fields, "Plasma compatibility entry")
    _common_entry(item)
    return PlasmaEntry(item["plasma"], item["status"], item["evidence"], item["checked_on"])


def _component_entry(value: Any) -> CompatibilityEntry:
    item = _object(value, "Component compatibility entry")
    fields = {"capability", "plasma", "status", "evidence", "checked_on"}
    _exact_fields(item, fields, "Component compatibility entry")
    _identifier(item["capability"], "Component capability")
    _common_entry(item)
    return CompatibilityEntry(
        item["capability"],
        item["plasma"],
        item["status"],
        item["evidence"],
        item["checked_on"],
    )


def _package_mapping(value: Any) -> PackageMapping:
    item = _object(value, "Distro package mapping")
    fields = {
        "capability",
        "distro",
        "provider",
        "package",
        "repository",
        "source_url",
        "status",
        "checked_on",
    }
    _exact_fields(item, fields, "Distro package mapping")
    for key in ("capability", "distro", "package"):
        _identifier(item[key], f"Distro package {key}")
    if not isinstance(item["provider"], str) or item["provider"] not in PACKAGE_PROVIDERS:
        raise ValueError("Distro package provider is unsupported")
    if (
        not isinstance(item["repository"], str)
        or item["repository"] not in REPOSITORY_CLASSES
    ):
        raise ValueError("Distro package repository class is unsupported")
    if item["provider"] == "aur" and item["repository"] != "community":
        raise ValueError("AUR mappings must be classified as community repositories")
    if not isinstance(item["status"], str) or item["status"] not in COMPATIBILITY_STATUSES:
        raise ValueError("Distro package status is unsupported")
    _https_url(item["source_url"], "Distro package source URL")
    _date(item["checked_on"])
    return PackageMapping(
        item["capability"],
        item["distro"],
        item["provider"],
        item["package"],
        item["repository"],
        item["source_url"],
        item["status"],
        item["checked_on"],
    )


def _common_entry(item: dict[str, Any]) -> None:
    if not isinstance(item["plasma"], str):
        raise ValueError("Compatibility plasma range must be a string")
    VersionRange.parse(item["plasma"])
    if not isinstance(item["status"], str) or item["status"] not in COMPATIBILITY_STATUSES:
        raise ValueError("Compatibility status is unsupported")
    if not isinstance(item["evidence"], str) or not 1 <= len(item["evidence"]) <= 512:
        raise ValueError("Compatibility evidence is invalid")
    _date(item["checked_on"])


def _most_conservative(statuses: list[str]) -> str:
    priority = {
        "upstream_unsupported": 5,
        "confirmed_broken": 4,
        "unknown": 3,
        "user_report_only": 2,
        "confirmed_working": 1,
    }
    return max(statuses, key=priority.__getitem__) if statuses else "unknown"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate compatibility database key: {key}")
        result[key] = value
    return result


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _exact_fields(value: dict[str, Any], fields: set[str], context: str) -> None:
    if set(value) != fields:
        raise ValueError(f"{context} has missing or unknown fields")


def _identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{context} contains unsupported characters")
    return value


def _https_url(value: Any, context: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{context} must be an HTTPS URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.fragment:
        raise ValueError(f"{context} must be an HTTPS URL without credentials or fragments")
    return value


def _date(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Compatibility checked_on must use YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Compatibility checked_on must use YYYY-MM-DD") from exc
    return value
