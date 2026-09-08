from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from alchemy.domain.transactions import TransactionState
from alchemy.drivers.panels import PanelDriver
from alchemy.services.transaction_service import TransactionFailedError, TransactionService
from tests.unit.test_transaction_service import FakeProbe


def _captured_panel(plugin: str = "org.kde.plasma.digitalclock") -> dict[str, Any]:
    return {
        "panel_plugin": "org.kde.panel",
        "screen": 0,
        "location": "bottom",
        "alignment": "center",
        "floating": True,
        "floating_applets": False,
        "height": 44,
        "length_mode": "fill",
        "length": 1920,
        "minimum_length": 1920,
        "maximum_length": 1920,
        "offset": 0,
        "hiding": "none",
        "opacity": "adaptive",
        "config": {"/General": {"custom": "kept"}},
        "widgets": [{"plugin": plugin, "config": {"/Appearance": {"foo": "bar"}}}],
    }


class FakePanelShell:
    def __init__(self, state: dict[str, Any], known: list[str]) -> None:
        self.state = state
        self.known = known
        self.apply_scripts: list[str] = []

    def dump_layout(self) -> str:
        panels = []
        for panel in self.state["panels"]:
            panels.append(
                {
                    "location": panel["location"],
                    "height": panel["height"] / 10,
                    "maximumLength": panel["maximum_length"],
                    "minimumLength": panel["minimum_length"],
                    "offset": panel["offset"],
                    "alignment": panel["alignment"],
                    "hiding": "normal" if panel["hiding"] == "none" else panel["hiding"],
                    "opacity": panel["opacity"],
                    "lengthMode": panel["length_mode"],
                    "config": panel.get("config", {}),
                    "applets": [
                        {"plugin": widget["plugin"], "config": widget.get("config", {})}
                        for widget in panel["widgets"]
                    ],
                }
            )
        layout = {"serializationFormatVersion": "1", "panels": panels, "desktops": []}
        return (
            "var plasma = getApiVersion(1);\n\nvar layout = "
            + json.dumps(layout)
            + ";\n\nplasma.loadSerializedLayout(layout);\n"
        )

    def evaluate(self, script: str) -> str:
        if "api_version: 1" in script:
            metadata = {
                "api_version": 1,
                "screens": self.state["screens"],
                "known_widget_types": self.known,
                "known_panel_types": ["org.kde.panel"],
                "panels": [
                    {
                        "panel_plugin": panel["panel_plugin"],
                        "screen": panel["screen"],
                        "floating": panel["floating"],
                        "floating_applets": panel["floating_applets"],
                        "height": panel["height"],
                        "length": panel["length"],
                        "minimum_length": panel["minimum_length"],
                        "maximum_length": panel["maximum_length"],
                        "offset": panel["offset"],
                        "widgets": [
                            {"plugin": widget["plugin"], "index": index}
                            for index, widget in enumerate(panel["widgets"])
                        ],
                    }
                    for panel in self.state["panels"]
                ],
            }
            return json.dumps(metadata)
        self.apply_scripts.append(script)
        marker = "var layout = "
        end_marker = ";\nvar availableWidgets"
        start = script.index(marker) + len(marker)
        incoming = json.loads(script[start : script.index(end_marker, start)])
        self.state["panels"] = [self._as_captured(panel) for panel in incoming["panels"]]
        return json.dumps({"ok": True, "panels": len(incoming["panels"])})

    @staticmethod
    def _as_captured(panel: dict[str, Any]) -> dict[str, Any]:
        height = panel["height"]
        length = panel.get("length") or 1920
        return {
            "panel_plugin": panel.get("panel_plugin", "org.kde.panel"),
            "screen": panel["screen"],
            "location": panel["location"],
            "alignment": panel["alignment"],
            "floating": panel["floating"],
            "floating_applets": panel.get("floating_applets", False),
            "height": height,
            "length_mode": panel["length_mode"],
            "length": length,
            "minimum_length": panel.get("minimum_length", length),
            "maximum_length": panel.get("maximum_length", length),
            "offset": panel.get("offset", 0),
            "hiding": panel["hiding"],
            "opacity": panel["opacity"],
            "config": panel.get("config", {}),
            "widgets": [
                {"plugin": widget["plugin"], "config": widget.get("config", {})}
                for widget in panel["widgets"]
            ],
        }


class IgnoreOneApplyShell(FakePanelShell):
    def __init__(self, state: dict[str, Any], known: list[str]) -> None:
        super().__init__(state, known)
        self.ignore_next_apply = False

    def evaluate(self, script: str) -> str:
        if "api_version: 1" not in script and self.ignore_next_apply:
            self.ignore_next_apply = False
            self.apply_scripts.append(script)
            return json.dumps({"ok": True, "panels": 1})
        return super().evaluate(script)


class PanelDriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_previews_mapping_applies_verifies_and_rolls_back(self) -> None:
        known = [
            "org.kde.plasma.digitalclock",
            "org.kde.plasma.kickoff",
            "org.kde.plasma.icontasks",
            "org.kde.plasma.panelspacer",
        ]
        state = {
            "screens": [{"x": 0, "y": 0, "width": 1920, "height": 1080}],
            "panels": [_captured_panel()],
        }
        shell = FakePanelShell(state, known)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "layout.json"
            path.write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "panels": [
                            {
                                "logical_id": "main",
                                "location": "top",
                                "height": {"unit": "screen_percent", "value": 4},
                                "widgets": [
                                    {"plugin": "org.kde.plasma.kickoff", "slot": "left"},
                                    {"plugin": "org.kde.plasma.icontasks", "slot": "center"},
                                    {
                                        "plugin": "org.kde.plasma.digitalclock",
                                        "slot": "right",
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            driver = PanelDriver(shell, config_path=Path(temporary) / "appletsrc")

            operation = (await driver.plan(str(path)))[0]
            preview = driver.public_plan(operation)
            self.assertEqual(preview["screen_mapping"][0]["screen"], 0)
            self.assertNotIn("kept", json.dumps(preview))
            self.assertNotIn("foo", json.dumps(preview))
            await driver.apply(operation)
            self.assertTrue((await driver.verify(operation)).matched)
            await driver.rollback(operation)
            self.assertTrue((await driver.verify(operation, expected=operation.before)).matched)
            self.assertIn('"custom": "kept"', shell.apply_scripts[-1])

    async def test_missing_widget_dependency_refuses_before_apply(self) -> None:
        state = {
            "screens": [{"x": 0, "y": 0, "width": 1920, "height": 1080}],
            "panels": [_captured_panel()],
        }
        shell = FakePanelShell(state, ["org.kde.plasma.digitalclock"])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "layout.json"
            path.write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "panels": [
                            {
                                "logical_id": "main",
                                "location": "bottom",
                                "height": {"unit": "pixels", "value": 44},
                                "widgets": [
                                    {"plugin": "org.example.thirdparty", "slot": "left"}
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            driver = PanelDriver(shell, config_path=Path(temporary) / "appletsrc")

            with self.assertRaisesRegex(RuntimeError, "org.example.thirdparty"):
                await driver.plan(str(path))
            self.assertEqual(shell.apply_scripts, [])

    async def test_transaction_verification_failure_restores_captured_layout(self) -> None:
        known = ["org.kde.plasma.digitalclock", "org.kde.plasma.kickoff"]
        old_panel = _captured_panel()
        state = {
            "screens": [{"x": 0, "y": 0, "width": 1920, "height": 1080}],
            "panels": [old_panel],
        }
        shell = IgnoreOneApplyShell(state, known)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            config_root = home / ".config"
            config_root.mkdir(parents=True)
            (config_root / "plasma-org.kde.plasma.desktop-appletsrc").write_text(
                "fixture\n", encoding="utf-8"
            )
            layout = root / "layout.json"
            layout.write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "panels": [
                            {
                                "logical_id": "main",
                                "location": "top",
                                "height": {"unit": "pixels", "value": 48},
                                "widgets": [
                                    {"plugin": "org.kde.plasma.kickoff", "slot": "left"}
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            service = TransactionService(
                home=home,
                config_root=config_root,
                state_root=root / "state",
                data_root=root / "data",
                which=lambda _name: None,
                probe=FakeProbe(),  # type: ignore[arg-type]
                plasma_shell=shell,
            )
            plan = await service.plan_panels(str(layout))
            shell.ignore_next_apply = True

            with self.assertRaisesRegex(TransactionFailedError, "previous state was restored"):
                await service.apply_panels(str(layout), str(plan["confirmation_token"]))

            latest = service.journals.latest()
            assert latest is not None
            self.assertEqual(latest["state"], TransactionState.ROLLED_BACK.value)
            self.assertEqual(shell.state["panels"], [old_panel])

    async def test_changed_screen_mapping_invalidates_confirmation_token(self) -> None:
        known = ["org.kde.plasma.digitalclock", "org.kde.plasma.kickoff"]
        state = {
            "screens": [{"x": 0, "y": 0, "width": 1920, "height": 1080}],
            "panels": [_captured_panel()],
        }
        shell = FakePanelShell(state, known)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            config_root = home / ".config"
            config_root.mkdir(parents=True)
            layout = root / "layout.json"
            layout.write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "panels": [
                            {
                                "logical_id": "main",
                                "location": "top",
                                "height": {"unit": "screen_percent", "value": 4},
                                "widgets": [
                                    {"plugin": "org.kde.plasma.kickoff", "slot": "left"}
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            service = TransactionService(
                home=home,
                config_root=config_root,
                state_root=root / "state",
                data_root=root / "data",
                which=lambda _name: None,
                probe=FakeProbe(),  # type: ignore[arg-type]
                plasma_shell=shell,
            )
            plan = await service.plan_panels(str(layout))
            shell.state["screens"][0]["height"] = 1440

            with self.assertRaisesRegex(TransactionFailedError, "run plan-panels again"):
                await service.apply_panels(str(layout), str(plan["confirmation_token"]))

            self.assertEqual(shell.apply_scripts, [])
            self.assertEqual(service.journals.all(), ())


if __name__ == "__main__":
    unittest.main()
