from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from alchemy.drivers.wallpaper import WallpaperDriver
from alchemy.platform.commands import CommandResult

_FILL_MODES = {
    "stretch": 0,
    "preserveAspectFit": 1,
    "preserveAspectCrop": 2,
    "pad": 6,
}


class FakePlasmaShell:
    def __init__(self, state: list[dict[str, str | int]]) -> None:
        self.state = state
        self.scripts: list[str] = []

    def evaluate(self, script: str) -> str:
        self.scripts.append(script)
        return json.dumps(self.state)


class WallpaperRunner:
    def __init__(self, shell: FakePlasmaShell) -> None:
        self.shell = shell
        self.calls: list[tuple[str, ...]] = []

    def run(self, arguments: tuple[str, ...], *, timeout: float = 3.0) -> CommandResult:
        del timeout
        argv = tuple(arguments)
        self.calls.append(argv)
        if argv[0] != "/usr/bin/plasma-apply-wallpaperimage":
            return CommandResult(argv, 1, "", "unexpected command")
        fill_mode = _FILL_MODES[argv[2]]
        image = Path(argv[3]).resolve().as_uri()
        for desktop in self.shell.state:
            desktop.update(plugin="org.kde.image", image=image, fill_mode=fill_mode)
        return CommandResult(argv, 0, "", "")


class WallpaperDriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_uniform_multi_desktop_state_applies_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_image = root / "old wallpaper.png"
            new_image = root / "new wallpaper.png"
            old_image.touch()
            new_image.touch()
            state = [
                {
                    "plugin": "org.kde.image",
                    "image": old_image.resolve().as_uri(),
                    "fill_mode": 2,
                },
                {
                    "plugin": "org.kde.image",
                    "image": old_image.resolve().as_uri(),
                    "fill_mode": 2,
                },
            ]
            shell = FakePlasmaShell(state)
            runner = WallpaperRunner(shell)
            driver = WallpaperDriver(
                runner,
                shell,
                apply_tool="/usr/bin/plasma-apply-wallpaperimage",
                config_path=root / "appletsrc",
            )

            operation = (await driver.plan(str(new_image)))[0]
            await driver.apply(operation)

            self.assertTrue((await driver.verify(operation)).matched)
            self.assertEqual(
                operation.command,
                (
                    "/usr/bin/plasma-apply-wallpaperimage",
                    "--fill-mode",
                    "preserveAspectCrop",
                    str(new_image.resolve()),
                ),
            )
            await driver.rollback(operation)
            self.assertTrue((await driver.verify(operation, expected=operation.before)).matched)

    async def test_non_uniform_multi_desktop_state_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_image = root / "old.png"
            other_image = root / "other.png"
            new_image = root / "new.png"
            for image in (old_image, other_image, new_image):
                image.touch()
            shell = FakePlasmaShell(
                [
                    {
                        "plugin": "org.kde.image",
                        "image": old_image.resolve().as_uri(),
                        "fill_mode": 2,
                    },
                    {
                        "plugin": "org.kde.image",
                        "image": other_image.resolve().as_uri(),
                        "fill_mode": 2,
                    },
                ]
            )
            driver = WallpaperDriver(
                WallpaperRunner(shell),
                shell,
                apply_tool="/usr/bin/plasma-apply-wallpaperimage",
                config_path=root / "appletsrc",
            )

            with self.assertRaisesRegex(RuntimeError, "non-uniform"):
                await driver.plan(str(new_image))


if __name__ == "__main__":
    unittest.main()
