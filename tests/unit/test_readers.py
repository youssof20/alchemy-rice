from __future__ import annotations

import unittest

from alchemy.drivers.readers import KConfigSettingReader
from alchemy.platform.commands import CommandResult


class FakeRunner:
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.arguments: tuple[str, ...] | None = None

    def run(self, arguments: tuple[str, ...], *, timeout: float = 3.0) -> CommandResult:
        del timeout
        self.arguments = tuple(arguments)
        return self.result


class KConfigSettingReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = KConfigSettingReader(
            "colors", "Color scheme", "kdeglobals", "General", "ColorScheme"
        )

    def test_passes_each_command_argument_separately(self) -> None:
        runner = FakeRunner(CommandResult(("kreadconfig6",), 0, "BreezeDark\n", ""))

        observation = self.reader.read(runner, "/usr/bin/kreadconfig6")

        self.assertEqual(observation.value, "BreezeDark")
        self.assertEqual(
            runner.arguments,
            (
                "/usr/bin/kreadconfig6",
                "--file",
                "kdeglobals",
                "--group",
                "General",
                "--key",
                "ColorScheme",
            ),
        )

    def test_missing_kreadconfig_is_reported_without_running_a_command(self) -> None:
        runner = FakeRunner(CommandResult((), 0, "", ""))

        observation = self.reader.read(runner, None)

        self.assertFalse(observation.available)
        self.assertIn("not available", observation.detail or "")
        self.assertIsNone(runner.arguments)

    def test_command_failure_is_observable(self) -> None:
        runner = FakeRunner(CommandResult(("kreadconfig6",), 1, "", "bad config"))

        observation = self.reader.read(runner, "kreadconfig6")

        self.assertFalse(observation.available)
        self.assertEqual(observation.detail, "bad config")


if __name__ == "__main__":
    unittest.main()
