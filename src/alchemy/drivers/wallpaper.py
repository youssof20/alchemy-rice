from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from alchemy.domain.transactions import Operation, VerificationResult
from alchemy.platform.commands import Runner
from alchemy.platform.plasma_shell import PlasmaShell

_FILL_MODE_NAMES = {
    0: "stretch",
    1: "preserveAspectFit",
    2: "preserveAspectCrop",
    6: "pad",
}
_READ_SCRIPT = """
var result = [];
var allDesktops = desktops();
for (var key in allDesktops) {
    var desktop = allDesktops[key];
    desktop.currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General'];
    result.push({
        plugin: desktop.wallpaperPlugin,
        image: desktop.readConfig('Image'),
        fill_mode: Number(desktop.readConfig('FillMode', 2))
    });
}
print(JSON.stringify(result));
""".strip()


class WallpaperDriver:
    name = "wallpaper.image"

    def __init__(
        self,
        runner: Runner,
        shell: PlasmaShell,
        *,
        apply_tool: str,
        config_path: Path,
    ) -> None:
        self.runner = runner
        self.shell = shell
        self.apply_tool = apply_tool
        self.config_path = config_path

    async def read(self) -> str:
        output = await asyncio.to_thread(self.shell.evaluate, _READ_SCRIPT)
        try:
            payload = json.loads(output.strip())
        except json.JSONDecodeError as exc:
            raise RuntimeError("Plasma returned malformed wallpaper state") from exc
        state = self._validated_state(payload)
        return self._serialize(state)

    async def plan(self, desired: str) -> tuple[Operation, ...]:
        image_path = Path(desired).expanduser().resolve(strict=True)
        if not image_path.is_file():
            raise ValueError("Wallpaper must be a regular local file")
        before = await self.read()
        current = self._uniform_state(before)
        desired_uri = image_path.as_uri()
        after_state = [
            {
                "plugin": "org.kde.image",
                "image": desired_uri,
                "fill_mode": current["fill_mode"],
            }
            for _ in json.loads(before)
        ]
        after = self._serialize(after_state)
        if before == after:
            return ()
        fill_name = _FILL_MODE_NAMES[int(current["fill_mode"])]
        return (
            Operation(
                operation_id=str(uuid.uuid4()),
                driver=self.name,
                target="kde.wallpaper.image",
                description=f"Change the shared desktop wallpaper to {image_path.name}",
                before=before,
                after=after,
                command=(
                    self.apply_tool,
                    "--fill-mode",
                    fill_name,
                    str(image_path),
                ),
                affected_paths=(str(self.config_path),),
            ),
        )

    async def apply(self, operation: Operation) -> None:
        result = await asyncio.to_thread(self.runner.run, operation.command, timeout=30.0)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Could not apply wallpaper")

    async def verify(
        self, operation: Operation, *, expected: str | None = None
    ) -> VerificationResult:
        observed = await self.read()
        wanted = operation.after if expected is None else expected
        matched = observed == wanted
        return VerificationResult(
            matched,
            observed,
            "Wallpaper state matches the planned value"
            if matched
            else "Observed wallpaper state differs",
        )

    async def rollback(self, operation: Operation) -> None:
        if operation.before is None:
            raise RuntimeError("Previous wallpaper state is unavailable")
        previous = self._uniform_state(operation.before)
        image_path = self._local_path(str(previous["image"]))
        fill_name = _FILL_MODE_NAMES[int(previous["fill_mode"])]
        result = await asyncio.to_thread(
            self.runner.run,
            (self.apply_tool, "--fill-mode", fill_name, str(image_path)),
            timeout=30.0,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Could not restore wallpaper")

    async def refresh_after_snapshot(self) -> None:
        raise RuntimeError("Wallpaper recovery requires a captured wallpaper state")

    @classmethod
    def _validated_state(cls, payload: Any) -> list[dict[str, str | int]]:
        if not isinstance(payload, list) or not payload:
            raise RuntimeError("Plasma reported no desktops")
        state: list[dict[str, str | int]] = []
        for desktop in payload:
            if not isinstance(desktop, dict):
                raise RuntimeError("Plasma returned an invalid desktop entry")
            plugin = desktop.get("plugin")
            image = desktop.get("image")
            fill_mode = desktop.get("fill_mode")
            if plugin != "org.kde.image":
                raise RuntimeError("All desktops must use KDE's image wallpaper plugin")
            if not isinstance(image, str) or not image:
                raise RuntimeError("A desktop has no restorable wallpaper image")
            if not isinstance(fill_mode, int) or fill_mode not in _FILL_MODE_NAMES:
                raise RuntimeError("A desktop uses an unsupported wallpaper fill mode")
            normalized_image = cls._local_path(image).resolve().as_uri()
            state.append({"plugin": plugin, "image": normalized_image, "fill_mode": fill_mode})
        return state

    @classmethod
    def _uniform_state(cls, serialized: str) -> dict[str, str | int]:
        try:
            state = cls._validated_state(json.loads(serialized))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Captured wallpaper state is malformed") from exc
        first = state[0]
        if any(desktop != first for desktop in state[1:]):
            raise RuntimeError("Wallpaper apply is disabled for non-uniform multi-desktop layouts")
        return first

    @staticmethod
    def _local_path(uri: str) -> Path:
        parsed = urlparse(uri)
        if (
            parsed.scheme != "file"
            or parsed.netloc not in {"", "localhost"}
            or parsed.fragment
            or parsed.query
        ):
            raise RuntimeError("Wallpaper recovery supports local file URLs only")
        path = Path(url2pathname(parsed.path))
        if not path.is_absolute():
            raise RuntimeError("Wallpaper URL is not an absolute local path")
        return path

    @staticmethod
    def _serialize(state: list[dict[str, str | int]]) -> str:
        return json.dumps(state, separators=(",", ":"), sort_keys=True)
