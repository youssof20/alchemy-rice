from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from alchemy.domain.compatibility_database import PackageMapping
from alchemy.domain.dependencies import Candidate, CommandPlan, PackageInfo, TrustTier
from alchemy.platform.commands import Runner

_PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,191}$")


class PackageProvider(Protocol):
    provider_id: str

    async def search(self, capability: str) -> tuple[Candidate, ...]: ...

    async def inspect(self, candidate: Candidate) -> PackageInfo: ...

    async def plan_install(self, candidate: Candidate) -> CommandPlan: ...

    async def install(self, candidate: Candidate) -> PackageInfo: ...


class CommandPackageProvider:
    """A reviewed package-manager adapter with fixed argument-vector templates."""

    def __init__(
        self,
        provider_id: str,
        runner: Runner,
        *,
        executable: str,
        query_executable: str,
        pkexec: str | None,
        mappings: tuple[PackageMapping, ...],
    ) -> None:
        self.provider_id = provider_id
        self.runner = runner
        self.executable = executable
        self.query_executable = query_executable
        self.pkexec = pkexec
        self.mappings = mappings

    async def search(self, capability: str) -> tuple[Candidate, ...]:
        return tuple(
            Candidate(
                mapping.provider,
                mapping.package,
                mapping.source_url,
                TrustTier.COMMUNITY
                if mapping.provider == "aur"
                else (
                    TrustTier.DISTRIBUTION
                    if mapping.repository == "official"
                    else TrustTier.COMMUNITY
                ),
                mapping.repository,
                mapping.status,
                mapping.checked_on,
            )
            for mapping in self.mappings
            if mapping.capability == capability and mapping.provider == self.provider_id
        )

    async def inspect(self, candidate: Candidate) -> PackageInfo:
        _validate_candidate(candidate, self.provider_id)
        arguments = self._query_arguments(candidate.package)
        result = await asyncio.to_thread(self.runner.run, arguments, timeout=20.0)
        if result.returncode != 0:
            return PackageInfo(False, None)
        return PackageInfo(True, self._parse_version(result.stdout))

    async def plan_install(self, candidate: Candidate) -> CommandPlan:
        _validate_candidate(candidate, self.provider_id)
        if self.provider_id == "aur":
            return CommandPlan(
                (Path(self.executable).name, "-S", "--needed", candidate.package),
                False,
                None,
                False,
            )
        if self.pkexec is None:
            return CommandPlan(
                self._public_install_arguments(candidate.package, "pkexec"),
                True,
                "Installing a system package changes the host package database",
                False,
            )
        return CommandPlan(
            self._public_install_arguments(candidate.package, Path(self.pkexec).name),
            True,
            "Installing a system package changes the host package database",
            True,
        )

    async def install(self, candidate: Candidate) -> PackageInfo:
        plan = await self.plan_install(candidate)
        if not plan.automatable or self.pkexec is None:
            raise RuntimeError("This package candidate requires manual installation")
        arguments = self._runtime_install_arguments(candidate.package)
        result = await asyncio.to_thread(self.runner.run, arguments, timeout=1800.0)
        if result.returncode != 0:
            raise RuntimeError(
                f"Package provider {self.provider_id} exited with status {result.returncode}"
            )
        installed = await self.inspect(candidate)
        if not installed.installed:
            raise RuntimeError("Package provider completed but installation was not verified")
        return installed

    def _query_arguments(self, package: str) -> tuple[str, ...]:
        if self.provider_id in {"pacman", "aur"}:
            return (self.query_executable, "-Q", "--", package)
        if self.provider_id in {"dnf", "zypper"}:
            return (
                self.query_executable,
                "-q",
                "--qf",
                "%{VERSION}-%{RELEASE}\\n",
                "--",
                package,
            )
        return (
            self.query_executable,
            "-W",
            "-f=${Status}\\t${Version}\\n",
            package,
        )

    def _parse_version(self, output: str) -> str | None:
        stripped = output.strip()
        if not stripped:
            return None
        if self.provider_id in {"pacman", "aur"}:
            fields = stripped.split()
            return _clean_version(fields[1]) if len(fields) >= 2 else None
        if self.provider_id == "apt":
            fields = stripped.split("\t")
            if len(fields) != 2 or fields[0] != "install ok installed":
                return None
            return _clean_version(fields[1].strip())
        return _clean_version(stripped.splitlines()[0])

    def _public_install_arguments(self, package: str, pkexec_name: str) -> tuple[str, ...]:
        manager = Path(self.executable).name
        if self.provider_id == "pacman":
            return (pkexec_name, manager, "-S", "--needed", "--noconfirm", "--", package)
        if self.provider_id == "dnf":
            return (pkexec_name, manager, "-y", "install", package)
        if self.provider_id == "apt":
            return (
                pkexec_name,
                manager,
                "install",
                "--yes",
                "--no-install-recommends",
                package,
            )
        return (
            pkexec_name,
            manager,
            "--non-interactive",
            "install",
            "--no-recommends",
            package,
        )

    def _runtime_install_arguments(self, package: str) -> tuple[str, ...]:
        assert self.pkexec is not None
        public = self._public_install_arguments(package, self.pkexec)
        return (public[0], self.executable, *public[2:])


ProviderFactory = Callable[[str, tuple[PackageMapping, ...]], PackageProvider | None]


class PackageProviderFactory:
    def __init__(self, runner: Runner, which: Callable[[str], str | None]) -> None:
        self.runner = runner
        self.which = which

    def create(
        self, provider_id: str, mappings: tuple[PackageMapping, ...]
    ) -> PackageProvider | None:
        if provider_id == "aur":
            executable = self._trusted("paru") or self._trusted("yay")
            pacman = self._trusted("pacman")
            if executable is None or pacman is None:
                return None
            return CommandPackageProvider(
                provider_id,
                self.runner,
                executable=executable,
                query_executable=pacman,
                pkexec=None,
                mappings=mappings,
            )
        executable_name = "apt-get" if provider_id == "apt" else provider_id
        query_name = {
            "pacman": "pacman",
            "dnf": "rpm",
            "apt": "dpkg-query",
            "zypper": "rpm",
        }.get(provider_id)
        if query_name is None:
            return None
        executable = self._trusted(executable_name)
        query = self._trusted(query_name)
        if executable is None or query is None:
            return None
        return CommandPackageProvider(
            provider_id,
            self.runner,
            executable=executable,
            query_executable=query,
            pkexec=self._trusted("pkexec"),
            mappings=mappings,
        )

    def _trusted(self, name: str) -> str | None:
        candidate = self.which(name)
        if candidate is None:
            return None
        if os.name == "nt":
            normalized = candidate.replace("\\", "/")
            return candidate if normalized.startswith(("/usr/bin/", "/usr/sbin/")) else None
        try:
            resolved = Path(candidate).resolve(strict=True)
        except OSError:
            return None
        return str(resolved) if resolved.parent in {Path("/usr/bin"), Path("/usr/sbin")} else None


def _validate_candidate(candidate: Candidate, provider_id: str) -> None:
    if candidate.provider != provider_id:
        raise ValueError("Package candidate belongs to a different provider")
    if _PACKAGE.fullmatch(candidate.package) is None:
        raise ValueError("Package candidate contains unsupported characters")


def _clean_version(value: str) -> str | None:
    if not 1 <= len(value) <= 256 or any(not 33 <= ord(character) <= 126 for character in value):
        return None
    return value
