from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from alchemy.domain.capabilities import EnvironmentReport
from alchemy.domain.transactions import Operation, TransactionState, VerificationResult
from alchemy.drivers.color_scheme import ColorSchemeDriver
from alchemy.drivers.panels import PanelDriver
from alchemy.drivers.registry import DriverRegistry
from alchemy.platform.commands import CommandRunner, Runner
from alchemy.platform.journal import JournalStore
from alchemy.platform.kde_notifications import KdeNotifier, Notifier
from alchemy.platform.locking import MutationLock
from alchemy.platform.plasma_shell import PlasmaShell
from alchemy.platform.snapshots import SnapshotStore
from alchemy.services.environment_probe import EnvironmentProbe


class TransactionFailedError(RuntimeError):
    pass


class TransactionalDriver(Protocol):
    name: str
    config_path: Path

    async def plan(self, desired: str) -> tuple[Operation, ...]: ...

    async def apply(self, operation: Operation) -> None: ...

    async def verify(
        self, operation: Operation, *, expected: str | None = None
    ) -> VerificationResult: ...

    async def rollback(self, operation: Operation) -> None: ...

    async def refresh_after_snapshot(self) -> None: ...


class TransactionService:
    def __init__(
        self,
        *,
        home: Path | None = None,
        config_root: Path | None = None,
        state_root: Path | None = None,
        data_root: Path | None = None,
        runner: Runner | None = None,
        which: Callable[[str], str | None] | None = None,
        probe: EnvironmentProbe | None = None,
        notifier: Notifier | None = None,
        plasma_shell: PlasmaShell | None = None,
    ) -> None:
        self.home = (home or Path.home()).absolute()
        self.config_root = config_root or _xdg_config_root(self.home)
        self.state_root = state_root or self.home / ".local" / "state" / "alchemy"
        self.data_root = data_root or self.home / ".local" / "share" / "alchemy"
        self.runner = runner or CommandRunner()
        self.which = which or shutil.which
        self.probe = probe or EnvironmentProbe(runner=self.runner, which=self.which, home=self.home)
        self.notifier = notifier or KdeNotifier()
        self.registry = DriverRegistry(
            self.runner,
            self.which,
            home=self.home,
            config_root=self.config_root,
            notifier=self.notifier,
            plasma_shell=plasma_shell,
        )
        self.journals = JournalStore(self.state_root / "transactions")
        self.snapshots = SnapshotStore(self.data_root / "snapshots", home=self.home)
        self.lock_path = self.state_root / "apply.lock"

    def setting_names(self) -> tuple[str, ...]:
        return self.registry.names()

    async def plan_color_scheme(self, desired: str) -> tuple[Operation, ...]:
        report = self.probe.inspect()
        return await self._color_driver(report.capabilities.apply_supported).plan(desired)

    async def apply_color_scheme(self, desired: str) -> dict[str, Any] | None:
        report = self.probe.inspect()
        driver = self._color_driver(report.capabilities.apply_supported)
        return await self._apply_driver(driver, desired, report)

    async def plan_component(self, name: str, desired: str) -> tuple[Operation, ...]:
        report = self.probe.inspect()
        self._require_mutation_environment(report)
        return await self._registry_driver(name).plan(desired)

    async def apply_component(self, name: str, desired: str) -> dict[str, Any] | None:
        report = self.probe.inspect()
        self._require_mutation_environment(report)
        return await self._apply_driver(self._registry_driver(name), desired, report)

    async def inspect_panels(self) -> dict[str, Any]:
        return await self.registry.create_panel().inspect()

    async def plan_panels(self, layout_path: str) -> dict[str, Any]:
        report = self.probe.inspect()
        self._require_mutation_environment(report)
        driver = self.registry.create_panel()
        operations = await driver.plan(layout_path)
        if not operations:
            return {"state": "no_change", "current": await driver.inspect()}
        return driver.public_plan(operations[0])

    async def apply_panels(
        self, layout_path: str, confirmation_token: str
    ) -> dict[str, Any] | None:
        report = self.probe.inspect()
        self._require_mutation_environment(report)
        return await self._apply_driver(
            self.registry.create_panel(),
            layout_path,
            report,
            confirmation_token=confirmation_token,
        )

    async def _apply_driver(
        self,
        driver: TransactionalDriver,
        desired: str,
        report: EnvironmentReport,
        *,
        confirmation_token: str | None = None,
    ) -> dict[str, Any] | None:
        with MutationLock(self.lock_path):
            operations = await driver.plan(desired)
            if not operations:
                return None
            operation = operations[0]
            if confirmation_token is not None and (
                driver.name != PanelDriver.name
                or PanelDriver.confirmation_token(operation) != confirmation_token
            ):
                raise TransactionFailedError(
                    "Panel state or screen mapping changed after preview; run plan-panels again"
                )
            snapshot = self.snapshots.create(
                (driver.config_path,),
                driver=driver.name,
                plasma_version=report.capabilities.plasma_version,
                reason=operation.description,
            )
            record = self.journals.create(
                operation=operation,
                snapshot_id=str(snapshot["snapshot_id"]),
                environment=report.capabilities.to_dict(),
            )
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
                    f"{operation.description} failed; the previous state was restored and verified."
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
            raise TransactionFailedError("Recovery requires exactly one operation")
        operation = Operation.from_dict(operations[0])
        driver = self._driver_for_recovery(operation.driver)
        with MutationLock(self.lock_path):
            if record["state"] != TransactionState.ROLLING_BACK.value:
                record = self.journals.transition(
                    record, TransactionState.ROLLING_BACK, current_operation_index=0
                )
            try:
                await self._restore_operation(driver, operation, str(record["snapshot_id"]))
                verification = await driver.verify(operation, expected=operation.before)
                if not verification.matched:
                    raise TransactionFailedError("Restored setting did not match pre-state")
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
        self, driver: TransactionalDriver, operation: Operation, snapshot_id: str
    ) -> None:
        if operation.before is None:
            await asyncio.to_thread(self.snapshots.restore, snapshot_id)
            await driver.refresh_after_snapshot()
            return
        await driver.rollback(operation)

    def _driver_for_recovery(self, name: str) -> TransactionalDriver:
        if name == ColorSchemeDriver.name:
            return self._color_driver(True)
        if name == PanelDriver.name:
            return self.registry.create_panel()
        return self._registry_driver(name)

    def _registry_driver(self, name: str) -> TransactionalDriver:
        try:
            return self.registry.create(name)
        except (RuntimeError, ValueError) as exc:
            raise TransactionFailedError(str(exc)) from exc

    def _color_driver(self, apply_supported: bool) -> ColorSchemeDriver:
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
            kdeglobals=self.config_root / "kdeglobals",
            notifier=self.notifier,
        )

    @staticmethod
    def _require_mutation_environment(report: EnvironmentReport) -> None:
        capability = report.capabilities
        if (
            capability.host_os != "linux"
            or capability.plasma_version is None
            or capability.session not in {"wayland", "x11"}
            or capability.desktop is None
            or "kde" not in capability.desktop.lower()
            or bool(capability.plasma_manager.active)
        ):
            raise TransactionFailedError(
                "Setting mutation requires an active KDE Plasma session not owned by "
                "plasma-manager."
            )
        parts = tuple(int(part) for part in capability.plasma_version.split("."))
        if not (6, 6) <= parts[:2] <= (6, 8):
            raise TransactionFailedError("Setting mutation targets Plasma 6.6 through 6.8")


def _xdg_config_root(home: Path) -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if not configured:
        return home / ".config"
    path = Path(configured)
    if not path.is_absolute():
        raise ValueError("XDG_CONFIG_HOME must be an absolute path")
    return path
