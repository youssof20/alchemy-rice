from __future__ import annotations

import os
import shutil
import sys
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alchemy.domain.compatibility_database import CompatibilityDatabase, PackageMapping
from alchemy.domain.dependencies import (
    Candidate,
    CommandPlan,
    DependencyReport,
    DependencyResolution,
    PackageInfo,
    TrustTier,
    bind_plan_token,
    classify_trust,
)
from alchemy.domain.rice import RiceManifest, load_rice, verify_sha256
from alchemy.platform.atomic import write_json_atomic
from alchemy.platform.commands import CommandRunner, Runner
from alchemy.platform.locking import MutationLock
from alchemy.platform.packages import PackageProvider, PackageProviderFactory
from alchemy.services.environment_probe import EnvironmentProbe

Now = Callable[[], datetime]


class DependencyService:
    """Resolve and separately install declared rice dependencies."""

    def __init__(
        self,
        *,
        probe: EnvironmentProbe | None = None,
        database: CompatibilityDatabase | None = None,
        database_root: Path | None = None,
        state_root: Path | None = None,
        runner: Runner | None = None,
        which: Callable[[str], str | None] | None = None,
        now: Now | None = None,
    ) -> None:
        self.probe = probe or EnvironmentProbe()
        self.database = database or CompatibilityDatabase.load(
            database_root or _default_database_root()
        )
        self.state_root = state_root or _xdg_state_root() / "alchemy"
        self.runner = runner or CommandRunner()
        self.which = which or shutil.which
        self.providers = PackageProviderFactory(self.runner, self.which)
        self.now = now or (lambda: datetime.now(UTC))

    async def resolve(
        self,
        path: str,
        *,
        expected_sha256: str | None = None,
        allow_known_incompatible: bool = False,
    ) -> DependencyReport:
        manifest = load_rice(path)
        verify_sha256(manifest.sha256, expected_sha256)
        return await self._resolve_manifest(
            manifest, allow_known_incompatible=allow_known_incompatible
        )

    async def install(
        self,
        path: str,
        dependency_id: str,
        plan_token: str,
        *,
        expected_sha256: str | None = None,
        allow_known_incompatible: bool = False,
    ) -> dict[str, Any]:
        with MutationLock(self.state_root / "apply.lock"):
            manifest = load_rice(path)
            verify_sha256(manifest.sha256, expected_sha256)
            report = await self._resolve_manifest(
                manifest, allow_known_incompatible=allow_known_incompatible
            )
            resolution = _dependency_by_id(report, dependency_id)
            if resolution.status == "installed":
                return {
                    "action": "no_change",
                    "dependency_id": dependency_id,
                    "installed": True,
                    "applied_config": False,
                }
            if resolution.plan_token != plan_token:
                raise RuntimeError(
                    "Dependency state or install plan changed; run dependency-resolve again"
                )
            if (
                resolution.candidate is None
                or resolution.command_plan is None
                or not resolution.command_plan.automatable
            ):
                raise RuntimeError("Dependency requires manual installation after source review")
            provider = self._provider_for(resolution.candidate.provider)
            installed = await provider.install(resolution.candidate)
            if not _version_satisfies(
                installed.version, resolution.declared_source.get("version")
            ):
                raise RuntimeError(
                    "Package installation completed but the declared version was not verified"
                )
            receipt_path = self._record_install(manifest, resolution, installed)
            return {
                "action": "installed",
                "rice_identity": manifest.identity,
                "rice_sha256": manifest.sha256,
                "dependency_id": resolution.dependency_id,
                "provider": resolution.candidate.provider,
                "package": resolution.candidate.package,
                "version": installed.version,
                "trust_tier": resolution.trust_tier.value,
                "trust_label": resolution.trust_tier.label,
                "receipt": str(receipt_path),
                "installed_by_alchemy": True,
                "automatic_uninstall_on_revert": False,
                "applied_config": False,
            }

    async def _resolve_manifest(
        self, manifest: RiceManifest, *, allow_known_incompatible: bool
    ) -> DependencyReport:
        environment = self.probe.inspect().capabilities
        manager = _normalized_manager(environment.package_manager)
        plasma_status = self.database.plasma_status(environment.plasma_version)
        plasma_evidence = tuple(
            item.to_dict()
            for item in self.database.plasma_evidence(environment.plasma_version)
        )
        resolutions: list[DependencyResolution] = []
        for dependency in manifest.data["dependencies"]:
            resolution = await self._resolve_dependency(
                dependency,
                host_os=environment.host_os,
                distro=environment.distro,
                manager=manager,
                aur_helper=environment.aur_helper,
                plasma_version=environment.plasma_version,
                immutable=bool(environment.immutable_host or environment.nix.active),
                allow_known_incompatible=allow_known_incompatible,
            )
            resolutions.append(
                bind_plan_token(
                    manifest.sha256,
                    resolution,
                    distro=environment.distro,
                    package_manager=manager,
                )
            )
        return DependencyReport(
            manifest.identity,
            manifest.sha256,
            environment.distro,
            manager,
            environment.immutable_host,
            plasma_status,
            plasma_evidence,
            tuple(resolutions),
        )

    async def _resolve_dependency(
        self,
        dependency: dict[str, Any],
        *,
        host_os: str,
        distro: str | None,
        manager: str | None,
        aur_helper: str | None,
        plasma_version: str | None,
        immutable: bool,
        allow_known_incompatible: bool,
    ) -> DependencyResolution:
        source = dependency["source"]
        source_type = source["type"]
        compatibility = self.database.component_status(
            dependency["capability"], plasma_version
        )
        evidence = tuple(
            item.to_dict()
            for item in self.database.component_evidence(
                dependency["capability"], plasma_version
            )
        )
        issues = _compatibility_issues(compatibility, allow_known_incompatible)
        if compatibility in {"confirmed_broken", "upstream_unsupported"} and not (
            allow_known_incompatible
        ):
            return _resolution(
                dependency,
                "blocked",
                classify_trust(source_type, None),
                compatibility,
                issues,
                compatibility_evidence=evidence,
            )
        if source_type != "distro_package":
            tier = classify_trust(source_type, None)
            issues.append("This source is not eligible for automatic package installation")
            return _resolution(
                dependency,
                "manual",
                tier,
                compatibility,
                issues,
                compatibility_evidence=evidence,
            )
        if host_os != "linux":
            issues.append("Host package installation is supported only on Linux")
            return _resolution(
                dependency,
                "host_refused",
                classify_trust(source_type, None),
                compatibility,
                issues,
                compatibility_evidence=evidence,
            )
        if immutable:
            issues.append("Host package mutation is refused on immutable or Nix-managed systems")
            return _resolution(
                dependency,
                "immutable_refused",
                classify_trust(source_type, None),
                compatibility,
                issues,
                compatibility_evidence=evidence,
            )
        mapping = self.database.package_mapping(dependency["capability"], distro)
        if mapping is None:
            issues.append("No reviewed package mapping exists for this distro and capability")
            return _resolution(
                dependency,
                "unresolved",
                TrustTier.MANUAL,
                compatibility,
                issues,
                compatibility_evidence=evidence,
            )
        tier = classify_trust(source_type, mapping.repository, mapping.provider)
        if mapping.status != "confirmed_working":
            issues.append("The package mapping is not confirmed available")
            return _resolution(
                dependency,
                "unresolved",
                tier,
                compatibility,
                issues,
                compatibility_evidence=evidence,
            )
        if not _provider_matches(mapping, manager, aur_helper):
            issues.append("The mapped package provider is not active in this environment")
            return _resolution(
                dependency,
                "provider_unavailable",
                tier,
                compatibility,
                issues,
                compatibility_evidence=evidence,
            )
        provider = self.providers.create(mapping.provider, self.database.package_mappings)
        if provider is None:
            issues.append("The package provider or its read-only query tool is unavailable")
            return _resolution(
                dependency,
                "provider_unavailable",
                tier,
                compatibility,
                issues,
                compatibility_evidence=evidence,
            )
        candidates = await provider.search(dependency["capability"])
        candidate = next(
            (item for item in candidates if item.package == mapping.package), None
        )
        if candidate is None:
            issues.append("The package provider did not return the reviewed candidate")
            return _resolution(
                dependency,
                "unresolved",
                tier,
                compatibility,
                issues,
                compatibility_evidence=evidence,
            )
        installed = await provider.inspect(candidate)
        required_version = source.get("version")
        if installed.installed and _version_satisfies(installed.version, required_version):
            return _resolution(
                dependency,
                "installed",
                tier,
                compatibility,
                issues,
                compatibility_evidence=evidence,
                candidate=candidate,
                installed=installed,
            )
        status = "version_mismatch" if installed.installed else "missing"
        if installed.installed:
            issues.append("The installed package version does not match the declared version")
        plan = await provider.plan_install(candidate)
        if tier != TrustTier.DISTRIBUTION:
            plan = replace(plan, automatable=False)
            issues.append("Third-party packaging requires manual source review")
        if not plan.automatable and mapping.provider != "aur":
            issues.append("pkexec is unavailable; privileged installation cannot be started")
        return _resolution(
            dependency,
            status,
            tier,
            compatibility,
            issues,
            compatibility_evidence=evidence,
            candidate=candidate,
            installed=installed,
            command_plan=plan,
        )

    def _provider_for(self, provider_id: str) -> PackageProvider:
        provider = self.providers.create(provider_id, self.database.package_mappings)
        if provider is None:
            raise RuntimeError("Package provider became unavailable; resolve again")
        return provider

    def _record_install(
        self,
        manifest: RiceManifest,
        resolution: DependencyResolution,
        installed: PackageInfo,
    ) -> Path:
        assert resolution.candidate is not None
        receipt = {
            "receipt_version": 1,
            "receipt_id": str(uuid.uuid4()),
            "recorded_at": self.now().astimezone(UTC).isoformat(),
            "rice": {"identity": manifest.identity, "sha256": manifest.sha256},
            "dependency_id": resolution.dependency_id,
            "capability": resolution.capability,
            "provider": resolution.candidate.provider,
            "package": resolution.candidate.package,
            "version": installed.version,
            "trust_tier": resolution.trust_tier.value,
            "installed_by_alchemy": True,
            "automatic_uninstall_on_revert": False,
        }
        path = self.state_root / "dependency-installs" / f"{receipt['receipt_id']}.json"
        write_json_atomic(path, receipt)
        return path


