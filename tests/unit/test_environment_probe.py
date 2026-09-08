from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alchemy.platform.commands import CommandResult
from alchemy.services.environment_probe import EnvironmentProbe, extract_version, parse_os_release


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], CommandResult]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def run(self, arguments: tuple[str, ...], *, timeout: float = 3.0) -> CommandResult:
        del timeout
        argv = tuple(arguments)
        self.calls.append(argv)
        return self.responses.get(argv, CommandResult(argv, 0, "", ""))


class EnvironmentProbeTests(unittest.TestCase):
    def test_parse_os_release_handles_quotes_and_comments(self) -> None:
        parsed = parse_os_release('# comment\nID="arch"\nVERSION_ID=rolling\nNAME="Arch Linux"\n')

        self.assertEqual(parsed["ID"], "arch")
        self.assertEqual(parsed["VERSION_ID"], "rolling")
        self.assertEqual(parsed["NAME"], "Arch Linux")

    def test_extract_version_ignores_product_text(self) -> None:
        self.assertEqual(extract_version("plasmashell 6.7.4\n"), "6.7.4")
        self.assertIsNone(extract_version("plasmashell unknown"))

    def test_probe_collects_capabilities_without_enabling_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "etc").mkdir()
            (root / "etc" / "os-release").write_text(
                'ID="arch"\nVERSION_ID="rolling"\n', encoding="utf-8"
            )
            executables = {
                "plasmashell": "/usr/bin/plasmashell",
                "pacman": "/usr/bin/pacman",
                "paru": "/usr/bin/paru",
                "kreadconfig6": "/usr/bin/kreadconfig6",
                "plasma-apply-colorscheme": "/usr/bin/plasma-apply-colorscheme",
                "kscreen-doctor": "/usr/bin/kscreen-doctor",
                "gdbus": "/usr/bin/gdbus",
            }
            runner = FakeRunner(
                {
                    ("/usr/bin/plasmashell", "--version"): CommandResult(
                        ("/usr/bin/plasmashell", "--version"), 0, "plasmashell 6.7.4\n", ""
                    ),
                    ("/usr/bin/kscreen-doctor", "-o"): CommandResult(
                        ("/usr/bin/kscreen-doctor", "-o"),
                        0,
                        "Output: 1 eDP-1 enabled connected primary\n  Scale: 1.25\n"
                        "Output: 2 HDMI-A-1 enabled connected\n  Scale: 1\n",
                        "",
                    ),
                    (
                        "/usr/bin/gdbus",
                        "introspect",
                        "--session",
                        "--dest",
                        "org.freedesktop.portal.Desktop",
                        "--object-path",
                        "/org/freedesktop/portal/desktop",
                    ): CommandResult(
                        ("/usr/bin/gdbus", "introspect"),
                        0,
                        "interface org.freedesktop.portal.Screenshot { ... }",
                        "",
                    ),
                }
            )
            probe = EnvironmentProbe(
                runner=runner,
                environ={
                    "XDG_SESSION_TYPE": "wayland",
                    "XDG_CURRENT_DESKTOP": "KDE",
                    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
                },
                which=executables.get,
                root=root,
                home=root / "home" / "tester",
                host_os="linux",
            )

            report = probe.inspect()

        capabilities = report.capabilities
        self.assertEqual(capabilities.plasma_version, "6.7.4")
        self.assertEqual(capabilities.session, "wayland")
        self.assertEqual(capabilities.distro, "arch")
        self.assertEqual(capabilities.package_manager, "pacman")
        self.assertEqual(capabilities.aur_helper, "paru")
        self.assertEqual(capabilities.monitors, ("eDP-1", "HDMI-A-1"))
        self.assertTrue(capabilities.mixed_scale)
        self.assertIn("colorscheme", capabilities.plasma_apply)
        self.assertIn("screenshot", capabilities.portals)
        self.assertFalse(capabilities.apply_supported)
        self.assertEqual(len(report.settings), 9)

    def test_non_linux_probe_is_explicitly_read_only(self) -> None:
        report = EnvironmentProbe(
            runner=FakeRunner({}),
            environ={},
            which=lambda _: None,
            root=Path("Z:/does-not-exist"),
            host_os="windows",
        ).inspect()

        self.assertFalse(report.capabilities.apply_supported)
        self.assertTrue(any("requires Linux" in warning for warning in report.warnings))
        self.assertTrue(all(not setting.available for setting in report.settings))


if __name__ == "__main__":
    unittest.main()
