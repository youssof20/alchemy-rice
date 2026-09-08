from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from alchemy.domain.app_adapters import (
    APP_CONFIG_MAX_BYTES,
    SUPPORTED_APPS,
    canonical_app_json,
    load_app_settings,
    parse_app_settings_bytes,
    parse_owned_config,
    render_owned_config,
)
from alchemy.domain.transactions import Operation, VerificationResult
from alchemy.platform.atomic import write_bytes_atomic

_EXECUTABLES = {
    "konsole": "konsole",
    "kitty": "kitty",
    "starship": "starship",
    "fastfetch": "fastfetch",
}
_ABSENT_CONFIG = "null"


class AppConfigDriver:
    def __init__(self, app: str, config_path: Path, home: Path) -> None:
        if app not in SUPPORTED_APPS:
            raise ValueError(f"Unsupported application adapter: {app}")
        self.app = app
        self.name = f"app.{app}"
        self.config_path = config_path.absolute()
        self.home = home.absolute()

    def inspect(self) -> dict[str, Any]:
        current = self._read()
        return {
            "app": self.app,
            "managed_path": str(self.config_path),
            "configured": current is not None,
            "settings": current,
            "owns_complete_file": True,
        }

    async def plan(self, desired_path: str) -> tuple[Operation, ...]:
        desired = await asyncio.to_thread(load_app_settings, self.app, desired_path)
        current = await asyncio.to_thread(self._read)
        if current == desired:
            return ()
        before = canonical_app_json(current) if current is not None else _ABSENT_CONFIG
        after = canonical_app_json(desired)
        return (
            Operation(
                operation_id=str(uuid.uuid4()),
                driver=self.name,
                target=f"/components/apps/{self.app}",
                description=f"Apply reviewed {self.app} visual settings",
                before=before,
                after=after,
                command=(),
                affected_paths=(str(self.config_path),),
            ),
        )

    async def apply(self, operation: Operation) -> None:
        self._validate_operation(operation)
        settings = parse_app_settings_bytes(self.app, operation.after.encode())
        await asyncio.to_thread(self._write, settings)

    async def verify(
        self, operation: Operation, *, expected: str | None = None
    ) -> VerificationResult:
        current = await asyncio.to_thread(self._read)
        observed = canonical_app_json(current) if current is not None else _ABSENT_CONFIG
        wanted = operation.after if expected is None else expected
        matched = observed == wanted
        return VerificationResult(
            matched,
            observed,
            f"{self.app} settings match the reviewed plan"
            if matched
            else f"Observed {self.app} settings differ from the reviewed plan",
        )

    async def rollback(self, operation: Operation) -> None:
        self._validate_operation(operation)
        if operation.before == _ABSENT_CONFIG:
            await asyncio.to_thread(self._remove)
            return
        if operation.before is None:
            raise RuntimeError(f"{self.app} operation has no previous-state representation")
        settings = parse_app_settings_bytes(self.app, operation.before.encode())
        await asyncio.to_thread(self._write, settings)

    async def refresh_after_snapshot(self) -> None:
        return None

    @staticmethod
    def confirmation_token(operation: Operation) -> str:
        payload = json.dumps(
            {
                "driver": operation.driver,
                "target": operation.target,
                "before": operation.before,
                "after": operation.after,
                "paths": operation.affected_paths,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def _read(self) -> dict[str, Any] | None:
        self._validate_path()
        if not self.config_path.exists():
            return None
        if self.config_path.is_symlink() or not self.config_path.is_file():
            raise RuntimeError(f"{self.app} managed path is not a regular file")
        with self.config_path.open("rb") as stream:
            raw = stream.read(APP_CONFIG_MAX_BYTES + 1)
        return parse_owned_config(self.app, raw)

    def _write(self, settings: dict[str, Any]) -> None:
        self._validate_path()
        if self.config_path.is_symlink():
            raise RuntimeError(f"{self.app} managed path cannot be a symlink")
        write_bytes_atomic(
            self.config_path,
            render_owned_config(self.app, settings),
            overwrite=True,
        )

    def _remove(self) -> None:
        self._validate_path()
        if self.config_path.is_symlink():
            raise RuntimeError(f"{self.app} managed path cannot be a symlink")
        if self.config_path.exists():
            if not self.config_path.is_file():
                raise RuntimeError(f"{self.app} managed path is not a regular file")
            self.config_path.unlink()

    def _validate_path(self) -> None:
        try:
            relative = self.config_path.relative_to(self.home)
        except ValueError as exc:
            raise RuntimeError("Application adapter path is outside the configured home") from exc
        current = self.home
        for part in relative.parts[:-1]:
            current /= part
            if current.is_symlink():
                raise RuntimeError(
                    f"Application adapter path has a symlinked parent: {current}"
                )

    def _validate_operation(self, operation: Operation) -> None:
        if (
            operation.driver != self.name
            or operation.target != f"/components/apps/{self.app}"
            or operation.affected_paths != (str(self.config_path),)
            or operation.command
        ):
            raise RuntimeError("Application operation does not match this adapter")


class AppDriverRegistry:
    def __init__(
        self,
        *,
        home: Path,
        config_root: Path,
        xdg_data_root: Path,
        which: Callable[[str], str | None],
    ) -> None:
        self.home = home
        self.config_root = config_root
        self.xdg_data_root = xdg_data_root
        self.which = which

    def names(self) -> tuple[str, ...]:
        return SUPPORTED_APPS

    def create(self, app: str, *, require_installed: bool = True) -> AppConfigDriver:
        if app not in SUPPORTED_APPS:
            raise ValueError(f"Unsupported application adapter: {app}")
        if require_installed and self.which(_EXECUTABLES[app]) is None:
            raise RuntimeError(f"{app} is not installed or is unavailable on PATH")
        return AppConfigDriver(app, self._path(app), self.home)

    def _path(self, app: str) -> Path:
        if app == "konsole":
            return self.xdg_data_root / "konsole" / "Alchemy.profile"
        if app == "kitty":
            return self.config_root / "kitty" / "kitty.conf"
        if app == "starship":
            return self.config_root / "starship.toml"
        return self.config_root / "fastfetch" / "config.jsonc"
