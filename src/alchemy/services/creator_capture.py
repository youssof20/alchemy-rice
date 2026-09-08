from __future__ import annotations

import getpass
import json
import socket
from pathlib import Path
from typing import Any, Protocol

from alchemy.domain.capture import CAPTURE_COMPONENTS, CaptureResult, build_capture
from alchemy.domain.rice import canonical_json_bytes, parse_rice_bytes
from alchemy.domain.sanitizer import SanitizationContext
from alchemy.platform.atomic import write_bytes_atomic
from alchemy.services.environment_probe import EnvironmentProbe
from alchemy.services.transaction_service import TransactionService

MAX_CAPTURE_METADATA_BYTES = 64 * 1024


class PanelInspector(Protocol):
    async def inspect_panels(self) -> dict[str, Any]: ...


class CreatorCaptureService:
    """Build a reviewable, local-only rice draft from allowlisted visual state."""

    def __init__(
        self,
        *,
        probe: EnvironmentProbe | None = None,
        panel_inspector: PanelInspector | None = None,
        sanitizer_context: SanitizationContext | None = None,
    ) -> None:
        self.probe = probe or EnvironmentProbe()
        self.panel_inspector = panel_inspector or TransactionService(probe=self.probe)
        self.sanitizer_context = sanitizer_context or SanitizationContext(
            home=str(Path.home()),
            username=getpass.getuser(),
            hostname=socket.gethostname(),
        )

    async def draft(
        self, metadata_path: str, *, excluded: frozenset[str] = frozenset()
    ) -> CaptureResult:
        metadata = load_capture_metadata(metadata_path)
        report = self.probe.inspect()
        _require_capture_environment(report.capabilities.to_dict())
        panel_state: dict[str, Any] | None = None
        panel_error: str | None = None
        if "panels" not in excluded:
            try:
                panel_state = await self.panel_inspector.inspect_panels()
            except (RuntimeError, ValueError, OSError) as exc:
                panel_error = f"Panel inspection failed ({type(exc).__name__}); panels were omitted"
        return build_capture(
            metadata,
            report,
            panel_state=panel_state,
            panel_error=panel_error,
            excluded=excluded,
            sanitizer_context=self.sanitizer_context,
        )

    async def export(
        self,
        metadata_path: str,
        destination_path: str,
        *,
        excluded: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        result = await self.draft(metadata_path, excluded=excluded)
        if not result.export_ready:
            codes = [item.code for item in result.findings if item.blocking]
            codes.extend(item.code for item in result.sanitization.findings)
            raise ValueError(
                "Capture is not export-ready; review and remove or replace: "
                + ", ".join(sorted(set(codes)))
            )
        destination = Path(destination_path).expanduser().absolute()
        if destination.suffix != ".rice":
            raise ValueError("Capture destination must use the .rice extension")
        if not destination.parent.is_dir():
            raise ValueError("Capture destination directory does not exist")
        manifest = parse_rice_bytes(canonical_json_bytes(result.manifest))
        write_bytes_atomic(destination, manifest.canonical_bytes, overwrite=False)
        return {
            "action": "captured",
            "identity": manifest.identity,
            "sha256": manifest.sha256,
            "bytes": len(manifest.canonical_bytes),
            "path": str(destination),
            "components": list(result.included_components),
            "findings": [item.to_dict() for item in result.findings],
            "summary": result.to_dict()["summary"],
            "applied": False,
            "uploaded": False,
        }


def load_capture_metadata(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Capture metadata must be a regular JSON file")
    if path.stat().st_size > MAX_CAPTURE_METADATA_BYTES:
        raise ValueError("Capture metadata exceeds the 64 KiB input limit")
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except UnicodeDecodeError as exc:
        raise ValueError("Capture metadata must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Capture metadata must be valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Capture metadata must be an object")
    return data


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _require_capture_environment(capability: dict[str, Any]) -> None:
    desktop = capability.get("desktop")
    plasma = capability.get("plasma_version")
    session = capability.get("session")
    if (
        capability.get("host_os") != "linux"
        or not isinstance(plasma, str)
        or not isinstance(desktop, str)
        or "kde" not in desktop.casefold()
        or session not in {"wayland", "x11"}
    ):
        raise RuntimeError("Desktop capture requires an active Linux KDE Plasma session")
    parts = tuple(int(part) for part in plasma.split("."))
    if not (6, 6) <= parts[:2] <= (6, 8):
        raise RuntimeError("Desktop capture targets Plasma 6.6 through 6.8")


def capture_component_names() -> tuple[str, ...]:
    return tuple(sorted(CAPTURE_COMPONENTS))
