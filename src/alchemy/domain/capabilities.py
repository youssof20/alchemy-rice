from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ComponentCapability:
    """A component state that can remain unknown when no reliable probe exists."""

    installed: bool | None
    active: bool | None
    evidence: str | None = None


@dataclass(frozen=True, slots=True)
class CapabilityMatrix:
    """Immutable facts observed for the current desktop session."""

    host_os: str
    plasma_version: str | None
    session: str | None
    desktop: str | None
    login_manager: str | None
    distro: str | None
    distro_version: str | None
    package_manager: str | None
    aur_helper: str | None
    portals: tuple[str, ...]
    plasma_apply: tuple[str, ...]
    union: ComponentCapability
    nix: ComponentCapability
    plasma_manager: ComponentCapability
    monitors: tuple[str, ...]
    mixed_scale: bool | None
    immutable_host: bool | None
    apply_supported: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SettingObservation:
    """A read-only setting value with its origin and availability."""

    component: str
    label: str
    value: str | None
    source: str
    available: bool
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EnvironmentReport:
    capabilities: CapabilityMatrix
    settings: tuple[SettingObservation, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilities": self.capabilities.to_dict(),
            "settings": [setting.to_dict() for setting in self.settings],
            "warnings": list(self.warnings),
        }
