from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from alchemy.domain.transactions import TransactionState
from alchemy.services.transaction_service import TransactionFailedError, TransactionService
from tests.unit.test_app_adapters import app_fixtures
from tests.unit.test_transaction_service import FakeProbe


class AppTransactionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_app_apply_and_revert_snapshot_an_initially_absent_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            settings = root / "kitty.json"
            settings.write_text(json.dumps(app_fixtures()["kitty"]), encoding="utf-8")
            service = self._service(root, home)

            plan = await service.plan_app("kitty", str(settings))
            committed = await service.apply_app(
                "kitty", str(settings), str(plan["plan_token"])
            )

            assert committed is not None
            self.assertEqual(committed["state"], TransactionState.COMMITTED.value)
            config = home / ".config" / "kitty" / "kitty.conf"
            self.assertTrue(config.is_file())
            self.assertEqual(service.inspect_app("kitty")["settings"], app_fixtures()["kitty"])
            reverted = await service.revert_last()
            self.assertEqual(reverted["state"], TransactionState.ROLLED_BACK.value)
            self.assertFalse(config.exists())

    async def test_app_revert_restores_exact_previous_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            config = home / ".config" / "kitty" / "kitty.conf"
            config.parent.mkdir(parents=True)
            original = b"# keep this comment\nfont_size 10.5\nbackground #101010\n"
            config.write_bytes(original)
            settings = root / "kitty.json"
            settings.write_text(json.dumps(app_fixtures()["kitty"]), encoding="utf-8")
            service = self._service(root, home)

            plan = await service.plan_app("kitty", str(settings))
            await service.apply_app("kitty", str(settings), str(plan["plan_token"]))
            await service.revert_last()

            self.assertEqual(config.read_bytes(), original)

    async def test_app_plan_token_detects_changed_requested_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            settings = root / "starship.json"
            settings.write_text(json.dumps(app_fixtures()["starship"]), encoding="utf-8")
            service = self._service(root, home)
            plan = await service.plan_app("starship", str(settings))
            changed = {"format_version": 1, "add_newline": True}
            settings.write_text(json.dumps(changed), encoding="utf-8")

            with self.assertRaisesRegex(TransactionFailedError, "changed after preview"):
                await service.apply_app(
                    "starship", str(settings), str(plan["plan_token"])
                )

            self.assertFalse((home / ".config" / "starship.toml").exists())

    async def test_app_plan_requires_installed_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            settings = root / "fastfetch.json"
            settings.write_text(json.dumps(app_fixtures()["fastfetch"]), encoding="utf-8")
            service = TransactionService(
                home=home,
                config_root=home / ".config",
                state_root=root / "state",
                data_root=root / "data",
                which=lambda _name: None,
                probe=FakeProbe(),  # type: ignore[arg-type]
            )

            with self.assertRaisesRegex(TransactionFailedError, "not installed"):
                await service.plan_app("fastfetch", str(settings))

    @staticmethod
    def _service(root: Path, home: Path) -> TransactionService:
        return TransactionService(
            home=home,
            config_root=home / ".config",
            state_root=root / "state",
            data_root=root / "data",
            which=lambda name: f"/usr/bin/{name}",
            probe=FakeProbe(),  # type: ignore[arg-type]
        )


if __name__ == "__main__":
    unittest.main()
