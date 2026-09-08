from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from alchemy.domain.capabilities import CapabilityMatrix
from alchemy.domain.gallery import (
    MAX_ENTRIES,
    OWNERSHIP_MAX_BYTES,
    REMOTE_IMAGE_MAX_BYTES,
    REMOTE_RICE_MAX_BYTES,
    SNAPSHOT_MAX_BYTES,
    GalleryEntry,
    GallerySnapshot,
    build_gallery_snapshot,
    entry_matches_environment,
    load_gallery_entry,
    load_gallery_snapshot,
    ownership_url,
    parse_gallery_snapshot_bytes,
    parse_metrics_bytes,
    validate_ownership_bytes,
)
from alchemy.domain.rice import parse_rice_bytes
from alchemy.platform.atomic import write_bytes_atomic, write_json_atomic
from alchemy.platform.gallery_http import GalleryHttpClient, UrllibGalleryHttpClient
from alchemy.services.environment_probe import EnvironmentProbe

GALLERY_SNAPSHOT_URL = (
    "https://raw.githubusercontent.com/youssof20/alchemy-rice-index/main/gallery.json"
)
GALLERY_REPORT_URL = (
    "https://github.com/youssof20/alchemy-rice-index/issues/new"
)


class GalleryService:
    def __init__(
        self,
        *,
        data_root: Path | None = None,
        client: GalleryHttpClient | None = None,
        probe: EnvironmentProbe | None = None,
    ) -> None:
        self.data_root = data_root or _xdg_data_root() / "alchemy"
        self.client = client or UrllibGalleryHttpClient()
        self.probe = probe or EnvironmentProbe()

    @property
    def cache_path(self) -> Path:
        return self.data_root / "gallery" / "gallery.json"

    @property
    def cache_metadata_path(self) -> Path:
        return self.data_root / "gallery" / "cache.json"

    def validate_directory(
        self, directory_value: str, *, verify_remote: bool = False
    ) -> dict[str, Any]:
        candidate = Path(directory_value).expanduser().absolute()
        if candidate.is_symlink():
            raise ValueError("Gallery entries path must be a regular directory")
        directory = candidate.resolve(strict=True)
        if not directory.is_dir():
            raise ValueError("Gallery entries path must be a regular directory")
        entries = self._load_entry_directory(directory)
        verified = 0
        if verify_remote:
            for entry in entries:
                self._verify_remote(entry)
                verified += 1
        return {
            "valid": True,
            "entries": len(entries),
            "remote_verified": verified,
            "executed_contributor_code": False,
        }

    def build(
        self,
        directory_value: str,
        destination_value: str,
        *,
        metrics_path: str | None = None,
        check: bool = False,
    ) -> dict[str, Any]:
        candidate = Path(directory_value).expanduser().absolute()
        if candidate.is_symlink():
            raise ValueError("Gallery entries path must be a regular directory")
        directory = candidate.resolve(strict=True)
        if not directory.is_dir():
            raise ValueError("Gallery entries path must be a regular directory")
        entries = self._load_entry_directory(directory)
        metrics: dict[str, dict[str, Any]] = {}
        if metrics_path is not None:
            metrics_candidate = Path(metrics_path).expanduser().absolute()
            if metrics_candidate.is_symlink():
                raise ValueError("Gallery metrics must be a regular, non-symlink file")
            metrics_file = metrics_candidate.resolve(strict=True)
            if not metrics_file.is_file():
                raise ValueError("Gallery metrics must be a regular, non-symlink file")
            metrics = parse_metrics_bytes(metrics_file.read_bytes())
        snapshot = build_gallery_snapshot(entries, metrics)
        destination = Path(destination_value).expanduser().absolute()
        if destination.is_symlink():
            raise ValueError("Gallery snapshot destination cannot be a symlink")
        if check:
            if not destination.is_file() or destination.read_bytes() != snapshot.canonical_bytes:
                raise RuntimeError(
                    "Committed gallery snapshot is not the deterministic build output"
                )
            action = "checked"
        else:
            if not destination.parent.is_dir():
                raise ValueError("Gallery snapshot destination directory does not exist")
            write_bytes_atomic(destination, snapshot.canonical_bytes, overwrite=True)
            action = "built"
        return {
            "action": action,
            "entries": len(entries),
            "sha256": snapshot.sha256,
            "source_digest": snapshot.data["source_digest"],
            "path": str(destination),
        }

    def refresh(self) -> dict[str, Any]:
        etag: str | None = None
        if self.cache_metadata_path.is_file() and not self.cache_metadata_path.is_symlink():
            try:
                metadata = json.loads(self.cache_metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                metadata = {}
            if metadata.get("source_url") == GALLERY_SNAPSHOT_URL and isinstance(
                metadata.get("etag"), str
            ):
                etag = metadata["etag"]
        document = self.client.fetch(
            GALLERY_SNAPSHOT_URL, maximum=SNAPSHOT_MAX_BYTES, etag=etag
        )
        if document.status == 304:
            snapshot = load_gallery_snapshot(self.cache_path)
            return self._cache_result(snapshot, "not_modified")
        if document.status != 200:
            raise RuntimeError(f"Gallery request returned unexpected HTTP {document.status}")
        snapshot = parse_gallery_snapshot_bytes(document.body)
        write_bytes_atomic(self.cache_path, snapshot.canonical_bytes, overwrite=True)
        write_json_atomic(
            self.cache_metadata_path,
            {
                "source_url": GALLERY_SNAPSHOT_URL,
                "etag": document.etag,
                "fetched_at": datetime.now(UTC).isoformat(),
                "sha256": snapshot.sha256,
            },
        )
        return self._cache_result(snapshot, "refreshed")

    def cache_local(
        self, source_value: str, *, expected_sha256: str | None = None
    ) -> dict[str, Any]:
        snapshot = load_gallery_snapshot(source_value)
        if expected_sha256 is not None and snapshot.sha256 != expected_sha256.lower():
            raise ValueError(
                f"Gallery snapshot SHA-256 mismatch: expected {expected_sha256.lower()}, "
                f"observed {snapshot.sha256}"
            )
        write_bytes_atomic(self.cache_path, snapshot.canonical_bytes, overwrite=True)
        write_json_atomic(
            self.cache_metadata_path,
            {
                "source_url": None,
                "etag": None,
                "fetched_at": datetime.now(UTC).isoformat(),
                "sha256": snapshot.sha256,
            },
        )
        return self._cache_result(snapshot, "cached")

    def browse(
        self,
        *,
        query: str | None = None,
        tag: str | None = None,
        sort_by: str = "updated",
    ) -> dict[str, Any]:
        snapshot, cached = self._cached_snapshot()
        entries = list(snapshot.entries)
        if query:
            needle = query.casefold()
            entries = [
                item
                for item in entries
                if needle
                in " ".join(
                    [
                        item["name"],
                        item["summary"],
                        item["author"]["name"],
                        *item["tags"],
                    ]
                ).casefold()
            ]
        if tag:
            entries = [item for item in entries if tag in item["tags"]]
        allowed_sorts = {"new", "updated", "downloads", "confirmed", "compatible"}
        if sort_by not in allowed_sorts:
            raise ValueError(
                "Gallery sort must be new, updated, downloads, confirmed, or compatible"
            )
        capability = (
            self.probe.inspect().capabilities if sort_by == "compatible" else None
        )
        entries.sort(
            key=lambda item: _gallery_sort_key(item, sort_by, capability), reverse=True
        )
        return {
            "cached": cached,
            "snapshot_sha256": snapshot.sha256,
            "sort": sort_by,
            "entries": entries,
        }

    def show(self, entry_id: str) -> dict[str, Any]:
        snapshot, cached = self._cached_snapshot()
        for entry in snapshot.entries:
            if entry["id"] == entry_id:
                return {"cached": cached, "entry": entry}
        raise ValueError(f"Gallery entry is not present in the local cache: {entry_id}")

    def report(
        self,
        entry_id: str,
        *,
        result: str,
        failed_component: str | None = None,
        error_class: str | None = None,
    ) -> dict[str, Any]:
        entry = self.show(entry_id)["entry"]
        if result not in {"success", "failure"}:
            raise ValueError("Gallery report result must be success or failure")
        if result == "success" and (failed_component is not None or error_class is not None):
            raise ValueError("Successful reports cannot include failure fields")
        if result == "failure" and (failed_component is None or error_class is None):
            raise ValueError("Failure reports require failed_component and error_class")
        _safe_report_value(failed_component, "failed_component")
        _safe_report_value(error_class, "error_class")
        capability = self.probe.inspect().capabilities
        report = {
            "rice": f"{entry['id']}@{entry['version']}",
            "plasma": capability.plasma_version or "unknown",
            "distro": capability.distro or "unknown",
            "session": capability.session or "unknown",
            "result": result,
            "failed_component": failed_component,
            "error_class": error_class,
        }
        report_json = json.dumps(report, indent=2, sort_keys=True)
        title = f"[Rice report] {report['rice']}"
        query = urlencode(
            {
                "template": "rice-report.yml",
                "title": title,
                "report": report_json,
            }
        )
        url = f"{GALLERY_REPORT_URL}?{query}"
        return {"report": report, "github_url": url, "uploaded": False}

    def _load_entry_directory(self, directory: Path) -> list[GalleryEntry]:
        entries: list[GalleryEntry] = []
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            if path.suffix != ".json":
                continue
            if path.is_symlink() or not path.is_file() or path.parent != directory:
                raise ValueError(f"Gallery entry is not a regular direct child: {path.name}")
            entries.append(load_gallery_entry(path))
            if len(entries) > MAX_ENTRIES:
                raise ValueError(f"Gallery may contain at most {MAX_ENTRIES} entries")
        ids = [entry.data["id"] for entry in entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Gallery entry ids must be unique")
        return entries

    def _verify_remote(self, entry: GalleryEntry) -> None:
        ownership = self.client.fetch(
            ownership_url(entry), maximum=OWNERSHIP_MAX_BYTES
        )
        if ownership.status != 200:
            raise RuntimeError("Creator ownership manifest could not be fetched")
        validate_ownership_bytes(ownership.body, entry)

        rice_document = self.client.fetch(
            entry.data["rice"]["url"], maximum=REMOTE_RICE_MAX_BYTES
        )
        if rice_document.status != 200:
            raise RuntimeError("Rice release asset could not be fetched")
        observed = hashlib.sha256(rice_document.body).hexdigest()
        if observed != entry.data["rice"]["sha256"]:
            raise ValueError("Rice release asset SHA-256 does not match the gallery entry")
        rice = parse_rice_bytes(rice_document.body)
        self._compare_rice_projection(entry, rice.data)

        for screenshot in entry.data["screenshots"]:
            document = self.client.fetch(
                screenshot["url"], maximum=REMOTE_IMAGE_MAX_BYTES
            )
            if document.status != 200:
                raise RuntimeError("Gallery screenshot could not be fetched")
            if hashlib.sha256(document.body).hexdigest() != screenshot["sha256"]:
                raise ValueError("Gallery screenshot SHA-256 does not match its metadata")
            _validate_image_header(document.body)

    @staticmethod
    def _compare_rice_projection(entry: GalleryEntry, rice: dict[str, Any]) -> None:
        expected = entry.data
        comparisons = {
            "id": rice["id"],
            "name": rice["name"],
            "version": rice["version"],
            "author": rice["author"],
            "source": rice["source"],
            "compatibility": rice["compatibility"],
            "components": sorted(rice["components"]),
            "dependencies": sorted(
                [
                    {
                        "id": item["id"],
                        "component_type": item["component_type"],
                        "source_type": item["source"]["type"],
                        "license": item["license"],
                    }
                    for item in rice["dependencies"]
                ],
                key=lambda item: item["id"],
            ),
            "licenses": rice["licenses"],
            "screenshots": [
                {key: item[key] for key in ("url", "sha256", "alt")}
                for item in rice["gallery"]["screenshots"]
            ],
        }
        for key, value in comparisons.items():
            actual = expected[key]
            if key == "screenshots":
                actual = [
                    {field: item[field] for field in ("url", "sha256", "alt")}
                    for item in actual
                ]
            if actual != value:
                raise ValueError(f"Gallery {key} metadata does not match the pinned rice")

    def _cached_snapshot(self) -> tuple[GallerySnapshot, bool]:
        if self.cache_path.is_file() and not self.cache_path.is_symlink():
            return load_gallery_snapshot(self.cache_path), True
        return build_gallery_snapshot([]), False

    def _cache_result(self, snapshot: GallerySnapshot, action: str) -> dict[str, Any]:
        return {
            "action": action,
            "entries": len(snapshot.entries),
            "sha256": snapshot.sha256,
            "path": str(self.cache_path),
        }


def _validate_image_header(raw: bytes) -> None:
    width: int
    height: int
    if raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) >= 24:
        width = int.from_bytes(raw[16:20], "big")
        height = int.from_bytes(raw[20:24], "big")
    elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP" and len(raw) >= 25:
        chunk = raw[12:16]
        if chunk == b"VP8X":
            if len(raw) < 30:
                raise ValueError("Gallery WebP screenshot header is truncated")
            width = int.from_bytes(raw[24:27], "little") + 1
            height = int.from_bytes(raw[27:30], "little") + 1
        elif chunk == b"VP8 ":
            if len(raw) < 30 or raw[23:26] != b"\x9d\x01\x2a":
                raise ValueError("Gallery WebP screenshot header is invalid")
            width = int.from_bytes(raw[26:28], "little") & 0x3FFF
            height = int.from_bytes(raw[28:30], "little") & 0x3FFF
        elif chunk == b"VP8L" and raw[20] == 0x2F:
            bits = int.from_bytes(raw[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
        else:
            raise ValueError("Gallery WebP screenshot header is unsupported")
    elif raw.startswith(b"\xff\xd8"):
        width, height = _jpeg_dimensions(raw)
    else:
        raise ValueError("Gallery screenshots must be PNG, JPEG, or WebP images")
    if not 1 <= width <= 16_384 or not 1 <= height <= 16_384 or width * height > 64_000_000:
        raise ValueError("Gallery screenshot dimensions exceed the safety limit")


def _jpeg_dimensions(raw: bytes) -> tuple[int, int]:
    offset = 2
    while offset + 9 < len(raw):
        if raw[offset] != 0xFF:
            offset += 1
            continue
        marker = raw[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(raw):
            break
        length = int.from_bytes(raw[offset : offset + 2], "big")
        if length < 2 or offset + length > len(raw):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height = int.from_bytes(raw[offset + 3 : offset + 5], "big")
            width = int.from_bytes(raw[offset + 5 : offset + 7], "big")
            return width, height
        offset += length
    raise ValueError("Gallery JPEG screenshot has no valid dimensions")


def _safe_report_value(value: str | None, context: str) -> None:
    if value is None:
        return
    if not value or len(value) > 128 or any(
        not (character.isalnum() or character in "._-") for character in value
    ):
        raise ValueError(f"Gallery report {context} contains unsupported characters")


def _gallery_sort_key(
    item: dict[str, Any], sort_by: str, capability: CapabilityMatrix | None
) -> tuple[Any, ...]:
    if sort_by == "new":
        return item["published_at"], item["id"]
    if sort_by == "updated":
        return item["updated_at"], item["id"]
    if sort_by == "downloads":
        return (
            item["community"]["release_downloads"],
            item["updated_at"],
            item["id"],
        )
    if sort_by == "confirmed":
        return (
            item["community"]["confirmed_reports"],
            item["updated_at"],
            item["id"],
        )
    assert capability is not None
    return (
        entry_matches_environment(
            item,
            plasma=capability.plasma_version,
            distro=capability.distro,
            session=capability.session,
        ),
        item["updated_at"],
        item["id"],
    )


def _xdg_data_root() -> Path:
    configured = os.environ.get("XDG_DATA_HOME", "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            raise ValueError("XDG_DATA_HOME must be an absolute path")
        return path
    return Path.home() / ".local" / "share"
