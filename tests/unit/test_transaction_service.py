from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alchemy.domain.capabilities import CapabilityMatrix, ComponentCapability, EnvironmentReport
from alchemy.domain.transactions import TransactionState
from alchemy.platform.commands import CommandResult
from alchemy.platform.kde_notifications import RefreshAction
from alchemy.services.transaction_service import TransactionFailedError, TransactionService


class FakeProbe:
    def inspect(self) -> EnvironmentReport:
        return EnvironmentReport(
            CapabilityMatrix(
                host_os="linux",
                plasma_version="6.7.4",
                session="wayland",
                desktop="KDE",
                login_manager="sddm",
                distro="arch",
                distro_version="rolling",
                package_manager="pacman",
                aur_helper=None,
                portals=("screenshot",),
                plasma_apply=("colorscheme",),
                union=ComponentCapability(None, None),
                nix=ComponentCapability(False, False),
                plasma_manager=ComponentCapability(False, False),
                monitors=("eDP-1",),
                mixed_scale=False,
                immutable_host=False,
                apply_supported=True,
            ),
            (),
            (),
        )


class StatefulColorRunner:
    def __init__(self, current: str, config: Path, *, ignore_apply: bool = False) -> None:
        self.current = current
        self.config = config
        self.ignore_apply = ignore_apply

    def run(self, arguments: tuple[str, ...], *, timeout: float = 3.0) -> CommandResult:
        del timeout
        argv = tuple(arguments)
        if argv[0] == "/usr/bin/kreadconfig6":
            return CommandResult(argv, 0, f"{self.current}\n", "")
        if argv[0] == "/usr/bin/plasma-apply-colorscheme":
            if not self.ignore_apply:
                self.current = argv[1]
                self.config.write_text(f"ColorScheme={self.current}\n", encoding="utf-8")
            return CommandResult(argv, 0, "", "")
        return CommandResult(argv, 1, "", "unexpected command")


class FakeNotifier:
    def __init__(self) -> None:
        self.actions: list[RefreshAction] = []

    def refresh(self, action: RefreshAction) -> None:
        self.actions.append(action)


class StatefulSettingRunner:
    def __init__(self, current: str, config: Path) -> None:
        self.current = current
        self.config = config

    def run(self, arguments: tuple[str, ...], *, timeout: float = 3.0) -> CommandResult:
        del timeout
        argv = tuple(arguments)
        if argv[0] == "/usr/bin/kreadconfig6":
            return CommandResult(argv, 0, f"{self.current}\n", "")
        if argv[0] == "/usr/bin/kwriteconfig6":
            self.current = argv[-1]
            self.config.write_text(f"Theme={self.current}\n", encoding="utf-8")
            return CommandResult(argv, 0, "", "")
        return CommandResult(argv, 1, "", "unexpected command")


class TransactionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_registry_setting_uses_shared_transaction_and_revert(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            config = home / ".config" / "kdeglobals"
            config.parent.mkdir(parents=True)
            config.write_text("Theme=breeze\n", encoding="utf-8")
            runner = StatefulSettingRunner("breeze", config)
            notifier = FakeNotifier()
            service = TransactionService(
                home=home,
                config_root=home / ".config",
                state_root=root / "state",
                data_root=root / "data",
                runner=runner,
                which={
                    "kreadconfig6": "/usr/bin/kreadconfig6",
                    "kwriteconfig6": "/usr/bin/kwriteconfig6",
                }.get,
                probe=FakeProbe(),  # type: ignore[arg-type]
                notifier=notifier,
            )

            committed = await service.apply_component("icons.theme", "Papirus-Dark")

            assert committed is not None
            self.assertEqual(committed["state"], TransactionState.COMMITTED.value)
            self.assertEqual(runner.current, "Papirus-Dark")
            reverted = await service.revert_last()
            self.assertEqual(reverted["state"], TransactionState.ROLLED_BACK.value)
            self.assertEqual(runner.current, "breeze")
            self.assertEqual(notifier.actions, [RefreshAction.ICON, RefreshAction.ICON])

    async def test_apply_and_revert_are_journaled_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            config = home / ".config" / "kdeglobals"
            config.parent.mkdir(parents=True)
            config.write_text("ColorScheme=BreezeLight\n", encoding="utf-8")
            runner = StatefulColorRunner("BreezeLight", config)
            service = self._service(root, home, runner)

            committed = await service.apply_color_scheme("BreezeDark")

            self.assertIsNotNone(committed)
            assert committed is not None
            self.assertEqual(committed["state"], TransactionState.COMMITTED.value)
            self.assertEqual(runner.current, "BreezeDark")
            reverted = await service.revert_last()
            self.assertEqual(reverted["state"], TransactionState.ROLLED_BACK.value)
            self.assertEqual(runner.current, "BreezeLight")

    async def test_verification_failure_restores_previous_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            config = home / ".config" / "kdeglobals"
            config.parent.mkdir(parents=True)
            config.write_text("ColorScheme=BreezeLight\n", encoding="utf-8")
            runner = StatefulColorRunner("BreezeLight", config, ignore_apply=True)
            service = self._service(root, home, runner)

            with self.assertRaisesRegex(TransactionFailedError, "previous state was restored"):
                await service.apply_color_scheme("BreezeDark")

            latest = service.journals.latest()
            assert latest is not None
            self.assertEqual(latest["state"], TransactionState.ROLLED_BACK.value)
            self.assertEqual(runner.current, "BreezeLight")

    async def test_incomplete_apply_can_be_recovered_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            config = home / ".config" / "kdeglobals"
            config.parent.mkdir(parents=True)
            config.write_text("ColorScheme=BreezeLight\n", encoding="utf-8")
            runner = StatefulColorRunner("BreezeLight", config)
            service = self._service(root, home, runner)
            operation = (await service.plan_color_scheme("BreezeDark"))[0]
            snapshot = service.snapshots.create(
                (config,),
                driver="color_scheme",
                plasma_version="6.7.4",
                reason="interrupted test",
            )
            record = service.journals.create(
                operation=operation,
                snapshot_id=str(snapshot["snapshot_id"]),
                environment={},
            )
            record = service.journals.transition(
                record, TransactionState.APPLYING, current_operation_index=0
            )
            runner.current = "BreezeDark"
            config.write_text("ColorScheme=BreezeDark\n", encoding="utf-8")

            recovered = await service.recover(str(record["transaction_id"]))

            self.assertEqual(recovered["state"], TransactionState.ROLLED_BACK.value)
            self.assertEqual(recovered["rollback_status"], "verified")
            self.assertEqual(runner.current, "BreezeLight")

    @staticmethod
    def _service(root: Path, home: Path, runner: StatefulColorRunner) -> TransactionService:
        executables = {
            "kreadconfig6": "/usr/bin/kreadconfig6",
            "plasma-apply-colorscheme": "/usr/bin/plasma-apply-colorscheme",
        }
        return TransactionService(
            home=home,
            config_root=home / ".config",
            state_root=root / "state",
            data_root=root / "data",
            runner=runner,
            which=executables.get,
            probe=FakeProbe(),  # type: ignore[arg-type]
        )


if __name__ == "__main__":
    unittest.main()
