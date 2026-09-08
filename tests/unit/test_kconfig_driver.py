from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alchemy.drivers.kconfig import KConfigDriver, KConfigSpec
from alchemy.drivers.registry import SPECS, DriverRegistry
from alchemy.platform.commands import CommandResult
from alchemy.platform.kde_notifications import RefreshAction


class FakeNotifier:
    def __init__(self) -> None:
        self.actions: list[RefreshAction] = []

    def refresh(self, action: RefreshAction) -> None:
        self.actions.append(action)


class StatefulKConfigRunner:
    def __init__(self, current: str | None) -> None:
        self.current = current
        self.calls: list[tuple[str, ...]] = []

    def run(self, arguments: tuple[str, ...], *, timeout: float = 3.0) -> CommandResult:
        del timeout
        argv = tuple(arguments)
        self.calls.append(argv)
        if argv[0] == "/usr/bin/kreadconfig6":
            return CommandResult(argv, 0, f"{self.current or ''}\n", "")
        if argv[0] == "/usr/bin/kwriteconfig6":
            self.current = argv[-1]
            return CommandResult(argv, 0, "", "")
        return CommandResult(argv, 1, "", "unexpected command")


class KConfigDriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_apply_verify_and_rollback_use_argument_vectors(self) -> None:
        runner = StatefulKConfigRunner("breeze")
        notifier = FakeNotifier()
        driver = KConfigDriver(
            KConfigSpec(
                "icons.theme",
                "kde.icons.theme",
                "icon theme",
                "kdeglobals",
                "Icons",
                "Theme",
                RefreshAction.ICON,
            ),
            runner,
            notifier,
            kreadconfig="/usr/bin/kreadconfig6",
            kwriteconfig="/usr/bin/kwriteconfig6",
            config_path=Path("/home/test/.config/kdeglobals"),
        )

        operation = (await driver.plan("Papirus-Dark"))[0]
        await driver.apply(operation)

        self.assertEqual(
            operation.command,
            (
                "/usr/bin/kwriteconfig6",
                "--file",
                "kdeglobals",
                "--group",
                "Icons",
                "--key",
                "Theme",
                "Papirus-Dark",
            ),
        )
        self.assertTrue((await driver.verify(operation)).matched)
        self.assertEqual(notifier.actions, [RefreshAction.ICON])
        await driver.rollback(operation)
        self.assertEqual(runner.current, "breeze")
        self.assertEqual(notifier.actions, [RefreshAction.ICON, RefreshAction.ICON])

    async def test_enumerated_value_is_validated_before_read(self) -> None:
        runner = StatefulKConfigRunner("Smart")
        driver = KConfigDriver(
            SPECS["kwin.placement"],
            runner,
            FakeNotifier(),
            kreadconfig="/usr/bin/kreadconfig6",
            kwriteconfig="/usr/bin/kwriteconfig6",
            config_path=Path("/home/test/.config/kwinrc"),
        )

        with self.assertRaisesRegex(ValueError, "must be one of"):
            await driver.plan("NearestCorner")

        self.assertEqual(runner.calls, [])

    async def test_cursor_size_is_bounded(self) -> None:
        runner = StatefulKConfigRunner("24")
        driver = KConfigDriver(
            SPECS["cursor.size"],
            runner,
            FakeNotifier(),
            kreadconfig="/usr/bin/kreadconfig6",
            kwriteconfig="/usr/bin/kwriteconfig6",
            config_path=Path("/home/test/.config/kcminputrc"),
        )

        with self.assertRaisesRegex(ValueError, "between 0 and 512"):
            await driver.plan("1024")

        self.assertEqual(runner.calls, [])

    def test_registry_exposes_reviewed_phase_two_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            registry = DriverRegistry(
                StatefulKConfigRunner(None),
                lambda name: f"/usr/bin/{name}",
                home=Path(temporary),
                notifier=FakeNotifier(),
            )

            self.assertEqual(
                set(registry.names()),
                {
                    "icons.theme",
                    "cursor.theme",
                    "cursor.size",
                    "plasma.theme",
                    "fonts.general",
                    "fonts.fixed",
                    "fonts.small",
                    "fonts.toolbar",
                    "fonts.menu",
                    "fonts.window_title",
                    "application_style.theme",
                    "decoration.plugin",
                    "decoration.theme",
                    "decoration.border_size",
                    "decoration.border_auto",
                    "kwin.placement",
                    "kwin.borderless_maximized",
                    "wallpaper.image",
                },
            )

    def test_registry_specs_match_reviewed_kconfig_locations(self) -> None:
        expected = {
            "icons.theme": ("kdeglobals", "Icons", "Theme"),
            "cursor.theme": ("kcminputrc", "Mouse", "cursorTheme"),
            "cursor.size": ("kcminputrc", "Mouse", "cursorSize"),
            "plasma.theme": ("plasmarc", "Theme", "name"),
            "fonts.general": ("kdeglobals", "General", "font"),
            "fonts.fixed": ("kdeglobals", "General", "fixed"),
            "fonts.small": ("kdeglobals", "General", "smallestReadableFont"),
            "fonts.toolbar": ("kdeglobals", "General", "toolBarFont"),
            "fonts.menu": ("kdeglobals", "General", "menuFont"),
            "fonts.window_title": ("kdeglobals", "WM", "activeFont"),
            "application_style.theme": ("kdeglobals", "KDE", "widgetStyle"),
            "decoration.plugin": (
                "kwinrc",
                "org.kde.kdecoration2",
                "library",
            ),
            "decoration.theme": (
                "kwinrc",
                "org.kde.kdecoration2",
                "theme",
            ),
            "decoration.border_size": (
                "kwinrc",
                "org.kde.kdecoration2",
                "BorderSize",
            ),
            "decoration.border_auto": (
                "kwinrc",
                "org.kde.kdecoration2",
                "BorderSizeAuto",
            ),
            "kwin.placement": ("kwinrc", "Windows", "Placement"),
            "kwin.borderless_maximized": (
                "kwinrc",
                "Windows",
                "BorderlessMaximizedWindows",
            ),
        }

        self.assertEqual(
            {name: (spec.config_file, spec.group, spec.key) for name, spec in SPECS.items()},
            expected,
        )

    async def test_registry_prefers_official_theme_apply_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runner = StatefulKConfigRunner("Breeze")
            registry = DriverRegistry(
                runner,
                lambda name: f"/usr/bin/{name}",
                home=Path(temporary),
                notifier=FakeNotifier(),
            )

            cursor = registry.create("cursor.theme")
            plasma = registry.create("plasma.theme")
            cursor_operation = (await cursor.plan("Breeze_Snow"))[0]
            plasma_operation = (await plasma.plan("breeze-dark"))[0]

            self.assertEqual(
                cursor_operation.command,
                ("/usr/bin/plasma-apply-cursortheme", "Breeze_Snow"),
            )
            self.assertEqual(
                plasma_operation.command,
                ("/usr/bin/plasma-apply-desktoptheme", "breeze-dark"),
            )


if __name__ == "__main__":
    unittest.main()
