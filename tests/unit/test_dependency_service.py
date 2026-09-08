from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alchemy.domain.capabilities import EnvironmentReport
from alchemy.domain.compatibility_database import (
    CompatibilityDatabase,
    CompatibilityEntry,
    PackageMapping,
    PlasmaEntry,
)
from alchemy.domain.dependencies import TrustTier, classify_trust
from alchemy.domain.rice import canonical_json_bytes
from alchemy.platform.commands import CommandResult
from alchemy.services.dependency_service import DependencyService
from tests.unit.test_rice_domain import capability, manifest_data


class FakeProbe:
    def __init__(self, **changes: object) -> None:
        self.report = EnvironmentReport(capability(**changes), (), ())

    def inspect(self) -> EnvironmentReport:
        return self.report


class InstallingRunner:
    def __init__(self, installed_version: str = "1.1.8-1") -> None:
        self.installed = False
        self.installed_version = installed_version
        self.calls: list[tuple[str, ...]] = []

    def run(self, arguments: tuple[str, ...], *, timeout: float = 3.0) -> CommandResult:
        del timeout
        argv = tuple(arguments)
        self.calls.append(argv)
        if argv[0] == "/usr/bin/pkexec":
            self.installed = True
            return CommandResult(argv, 0, "", "")
        if argv[:2] == ("/usr/bin/pacman", "-Q"):
            if self.installed:
                return CommandResult(argv, 0, f"kvantum {self.installed_version}\n", "")
            return CommandResult(argv, 1, "", "not installed")
        return CommandResult(argv, 1, "", "unexpected")


def _database(component_status: str = "unknown") -> CompatibilityDatabase:
    return CompatibilityDatabase(
        (PlasmaEntry(">=6.6,<6.9", "unknown", "Pending", "2026-09-08"),),
        (
            CompatibilityEntry(
                "qt.style.kvantum",
                ">=6.6,<6.9",
                component_status,
                "Test evidence",
                "2026-09-08",
            ),
        ),
        (
            PackageMapping(
                "qt.style.kvantum",
                "arch",
                "pacman",
                "kvantum",
                "official",
                "https://archlinux.org/packages/extra/x86_64/kvantum/",
                "confirmed_working",
                "2026-09-08",
            ),
        ),
    )


