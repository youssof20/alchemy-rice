from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from alchemy.domain.transactions import Operation, TransactionState
from alchemy.drivers.color_scheme import ColorSchemeDriver
from alchemy.platform.commands import CommandRunner, Runner
from alchemy.platform.journal import JournalStore
from alchemy.platform.locking import MutationLock
from alchemy.platform.snapshots import SnapshotStore
from alchemy.services.environment_probe import EnvironmentProbe


class TransactionFailedError(RuntimeError):
    pass


class TransactionService:
    def __init__(
        self,
        *,
        home: Path | None = None,
        state_root: Path | None = None,
        data_root: Path | None = None,
        runner: Runner | None = None,
        which: Callable[[str], str | None] | None = None,
        probe: EnvironmentProbe | None = None,
    ) -> None:
        self.home = (home or Path.home()).absolute()
        self.state_root = state_root or self.home / ".local" / "state" / "alchemy"
        self.data_root = data_root or self.home / ".local" / "share" / "alchemy"
        self.runner = runner or CommandRunner()
        self.which = which or shutil.which
        self.probe = probe or EnvironmentProbe(runner=self.runner, which=self.which, home=self.home)
        self.journals = JournalStore(self.state_root / "transactions")
        self.snapshots = SnapshotStore(self.data_root / "snapshots", home=self.home)
        self.lock_path = self.state_root / "apply.lock"

    async def plan_color_scheme(self, desired: str) -> tuple[Operation, ...]:
        report = self.probe.inspect()
        return await self._driver(report.capabilities.apply_supported).plan(desired)

    async def apply_color_scheme(self, desired: str) -> dict[str, Any] | None:
        report = self.probe.inspect()
        driver = self._driver(report.capabilities.apply_supported)
        operations = await driver.plan(desired)
        if not operations:
            return None
        operation = operations[0]
        snapshot = self.snapshots.create(
            (driver.kdeglobals,),
            driver=driver.name,
            plasma_version=report.capabilities.plasma_version,
            reason=operation.description,
        )
        record = self.journals.create(
            operation=operation,
            snapshot_id=str(snapshot["snapshot_id"]),
            environment=report.capabilities.to_dict(),
        )
        with MutationLock(self.lock_path):
            record = self.journals.transition(
                record, TransactionState.APPLYING, current_operation_index=0
            )
            try:
                await driver.apply(operation)
                verification = await driver.verify(operation)
                if not verification.matched:
                    raise TransactionFailedError(verification.detail)
            except Exception as exc:
                record = self.journals.transition(
                    record,
                    TransactionState.ROLLING_BACK,
                    current_operation_index=0,
                    error=str(exc),
                )
                try:
                    await self._restore_operation(driver, operation, str(snapshot["snapshot_id"]))
                    rollback_verification = await driver.verify(
                        operation, expected=operation.before
                    )
                    if not rollback_verification.matched:
                        raise TransactionFailedError("Rollback verification failed")
                    self.journals.transition(
                        record,
                        TransactionState.ROLLED_BACK,
                        current_operation_index=0,
                        verification=rollback_verification,
                        rollback_status="verified",
                        error=str(exc),
                    )
                except Exception as rollback_error:
                    self.journals.transition(
                        record,
                        TransactionState.FAILED,
                        current_operation_index=0,
                        rollback_status="failed",
                        error=f"{exc}; rollback: {rollback_error}",
                    )
                    raise TransactionFailedError(
                        f"Apply failed and rollback could not be verified: {rollback_error}"
                    ) from exc
                raise TransactionFailedError(
                    "Color-scheme apply failed; the previous state was restored and verified."
                ) from exc
            return self.journals.transition(
                record,
                TransactionState.COMMITTED,
                current_operation_index=0,
                verification=verification,
            )

    async def revert_last(self) -> dict[str, Any]:
        record = self.journals.latest(TransactionState.COMMITTED)
        if record is None:
            raise TransactionFailedError("No committed transaction is available to revert")
        return await self._rollback_record(record)

    async def recover(self, transaction_id: str) -> dict[str, Any]:
        record = self.journals.load(transaction_id)
        state = TransactionState(record["state"])
        if state not in {
            TransactionState.PLANNED,
            TransactionState.APPLYING,
            TransactionState.ROLLING_BACK,
            TransactionState.FAILED,
        }:
            raise TransactionFailedError(f"Transaction is already {state.value}")
        return await self._rollback_record(record)

    async def _rollback_record(self, record: dict[str, Any]) -> dict[str, Any]:
        operations = record.get("operations")
        if not isinstance(operations, list) or len(operations) != 1:
            raise TransactionFailedError("Phase 1 recovery requires exactly one operation")
        operation = Operation.from_dict(operations[0])
        driver = self._driver(True)
        with MutationLock(self.lock_path):
            if record["state"] != TransactionState.ROLLING_BACK.value:
                record = self.journals.transition(
                    record, TransactionState.ROLLING_BACK, current_operation_index=0
                )
            try:
                await self._restore_operation(driver, operation, str(record["snapshot_id"]))
                verification = await driver.verify(operation, expected=operation.before)
                if not verification.matched:
                    raise TransactionFailedError("Restored color scheme did not match pre-state")
            except Exception as exc:
                self.journals.transition(
                    record,
                    TransactionState.FAILED,
                    current_operation_index=0,
                    rollback_status="failed",
                    error=str(exc),
                )
                raise
            return self.journals.transition(
                record,
                TransactionState.ROLLED_BACK,
                current_operation_index=0,
                verification=verification,
                rollback_status="verified",
            )

    async def _restore_operation(
        self, driver: ColorSchemeDriver, operation: Operation, snapshot_id: str
    ) -> None:
        if operation.before is None:
            await asyncio.to_thread(self.snapshots.restore, snapshot_id)
            return
        await driver.rollback(operation)

    def _driver(self, apply_supported: bool) -> ColorSchemeDriver:
        kreadconfig = self.which("kreadconfig6")
        apply_tool = self.which("plasma-apply-colorscheme")
        if not apply_supported or kreadconfig is None or apply_tool is None:
            raise TransactionFailedError(
                "Color-scheme mutation is unavailable on this environment. "
                "Alchemy requires a tested Plasma 6.6-6.8 session and both KDE tools."
            )
        return ColorSchemeDriver(
            self.runner,
            kreadconfig=kreadconfig,
            apply_tool=apply_tool,
            kdeglobals=self.home / ".config" / "kdeglobals",
        )
