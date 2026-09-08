from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from alchemy.domain.capabilities import (
    CapabilityMatrix,
    ComponentCapability,
    EnvironmentReport,
    SettingObservation,
)
from alchemy.domain.capture import build_capture
from alchemy.domain.panels import PANEL_SPACER
from alchemy.domain.rice import load_rice
from alchemy.domain.sanitizer import SanitizationContext
from alchemy.services.creator_capture import CreatorCaptureService


def _capability(**changes: object) -> CapabilityMatrix:
    values: dict[str, object] = {
        "host_os": "linux",
        "plasma_version": "6.7.4",
        "session": "wayland",
        "desktop": "KDE",
        "login_manager": "sddm",
        "distro": "arch",
        "distro_version": "rolling",
        "package_manager": "pacman",
        "aur_helper": None,
        "portals": (),
        "plasma_apply": (),
        "union": ComponentCapability(None, None),
        "nix": ComponentCapability(False, False),
        "plasma_manager": ComponentCapability(False, False),
        "monitors": ("eDP-1",),
        "mixed_scale": False,
        "immutable_host": False,
        "apply_supported": True,
    }
    values.update(changes)
    return CapabilityMatrix(**values)  # type: ignore[arg-type]


def _metadata() -> dict[str, object]:
    return {
        "id": "github:example/rice:captured",
        "name": "Captured",
        "version": "1.0.0",
        "author": {"name": "Example", "url": "https://example.com/author"},
        "source": {
            "repo": "https://example.com/rice",
            "release": "v1.0.0",
            "commit": "a" * 40,
        },
    }


def _observations() -> tuple[SettingObservation, ...]:
    return (
        SettingObservation(
            "colors",
            "Color scheme",
            "BreezeDark",
            "kdeglobals [General] ColorScheme",
            True,
        ),
        SettingObservation(
            "cursor", "Cursor size", "36", "kcminputrc [Mouse] cursorSize", True
        ),
        SettingObservation(
            "cursor",
            "Cursor theme",
            "Breeze_Snow",
            "kcminputrc [Mouse] cursorTheme",
            True,
        ),
        SettingObservation(
            "icons", "Icon theme", "Papirus-Dark", "kdeglobals [Icons] Theme", True
        ),
        SettingObservation(
            "unknown", "Private app state", "ignored", "app.conf [State] recent", True
        ),
    )


def _panel_state(screen: int = 0) -> dict[str, object]:
    return {
        "screen_count": 1,
        "screens": [{"x": 0, "y": 0, "width": 1920, "height": 1080}],
        "panels": [
            {
                "screen": screen,
                "location": "bottom",
                "alignment": "center",
                "height": 44,
                "length_mode": "fill",
                "hiding": "none",
                "floating": True,
                "opacity": "adaptive",
                "widgets": [
                    "org.kde.plasma.kickoff",
                    PANEL_SPACER,
                    "org.kde.plasma.digitalclock",
                ],
            }
        ],
    }


class FakeProbe:
    def __init__(self, report: EnvironmentReport) -> None:
        self.report = report

    def inspect(self) -> EnvironmentReport:
        return self.report


class FakePanels:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = state

    async def inspect_panels(self) -> dict[str, object]:
        return self.state


