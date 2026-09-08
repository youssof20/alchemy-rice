from __future__ import annotations

import unittest

from alchemy.domain.compatibility_database import PackageMapping
from alchemy.domain.dependencies import Candidate, TrustTier
from alchemy.platform.commands import CommandResult
from alchemy.platform.packages import CommandPackageProvider, PackageProviderFactory


class FakeRunner:
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.calls: list[tuple[str, ...]] = []

    def run(self, arguments: tuple[str, ...], *, timeout: float = 3.0) -> CommandResult:
        del timeout
        self.calls.append(tuple(arguments))
        return self.result


def _mapping(provider: str = "pacman") -> PackageMapping:
    return PackageMapping(
        "qt.style.kvantum",
        "arch",
        provider,
        "kvantum",
        "official",
        "https://example.com/package",
        "confirmed_working",
        "2026-09-08",
    )


class PackageProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_plans_are_explicit_and_provider_specific(self) -> None:
        expected = {
            "pacman": ("pkexec", "pacman", "-S", "--needed", "--noconfirm", "--", "kvantum"),
            "dnf": ("pkexec", "dnf", "-y", "install", "kvantum"),
            "apt": (
                "pkexec",
                "apt-get",
                "install",
                "--yes",
                "--no-install-recommends",
                "kvantum",
            ),
            "zypper": (
                "pkexec",
                "zypper",
                "--non-interactive",
                "install",
                "--no-recommends",
                "kvantum",
            ),
        }
        for provider_id, arguments in expected.items():
            with self.subTest(provider=provider_id):
                runner = FakeRunner(CommandResult((), 1, "", ""))
                provider = CommandPackageProvider(
                    provider_id,
                    runner,
                    executable=f"/usr/bin/{'apt-get' if provider_id == 'apt' else provider_id}",
                    query_executable="/usr/bin/query",
                    pkexec="/usr/bin/pkexec",
                    mappings=(_mapping(provider_id),),
                )
                candidate = Candidate(
                    provider_id,
                    "kvantum",
                    "https://example.com/package",
                    TrustTier.DISTRIBUTION,
                    "official",
                    "confirmed_working",
                    "2026-09-08",
                )

                plan = await provider.plan_install(candidate)

                self.assertEqual(plan.arguments, arguments)
                self.assertTrue(plan.requires_privilege)
                self.assertTrue(plan.automatable)

    async def test_pacman_inspection_parses_installed_version(self) -> None:
        runner = FakeRunner(CommandResult((), 0, "kvantum 1.1.8-1\n", ""))
        provider = CommandPackageProvider(
            "pacman",
            runner,
            executable="/usr/bin/pacman",
            query_executable="/usr/bin/pacman",
            pkexec="/usr/bin/pkexec",
            mappings=(_mapping(),),
        )
        candidate = Candidate(
            "pacman",
            "kvantum",
            "https://example.com/package",
            TrustTier.DISTRIBUTION,
            "official",
            "confirmed_working",
            "2026-09-08",
        )

        info = await provider.inspect(candidate)

        self.assertTrue(info.installed)
        self.assertEqual(info.version, "1.1.8-1")
        self.assertEqual(runner.calls, [("/usr/bin/pacman", "-Q", "--", "kvantum")])

    async def test_aur_plan_is_visible_but_not_automatable(self) -> None:
        provider = CommandPackageProvider(
            "aur",
            FakeRunner(CommandResult((), 1, "", "")),
            executable="/usr/bin/paru",
            query_executable="/usr/bin/pacman",
            pkexec=None,
            mappings=(_mapping("aur"),),
        )
        candidate = Candidate(
            "aur",
            "kvantum-git",
            "https://aur.archlinux.org/packages/kvantum-git",
            TrustTier.COMMUNITY,
            "community",
            "confirmed_working",
            "2026-09-08",
        )

        plan = await provider.plan_install(candidate)

        self.assertFalse(plan.automatable)
        self.assertNotIn("sudo", plan.arguments)

    async def test_factory_rejects_package_tools_from_untrusted_paths(self) -> None:
        factory = PackageProviderFactory(
            FakeRunner(CommandResult((), 1, "", "")), lambda name: f"C:/temp/{name}.exe"
        )

        provider = factory.create("pacman", (_mapping(),))

        self.assertIsNone(provider)


if __name__ == "__main__":
    unittest.main()
