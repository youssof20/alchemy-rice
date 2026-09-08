from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from alchemy.domain.rice import (
    RiceManifest,
    evaluate_compatibility,
    load_override,
    load_rice,
    resolve_override,
    verify_sha256,
)
from alchemy.platform.atomic import write_bytes_atomic
from alchemy.services.environment_probe import EnvironmentProbe


class RiceService:
    def __init__(
        self, *, data_root: Path | None = None, probe: EnvironmentProbe | None = None
    ) -> None:
        self.data_root = data_root or _xdg_data_root() / "alchemy"
        self.probe = probe or EnvironmentProbe()

    def inspect(
        self,
        path: str,
        *,
        expected_sha256: str | None = None,
        override_path: str | None = None,
    ) -> dict[str, Any]:
        manifest = load_rice(path)
        verify_sha256(manifest.sha256, expected_sha256)
        if override_path is None:
            data = manifest.data
            resolved: dict[str, Any] | None = None
        else:
            override = load_override(override_path)
            result = resolve_override(manifest, override)
            data = result.data
            resolved = {
                "override_sha256": override.sha256,
                "resolved_sha256": result.resolved_sha256,
                "provenance": result.provenance,
                "components": result.data["components"],
            }
        compatibility = evaluate_compatibility(data, self.probe.inspect().capabilities)
        return {
            "valid": True,
            "identity": manifest.identity,
            "sha256": manifest.sha256,
            "canonical_bytes": len(manifest.canonical_bytes),
            "components": sorted(data["components"]),
            "source": data["source"],
            "dependencies": data["dependencies"],
            "compatibility": compatibility.to_dict(),
            "resolved": resolved,
        }

    def export(self, source_path: str, destination_path: str) -> dict[str, Any]:
        manifest = load_rice(source_path, require_canonical=False)
        destination = Path(destination_path).expanduser().absolute()
        if destination.suffix != ".rice":
            raise ValueError("Export destination must use the .rice extension")
        if not destination.parent.is_dir():
            raise ValueError("Export destination directory does not exist")
        write_bytes_atomic(destination, manifest.canonical_bytes, overwrite=False)
        return self._stored_result(manifest, destination, "exported")

    def import_manifest(
        self,
        path: str,
        *,
        expected_sha256: str | None = None,
        override_path: str | None = None,
    ) -> dict[str, Any]:
        source = Path(path).expanduser().resolve(strict=True)
        if source.suffix != ".rice":
            raise ValueError("Imported manifests must use the .rice extension")
        manifest = load_rice(source)
        verify_sha256(manifest.sha256, expected_sha256)
        imports = self.data_root / "rices" / "imports"
        destination = imports / f"{manifest.sha256}.rice"
        override = load_override(override_path) if override_path is not None else None
        resolved = resolve_override(manifest, override) if override is not None else None
        compatibility_data = resolved.data if resolved is not None else manifest.data
        compatibility = evaluate_compatibility(
            compatibility_data, self.probe.inspect().capabilities
        ).to_dict()
        _store_once(destination, manifest.canonical_bytes)
        result = self._stored_result(manifest, destination, "imported")
        if override is not None and resolved is not None:
            override_destination = imports / (
                f"{manifest.sha256}-{override.sha256}.override.json"
            )
            _store_once(override_destination, override.canonical_bytes)
            result.update(
                {
                    "override_sha256": override.sha256,
                    "override_path": str(override_destination),
                    "resolved_sha256": resolved.resolved_sha256,
                }
            )
        result["compatibility"] = compatibility
        return result

    def resolve(self, base_path: str, override_path: str) -> dict[str, Any]:
        base = load_rice(base_path)
        override = load_override(override_path)
        result = resolve_override(base, override)
        compatibility = evaluate_compatibility(
            result.data, self.probe.inspect().capabilities
        )
        return {
            "identity": base.identity,
            "base_sha256": base.sha256,
            "override_sha256": override.sha256,
            "resolved_sha256": result.resolved_sha256,
            "components": result.data["components"],
            "dependencies": result.data["dependencies"],
            "provenance": result.provenance,
            "compatibility": compatibility.to_dict(),
        }

    @staticmethod
    def _stored_result(
        manifest: RiceManifest, destination: Path, action: str
    ) -> dict[str, Any]:
        return {
            "action": action,
            "identity": manifest.identity,
            "sha256": manifest.sha256,
            "bytes": len(manifest.canonical_bytes),
            "path": str(destination),
            "applied": False,
        }


def _xdg_data_root() -> Path:
    configured = os.environ.get("XDG_DATA_HOME", "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            raise ValueError("XDG_DATA_HOME must be an absolute path")
        return path
    return Path.home() / ".local" / "share"


def _store_once(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlinked rice cache entry: {path.name}")
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"Stored rice artifact failed integrity verification: {path.name}")
        return
    try:
        write_bytes_atomic(path, payload, overwrite=False)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise RuntimeError(
                f"Stored rice artifact failed integrity verification: {path.name}"
            ) from None