def _resolution(
    dependency: dict[str, Any],
    status: str,
    trust_tier: TrustTier,
    compatibility: str,
    issues: list[str],
    *,
    compatibility_evidence: tuple[dict[str, str], ...] = (),
    candidate: Candidate | None = None,
    installed: PackageInfo | None = None,
    command_plan: CommandPlan | None = None,
) -> DependencyResolution:
    return DependencyResolution(
        dependency["id"],
        dependency["capability"],
        dependency["component_type"],
        dependency["license"],
        dependency["source"],
        status,
        trust_tier,
        candidate,
        installed,
        command_plan,
        None,
        compatibility,
        compatibility_evidence,
        tuple(issues),
    )


def _compatibility_issues(status: str, allowed: bool) -> list[str]:
    if status == "confirmed_working":
        return []
    if status in {"confirmed_broken", "upstream_unsupported"}:
        return [
            "Known incompatible component was explicitly allowed"
            if allowed
            else "Known incompatible component blocks installation"
        ]
    if status == "user_report_only":
        return ["Compatibility evidence is a user report, not a confirmed result"]
    return ["Component compatibility is unknown"]


def _provider_matches(
    mapping: PackageMapping, manager: str | None, aur_helper: str | None
) -> bool:
    if mapping.provider == "aur":
        return manager == "pacman" and aur_helper in {"paru", "yay"}
    return mapping.provider == manager


def _normalized_manager(value: str | None) -> str | None:
    return "apt" if value == "apt-get" else value


def _version_satisfies(installed: str | None, required: Any) -> bool:
    if required is None:
        return True
    if installed is None or not isinstance(required, str):
        return False
    return installed == required or installed.startswith(f"{required}-")


def _dependency_by_id(report: DependencyReport, dependency_id: str) -> DependencyResolution:
    matches = [item for item in report.dependencies if item.dependency_id == dependency_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown dependency id: {dependency_id}")
    return matches[0]


def _xdg_state_root() -> Path:
    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            raise ValueError("XDG_STATE_HOME must be an absolute path")
        return path
    return Path.home() / ".local" / "state"


def _default_database_root() -> Path:
    repository = Path(__file__).resolve().parents[3] / "compatibility"
    installed = Path(sys.prefix) / "share" / "alchemy" / "compatibility"
    if repository.is_dir():
        return repository
    return installed