def _rice(dependency_source: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = manifest_data()
    payload["dependencies"] = [
        {
            "id": "kvantum-style-engine",
            "capability": "qt.style.kvantum",
            "component_type": "executable",
            "license": "GPL-3.0-or-later",
            "source": dependency_source
            or {"type": "distro_package", "package": "kvantum"},
        }
    ]
    return payload


class DependencyServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_trust_classification_never_calls_aur_official(self) -> None:
        self.assertEqual(
            classify_trust("distro_package", "official"), TrustTier.DISTRIBUTION
        )
        self.assertEqual(classify_trust("distro_package", "community"), TrustTier.COMMUNITY)
        self.assertEqual(
            classify_trust("distro_package", "official", "aur"), TrustTier.COMMUNITY
        )
        self.assertEqual(classify_trust("github_release", None), TrustTier.COMMUNITY)
        self.assertEqual(classify_trust("manual", None), TrustTier.MANUAL)

    async def test_resolve_then_install_uses_bound_plan_and_records_receipt(self) -> None:
        runner = InstallingRunner()
        executables = {
            "pacman": "/usr/bin/pacman",
            "pkexec": "/usr/bin/pkexec",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rice = root / "test.rice"
            rice.write_bytes(canonical_json_bytes(_rice()))
            service = DependencyService(
                probe=FakeProbe(),  # type: ignore[arg-type]
                database=_database(),
                state_root=root / "state",
                runner=runner,
                which=executables.get,
                now=lambda: datetime(2026, 9, 8, tzinfo=UTC),
            )

            report = await service.resolve(str(rice))
            resolution = report.dependencies[0]
            self.assertEqual(resolution.status, "missing")
            self.assertEqual(resolution.trust_tier, TrustTier.DISTRIBUTION)
            self.assertIsNotNone(resolution.plan_token)
            with self.assertRaisesRegex(RuntimeError, "resolve again"):
                await service.install(str(rice), resolution.dependency_id, "0" * 64)

            result = await service.install(
                str(rice), resolution.dependency_id, str(resolution.plan_token)
            )
            receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))

        self.assertEqual(result["action"], "installed")
        self.assertFalse(result["automatic_uninstall_on_revert"])
        self.assertTrue(receipt["installed_by_alchemy"])
        self.assertFalse(receipt["automatic_uninstall_on_revert"])
        self.assertTrue(any(call[0] == "/usr/bin/pkexec" for call in runner.calls))

    async def test_immutable_host_refuses_package_mutation(self) -> None:
        runner = InstallingRunner()
        with tempfile.TemporaryDirectory() as temporary:
            rice = Path(temporary) / "test.rice"
            rice.write_bytes(canonical_json_bytes(_rice()))
            service = DependencyService(
                probe=FakeProbe(immutable_host=True),  # type: ignore[arg-type]
                database=_database(),
                state_root=Path(temporary) / "state",
                runner=runner,
                which=lambda name: f"/usr/bin/{name}",
            )

            report = await service.resolve(str(rice))

        self.assertEqual(report.dependencies[0].status, "immutable_refused")
        self.assertEqual(runner.calls, [])

    async def test_non_linux_host_refuses_package_mutation(self) -> None:
        runner = InstallingRunner()
        with tempfile.TemporaryDirectory() as temporary:
            rice = Path(temporary) / "test.rice"
            rice.write_bytes(canonical_json_bytes(_rice()))
            service = DependencyService(
                probe=FakeProbe(host_os="windows"),  # type: ignore[arg-type]
                database=_database(),
                state_root=Path(temporary) / "state",
                runner=runner,
                which=lambda name: f"/usr/bin/{name}",
            )

            report = await service.resolve(str(rice))

        self.assertEqual(report.dependencies[0].status, "host_refused")
        self.assertEqual(runner.calls, [])

    async def test_manual_source_has_visible_tier_and_no_command(self) -> None:
        source = {"type": "manual", "url": "https://example.com/project"}
        with tempfile.TemporaryDirectory() as temporary:
            rice = Path(temporary) / "test.rice"
            rice.write_bytes(canonical_json_bytes(_rice(source)))
            service = DependencyService(
                probe=FakeProbe(),  # type: ignore[arg-type]
                database=_database(),
                state_root=Path(temporary) / "state",
                runner=InstallingRunner(),
                which=lambda _: None,
            )

            resolution = (await service.resolve(str(rice))).dependencies[0]

        self.assertEqual(resolution.status, "manual")
        self.assertEqual(resolution.trust_tier, TrustTier.MANUAL)
        self.assertEqual(resolution.declared_source["url"], "https://example.com/project")
        self.assertIsNone(resolution.command_plan)

    async def test_confirmed_breakage_requires_explicit_override(self) -> None:
        runner = InstallingRunner()
        executables = {
            "pacman": "/usr/bin/pacman",
            "pkexec": "/usr/bin/pkexec",
        }
        with tempfile.TemporaryDirectory() as temporary:
            rice = Path(temporary) / "test.rice"
            rice.write_bytes(canonical_json_bytes(_rice()))
            service = DependencyService(
                probe=FakeProbe(),  # type: ignore[arg-type]
                database=_database("confirmed_broken"),
                state_root=Path(temporary) / "state",
                runner=runner,
                which=executables.get,
            )

            blocked = await service.resolve(str(rice))
            allowed = await service.resolve(str(rice), allow_known_incompatible=True)

        self.assertEqual(blocked.dependencies[0].status, "blocked")
        self.assertIsNone(blocked.dependencies[0].command_plan)
        self.assertEqual(allowed.dependencies[0].status, "missing")
        self.assertIsNotNone(allowed.dependencies[0].command_plan)

    async def test_install_refuses_unverified_declared_version(self) -> None:
        runner = InstallingRunner("1.1.7-1")
        executables = {
            "pacman": "/usr/bin/pacman",
            "pkexec": "/usr/bin/pkexec",
        }
        source = {"type": "distro_package", "package": "kvantum", "version": "1.1.8"}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rice = root / "test.rice"
            rice.write_bytes(canonical_json_bytes(_rice(source)))
            service = DependencyService(
                probe=FakeProbe(),  # type: ignore[arg-type]
                database=_database(),
                state_root=root / "state",
                runner=runner,
                which=executables.get,
            )
            resolution = (await service.resolve(str(rice))).dependencies[0]

            with self.assertRaisesRegex(RuntimeError, "declared version"):
                await service.install(
                    str(rice), resolution.dependency_id, str(resolution.plan_token)
                )

            self.assertFalse((root / "state" / "dependency-installs").exists())


if __name__ == "__main__":
    unittest.main()
