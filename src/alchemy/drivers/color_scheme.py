from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

from alchemy.domain.transactions import Operation, VerificationResult
from alchemy.platform.commands import Runner
from alchemy.platform.kde_notifications import Notifier, RefreshAction

_THEME_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,127}$")


class ColorSchemeDriver:
    name = "color_scheme"

    def __init__(
        self,
        runner: Runner,
        *,
        kreadconfig: str,
        apply_tool: str,
        kdeglobals: Path,
        notifier: Notifier,
    ) -> None:
        self.runner = runner
        self.kreadconfig = kreadconfig
        self.apply_tool = apply_tool
        self.kdeglobals = kdeglobals
        self.config_path = kdeglobals
        self.notifier = notifier

    async def read(self) -> str | None:
        result = await asyncio.to_thread(
            self.runner.run,
            (
                self.kreadconfig,
                "--file",
                "kdeglobals",
                "--group",
                "General",
                "--key",
                "ColorScheme",
            ),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Could not read the active color scheme")
        return result.stdout.strip() or None

    async def plan(self, desired: str) -> tuple[Operation, ...]:
        if not _THEME_NAME.fullmatch(desired):
            raise ValueError("Color-scheme name contains unsupported characters")
        current = await self.read()
        if current == desired:
            return ()
        return (
            Operation(
                operation_id=str(uuid.uuid4()),
                driver=self.name,
                target="kde.color_scheme",
                description=f"Change color scheme from {current or 'unset'} to {desired}",
                before=current,
                after=desired,
                command=(self.apply_tool, desired),
                affected_paths=(str(self.kdeglobals),),
            ),
        )

    async def apply(self, operation: Operation) -> None:
        result = await asyncio.to_thread(self.runner.run, operation.command, timeout=30.0)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Color-scheme apply failed")

    async def verify(
        self, operation: Operation, *, expected: str | None = None
    ) -> VerificationResult:
        observed = await self.read()
        wanted = operation.after if expected is None else expected
        matched = observed == wanted
        detail = (
            "Color scheme matches the planned value" if matched else "Observed color scheme differs"
        )
        return VerificationResult(matched, observed, detail)

    async def rollback(self, operation: Operation) -> None:
        if operation.before is None:
            raise RuntimeError("The previous color scheme was unset; restore the snapshot instead")
        result = await asyncio.to_thread(
            self.runner.run, (self.apply_tool, operation.before), timeout=30.0
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Color-scheme rollback failed")

    async def refresh_after_snapshot(self) -> None:
        await asyncio.to_thread(self.notifier.refresh, RefreshAction.PALETTE)
