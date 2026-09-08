from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from alchemy.domain.app_adapters import canonical_app_json, render_owned_config
from alchemy.drivers.apps import AppConfigDriver
from tests.unit.test_app_adapters import app_fixtures


class AppDriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_apply_verify_and_rollback_use_only_owned_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            config = home / ".config" / "kitty" / "kitty.conf"
            config.parent.mkdir(parents=True)
            previous = {"format_version": 1, "font_size": 10}
            desired = app_fixtures()["kitty"]
            config.write_bytes(render_owned_config("kitty", previous))
            settings = home / "kitty.json"
            settings.write_text(json.dumps(desired), encoding="utf-8")
            driver = AppConfigDriver("kitty", config, home)

            operation = (await driver.plan(str(settings)))[0]
            token = driver.confirmation_token(operation)
            await driver.apply(operation)

            self.assertEqual(len(token), 64)
            self.assertTrue((await driver.verify(operation)).matched)
            self.assertEqual(driver.inspect()["settings"], desired)
            await driver.rollback(operation)
            self.assertEqual(driver.inspect()["settings"], previous)
            self.assertEqual(operation.command, ())

    async def test_mixed_existing_config_is_refused_before_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            config = home / ".config" / "kitty" / "kitty.conf"
            config.parent.mkdir(parents=True)
            config.write_text("font_size 11\nmap ctrl+x launch sh\n", encoding="utf-8")
            settings = home / "kitty.json"
            settings.write_text(
                canonical_app_json({"format_version": 1, "font_size": 12}),
                encoding="utf-8",
            )
            driver = AppConfigDriver("kitty", config, home)

            with self.assertRaisesRegex(ValueError, "allowlist"):
                await driver.plan(str(settings))


if __name__ == "__main__":
    unittest.main()
