from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alchemy.platform.atomic import write_json_atomic


class SnapshotError(RuntimeError):
    pass


class SnapshotStore:
    """Capture and restore only explicitly named user-owned paths."""

    def __init__(self, directory: Path, *, home: Path) -> None:
        self.directory = directory
        self.home = home.absolute()

    def create(
        self,
        paths: tuple[Path, ...],
        *,
        driver: str,
        plasma_version: str | None,
        reason: str,
    ) -> dict[str, Any]:
        snapshot_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4()}"
        destination = self.directory / snapshot_id
        destination.mkdir(parents=True, exist_ok=False)
        manifest: dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "created_at": datetime.now(UTC).isoformat(),
            "plasma_version": plasma_version,
            "reason": reason,
            "archive": "user-state.tar",
            "entries": [],
        }
        archive_path = destination / "user-state.tar"
        try:
            with tarfile.open(archive_path, "w", dereference=False) as archive:
                for path in paths:
                    manifest["entries"].append(self._capture_entry(archive, path, driver))
            write_json_atomic(destination / "manifest.json", manifest)
        except Exception:
            # Leave a visible incomplete snapshot directory for diagnosis. It is
            # never treated as valid without a complete manifest.
            raise
        return manifest

    def restore(self, snapshot_id: str) -> None:
        destination = self._snapshot_path(snapshot_id)
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            raise SnapshotError("Snapshot manifest has no entry list")
        with tarfile.open(destination / str(manifest["archive"]), "r") as archive:
            for entry in entries:
                if not isinstance(entry, dict):
                    raise SnapshotError("Snapshot entry must be an object")
                self._restore_entry(archive, entry)

    def _capture_entry(
        self, archive: tarfile.TarFile, path: Path, driver: str
    ) -> dict[str, Any]:
        absolute = self._validate_user_path(path)
        relative = absolute.relative_to(self.home).as_posix()
        entry: dict[str, Any] = {
            "logical_path": relative,
            "original_path": str(absolute),
            "exists": absolute.exists() or absolute.is_symlink(),
            "sha256": None,
            "mode": None,
            "symlink": False,
            "symlink_target": None,
            "size": 0,
            "driver": driver,
        }
        if not entry["exists"]:
            return entry
        metadata = absolute.lstat()
        entry["mode"] = stat.S_IMODE(metadata.st_mode)
        if absolute.is_symlink():
            target = os.readlink(absolute)
            info = tarfile.TarInfo(relative)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            info.mode = int(entry["mode"])
            archive.addfile(info)
            entry["symlink"] = True
            entry["symlink_target"] = target
            return entry
        if not absolute.is_file():
            raise SnapshotError(f"Snapshot path is not a regular file: {relative}")
        data = absolute.read_bytes()
        info = tarfile.TarInfo(relative)
        info.size = len(data)
        info.mode = int(entry["mode"])
        archive.addfile(info, io.BytesIO(data))
        entry["size"] = len(data)
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        return entry

    def _restore_entry(self, archive: tarfile.TarFile, entry: dict[str, Any]) -> None:
        target = self._validate_user_path(Path(str(entry["original_path"])))
        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                raise SnapshotError(f"Refusing to replace directory: {target}")
            target.unlink()
        if not entry["exists"]:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        member = archive.getmember(str(entry["logical_path"]))
        if entry["symlink"]:
            os.symlink(str(entry["symlink_target"]), target)
            return
        stream = archive.extractfile(member)
        if stream is None:
            raise SnapshotError(f"Missing snapshot content: {entry['logical_path']}")
        data = stream.read()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise SnapshotError(f"Snapshot hash mismatch: {entry['logical_path']}")
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.restore")
        try:
            temporary.write_bytes(data)
            os.chmod(temporary, int(entry["mode"]))
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def _validate_user_path(self, path: Path) -> Path:
        absolute = path.absolute()
        try:
            relative = absolute.relative_to(self.home)
        except ValueError as exc:
            raise SnapshotError("Snapshot path is outside the configured home directory") from exc
        current = self.home
        for part in relative.parts[:-1]:
            current /= part
            if current.is_symlink():
                raise SnapshotError(
                    f"Snapshot path has a symlinked parent directory: {current}"
                )
        return absolute

    def _snapshot_path(self, snapshot_id: str) -> Path:
        if "/" in snapshot_id or "\\" in snapshot_id or snapshot_id in {"", ".", ".."}:
            raise SnapshotError("Invalid snapshot id")
        return self.directory / snapshot_id
