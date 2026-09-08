from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Any

from alchemy.domain.rice import canonical_json_bytes


class TrustTier(StrEnum):
    DISTRIBUTION = "tier_a_distribution"
    COMMUNITY = "tier_b_community"
    MANUAL = "tier_c_manual"

    @property
    def label(self) -> str:
        return {
            self.DISTRIBUTION: "Official distro package",
            self.COMMUNITY: "Third-party package - review source",
            self.MANUAL: "Manual install required",
        }[self]


@dataclass(frozen=True, slots=True)
class Candidate:
    provider: str
    package: str
    source_url: str
    trust_tier: TrustTier
    repository: str
    mapping_status: str
    checked_on: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["trust_tier"] = self.trust_tier.value
        value["trust_label"] = self.trust_tier.label
        return value


@dataclass(frozen=True, slots=True)
class PackageInfo:
    installed: bool
    version: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CommandPlan:
    arguments: tuple[str, ...]
    requires_privilege: bool
    privilege_reason: str | None
    automatable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "arguments": list(self.arguments),
            "requires_privilege": self.requires_privilege,
            "privilege_reason": self.privilege_reason,
            "automatable": self.automatable,
        }


@dataclass(frozen=True, slots=True)
class DependencyResolution:
    dependency_id: str
    capability: str
    component_type: str
    license: str
    declared_source: dict[str, Any]
    status: str
    trust_tier: TrustTier
    candidate: Candidate | None
    installed: PackageInfo | None
    command_plan: CommandPlan | None
    plan_token: str | None
    compatibility_status: str
    compatibility_evidence: tuple[dict[str, str], ...]
    issues: tuple[str, ...]

    def with_plan_token(self, token: str) -> DependencyResolution:
        return replace(self, plan_token=token)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dependency_id": self.dependency_id,
            "capability": self.capability,
            "component_type": self.component_type,
            "license": self.license,
            "declared_source": self.declared_source,
            "status": self.status,
            "trust_tier": self.trust_tier.value,
            "trust_label": self.trust_tier.label,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "installed": self.installed.to_dict() if self.installed else None,
            "command_plan": self.command_plan.to_dict() if self.command_plan else None,
            "plan_token": self.plan_token,
            "compatibility_status": self.compatibility_status,
            "compatibility_evidence": list(self.compatibility_evidence),
            "issues": list(self.issues),
        }


@dataclass(frozen=True, slots=True)
class DependencyReport:
    rice_identity: str
    rice_sha256: str
    distro: str | None
    package_manager: str | None
    immutable_host: bool | None
    plasma_status: str
    plasma_evidence: tuple[dict[str, str], ...]
    dependencies: tuple[DependencyResolution, ...]

    @property
    def ready(self) -> bool:
        return all(item.status == "installed" for item in self.dependencies)

    @property
    def install_required(self) -> bool:
        return any(item.status in {"missing", "version_mismatch"} for item in self.dependencies)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rice_identity": self.rice_identity,
            "rice_sha256": self.rice_sha256,
            "environment": {
                "distro": self.distro,
                "package_manager": self.package_manager,
                "immutable_host": self.immutable_host,
            },
            "plasma_status": self.plasma_status,
            "plasma_evidence": list(self.plasma_evidence),
            "ready": self.ready,
            "install_required": self.install_required,
            "dependencies": [item.to_dict() for item in self.dependencies],
        }


def classify_trust(
    source_type: str, repository: str | None, provider: str | None = None
) -> TrustTier:
    if provider == "aur":
        return TrustTier.COMMUNITY
    if source_type == "distro_package" and repository == "official":
        return TrustTier.DISTRIBUTION
    if source_type in {"kde_store", "github_release"} or repository == "community":
        return TrustTier.COMMUNITY
    return TrustTier.MANUAL


def bind_plan_token(
    rice_sha256: str,
    resolution: DependencyResolution,
    *,
    distro: str | None,
    package_manager: str | None,
) -> DependencyResolution:
    if resolution.command_plan is None:
        return resolution
    payload = {
        "rice_sha256": rice_sha256,
        "dependency_id": resolution.dependency_id,
        "status": resolution.status,
        "candidate": resolution.candidate.to_dict() if resolution.candidate else None,
        "command_plan": resolution.command_plan.to_dict(),
        "distro": distro,
        "package_manager": package_manager,
        "compatibility_status": resolution.compatibility_status,
        "compatibility_evidence": list(resolution.compatibility_evidence),
    }
    token = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return resolution.with_plan_token(token)