class CaptureDomainTests(unittest.TestCase):
    def test_captures_only_allowlisted_visual_state_and_portable_panels(self) -> None:
        report = EnvironmentReport(_capability(), _observations(), ())
        result = build_capture(
            _metadata(),  # type: ignore[arg-type]
            report,
            panel_state=_panel_state(),  # type: ignore[arg-type]
            panel_error=None,
            excluded=frozenset({"wallpaper", "effects", "apps"}),
            sanitizer_context=SanitizationContext(username="localuser"),
        )

        self.assertTrue(result.export_ready)
        self.assertEqual(result.manifest["components"]["cursor"]["size"], 36)
        widgets = result.manifest["components"]["panels"]["panels"][0]["widgets"]
        self.assertEqual(
            widgets,
            [
                {"plugin": "org.kde.plasma.kickoff", "slot": "left"},
                {"plugin": "org.kde.plasma.digitalclock", "slot": "right"},
            ],
        )
        self.assertNotIn("unknown", result.manifest["components"])
        self.assertIn("setting_not_allowlisted", {item.code for item in result.findings})
        self.assertIn("component_provenance_unresolved", {item.code for item in result.findings})

    def test_unknown_screen_intent_blocks_panel_export(self) -> None:
        result = build_capture(
            _metadata(),  # type: ignore[arg-type]
            EnvironmentReport(_capability(), _observations(), ()),
            panel_state=_panel_state(screen=1),  # type: ignore[arg-type]
            panel_error=None,
            excluded=frozenset(),
            sanitizer_context=SanitizationContext(),
        )

        self.assertFalse(result.export_ready)
        self.assertNotIn("panels", result.manifest["components"])
        self.assertIn("panel_screen_intent_unknown", {item.code for item in result.findings})

    def test_third_party_widget_name_is_reviewable_but_blocks_export(self) -> None:
        state = _panel_state()
        state["panels"][0]["widgets"] = ["com.example.customclock"]  # type: ignore[index]
        result = build_capture(
            _metadata(),  # type: ignore[arg-type]
            EnvironmentReport(_capability(), _observations(), ()),
            panel_state=state,  # type: ignore[arg-type]
            panel_error=None,
            excluded=frozenset(),
            sanitizer_context=SanitizationContext(),
        )

        widgets = result.manifest["components"]["panels"]["panels"][0]["widgets"]
        self.assertEqual(widgets[0]["plugin"], "com.example.customclock")
        self.assertFalse(result.export_ready)
        self.assertIn("widget_provenance_unresolved", {item.code for item in result.findings})


class CreatorCaptureServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_exports_canonical_rice_without_applying_or_uploading(self) -> None:
        report = EnvironmentReport(_capability(), _observations()[:3], ())
        service = CreatorCaptureService(
            probe=FakeProbe(report),  # type: ignore[arg-type]
            panel_inspector=FakePanels(_panel_state()),  # type: ignore[arg-type]
            sanitizer_context=SanitizationContext(username="localuser"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "metadata.json"
            metadata.write_text(json.dumps(_metadata()), encoding="utf-8")
            destination = root / "captured.rice"

            result = await service.export(str(metadata), str(destination))
            loaded = load_rice(destination)

        self.assertEqual(result["action"], "captured")
        self.assertFalse(result["applied"])
        self.assertFalse(result["uploaded"])
        self.assertEqual(result["sha256"], loaded.sha256)

    async def test_refuses_capture_without_a_real_plasma_environment(self) -> None:
        report = EnvironmentReport(_capability(host_os="windows"), (), ())
        service = CreatorCaptureService(
            probe=FakeProbe(report),  # type: ignore[arg-type]
            panel_inspector=FakePanels(_panel_state()),  # type: ignore[arg-type]
        )
        with tempfile.TemporaryDirectory() as temporary:
            metadata = Path(temporary) / "metadata.json"
            metadata.write_text(json.dumps(_metadata()), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "active Linux KDE"):
                await service.draft(str(metadata))

    async def test_secret_in_metadata_withholds_draft_and_blocks_export(self) -> None:
        report = EnvironmentReport(_capability(), _observations()[:3], ())
        service = CreatorCaptureService(
            probe=FakeProbe(report),  # type: ignore[arg-type]
            panel_inspector=FakePanels(_panel_state()),  # type: ignore[arg-type]
            sanitizer_context=SanitizationContext(username="localuser"),
        )
        unsafe = _metadata()
        unsafe["author"] = {"name": "person@example.com"}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "metadata.json"
            metadata.write_text(json.dumps(unsafe), encoding="utf-8")
            destination = root / "captured.rice"

            draft = await service.draft(str(metadata))
            with self.assertRaisesRegex(ValueError, "email_address"):
                await service.export(str(metadata), str(destination))

            self.assertIsNone(draft.to_dict()["manifest"])
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
