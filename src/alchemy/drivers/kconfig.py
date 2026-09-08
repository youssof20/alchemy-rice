from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from alchemy.domain.transactions import Operation, VerificationResult
from alchemy.platform.commands import Runner
from alchemy.platform.kde_notifications import Notifier, RefreshAction

_SAFE_VALUE = re.compile(r"^[^\x00-\x1f\x7f]{1,512}$")


@dataclass(frozen=True, slots=True)
class KConfigSpec:
    name: str
    target: str
    label: str
    config_file: str
    group: str
    key: str
    refresh: RefreshAction
    allowed_values: frozenset[str] | None = None
    minimum_integer: int | None = None
    maximum_integer: int | None = None


class KConfigDriver:
    def __init__(
        self,
        spec: KConfigSpec,
        runner: Runner,
        notifier: Notifier,
        *,
        kreadconfig: str,
        kwriteconfig: str,
        config_path: Path,
        apply_tool: str | None = None,
        apply_arguments: tuple[str, ...] = (),
    ) -> None:
        self.spec = spec
        self.name = spec.name
        self.runner = runner
        self.notifier = notifier
        self.kreadconfig = kreadconfig
        self.kwriteconfig = kwriteconfig
        self.config_path = config_path
        self.apply_tool = apply_tool
        self.apply_arguments = apply_arguments

    async def read(self) -> str | None:
        arguments = (
            self.kreadconfig,
            "--file",
            self.spec.config_file,
            "--group",
            self.spec.group,
            "--key",
            self.spec.key,
        )
        result = await asyncio.to_thread(self.runner.run, arguments)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"Could not read {self.spec.label}")
        return result.stdout.strip() or None

    async def plan(self, desired: str) -> tuple[Operation, ...]:
        self._validate(desired)
        current = await self.read()
        if current == desired:
            return ()
        command = (
            (self.apply_tool, *self.apply_arguments, desired)
            if self.apply_tool
            else self._write_command(desired)
        )
        return (
            Operation(
                operation_id=str(uuid.uuid4()),
                driver=self.name,
                target=self.spec.target,
                description=f"Change {self.spec.label} from {current or 'unset'} to {desired}",
                before=current,
                after=desired,
                command=command,
                affected_paths=(str(self.config_path),),
            ),
        )

    async def apply(self, operation: Operation) -> None:
        result = await asyncio.to_thread(self.runner.run, operation.command, timeout=30.0)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"Could not apply {self.spec.label}")
        if self.apply_tool is None:
            await asyncio.to_thread(self.notifier.refresh, self.spec.refresh)

    async def verify(
        self, operation: Operation, *, expected: str | None = None
    ) -> VerificationResult:
        observed = await self.read()
        wanted = operation.after if expected is None else expected
        matched = observed == wanted
        return VerificationResult(
            matched,
            observed,
            f"{self.spec.label} matches the planned value"
            if matched
            else f"Observed {self.spec.label} differs",
        )

    async def rollback(self, operation: Operation) -> None:
        if operation.before is None:
            raise RuntimeError(f"Previous {self.spec.label} was unset; restore the snapshot")
        command = (
            (self.apply_tool, *self.apply_arguments, operation.before)
            if self.apply_tool
            else self._write_command(operation.before)
        )
        result = await asyncio.to_thread(self.runner.run, command, timeout=30.0)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"Could not restore {self.spec.label}")
        if self.apply_tool is None:
            await asyncio.to_thread(self.notifier.refresh, self.spec.refresh)

    async def refresh_after_snapshot(self) -> None:
        await asyncio.to_thread(self.notifier.refresh, self.spec.refresh)

    def _write_command(self, value: str) -> tuple[str, ...]:
        return (
            self.kwriteconfig,
            "--file",
            self.spec.config_file,
            "--group",
            self.spec.group,
            "--key",
            self.spec.key,
            value,
        )

    def _validate(self, value: str) -> None:
        if not _SAFE_VALUE.fullmatch(value):
            raise ValueError(f"{self.spec.label} contains unsupported characters")
        if self.spec.allowed_values is not None and value not in self.spec.allowed_values:
            allowed = ", ".join(sorted(self.spec.allowed_values))
            raise ValueError(f"{self.spec.label} must be one of: {allowed}")
        if self.spec.minimum_integer is not None:
            try:
                integer = int(value)
            except ValueError as exc:
                raise ValueError(f"{self.spec.label} must be an integer") from exc
            assert self.spec.maximum_integer is not None
            if not self.spec.minimum_integer <= integer <= self.spec.maximum_integer:
                raise ValueError(
                    f"{self.spec.label} must be between "
                    f"{self.spec.minimum_integer} and {self.spec.maximum_integer}"
                )
