from __future__ import annotations

import os
import platform
import re
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path

from alchemy.domain.capabilities import (
    CapabilityMatrix,
    ComponentCapability,
    EnvironmentReport,
)
from alchemy.drivers.readers import default_setting_readers, read_all
from alchemy.platform.commands import CommandRunner, Runner

Which = Callable[[str], str | None]

_VERSION_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)")
_KSCREEN_OUTPUT_PATTERN = re.compile(
    r"^Output:\s+\d+\s+(?P<name>\S+)(?P<rest>.*)$", re.MULTILINE
)
_KSCREEN_SCALE_PATTERN = re.compile(r"Scale:\s*(?P<scale>\d+(?:\.\d+)?)")


class EnvironmentProbe:
    """Collect read-only desktop capabilities and reviewed visual settings."""

    def __init__(
        self,
        *,
        runner: Runner | None = None,
        environ: Mapping[str, str] | None = None,
        which: Which | None = None,
        root: Path | None = None,
        home: Path | None = None,
        host_os: str | None = None,
    ) -> None:
        self._environ = dict(os.environ if environ is None else environ)
        self._runner = runner or CommandRunner(environment=self._environ)
        self._which = which or shutil.which
        self._root = root or Path("/")
        self._home = home or Path.home()
        self._host_os = host_os or platform.system().lower()

    def inspect(self) -> EnvironmentReport:
        warnings: list[str] = []
        os_release = self._read_os_release()
        plasma_version = self._plasma_version()
        session = _normalized(self._environ.get("XDG_SESSION_TYPE"))
        desktop = _first_nonempty(
            self._environ.get("XDG_CURRENT_DESKTOP"),
            self._environ.get("DESKTOP_SESSION"),
        )

        package_manager = self._first_executable(
            "pacman", "dnf", "apt-get", "zypper", "rpm-ostree", "transactional-update"
        )
        aur_helper = self._first_executable("paru", "yay")
        portals = self._portals()
        plasma_apply = self._plasma_apply_tools()
        monitors, mixed_scale = self._monitors()
        login_manager = self._login_manager()
        nix = self._nix_capability(os_release)
        plasma_manager = self._plasma_manager_capability()
        union = self._union_capability()
        immutable_host = self._immutable_host(package_manager, os_release)

        if self._host_os != "linux":
            warnings.append(
                "Alchemy can be developed and tested here, but KDE inspection requires Linux."
            )
        if self._host_os == "linux" and plasma_version is None:
            warnings.append("Plasma was not detected; Apply remains disabled.")
        if session == "x11":
            warnings.append("Legacy X11 session detected; Wayland is the primary target.")
        if plasma_manager.active:
            warnings.append(
                "plasma-manager may own this desktop state; future Apply operations "
                "must not fight it."
            )

        kreadconfig = self._which("kreadconfig6")
        settings = read_all(default_setting_readers(), self._runner, kreadconfig)
        capabilities = CapabilityMatrix(
            host_os=self._host_os,
            plasma_version=plasma_version,
            session=session,
            desktop=desktop,
            login_manager=login_manager,
            distro=_normalized(os_release.get("ID")),
            distro_version=_normalized(os_release.get("VERSION_ID")),
            package_manager=package_manager,
            aur_helper=aur_helper,
            portals=portals,
            plasma_apply=plasma_apply,
            union=union,
            nix=nix,
            plasma_manager=plasma_manager,
            monitors=monitors,
            mixed_scale=mixed_scale,
            immutable_host=immutable_host,
            apply_supported=_color_apply_supported(
                host_os=self._host_os,
                plasma_version=plasma_version,
                session=session,
                desktop=desktop,
                plasma_apply=plasma_apply,
                kreadconfig_available=kreadconfig is not None,
                plasma_manager_active=bool(plasma_manager.active),
            ),
        )
        return EnvironmentReport(capabilities, settings, tuple(warnings))

    def _read_os_release(self) -> dict[str, str]:
        path = self._root / "etc" / "os-release"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {}
        return parse_os_release(text)

    def _plasma_version(self) -> str | None:
        executable = self._which("plasmashell")
        if executable is None:
            return None
        result = self._runner.run((executable, "--version"))
        if result.returncode != 0:
            return None
        return extract_version(result.stdout or result.stderr)

    def _first_executable(self, *names: str) -> str | None:
        for name in names:
            if self._which(name):
                return name
        return None

    def _plasma_apply_tools(self) -> tuple[str, ...]:
        tools = {
            "colorscheme": "plasma-apply-colorscheme",
            "cursortheme": "plasma-apply-cursortheme",
            "desktoptheme": "plasma-apply-desktoptheme",
            "lookandfeel": "plasma-apply-lookandfeel",
            "wallpaper": "plasma-apply-wallpaperimage",
        }
        return tuple(
            capability for capability, executable in tools.items() if self._which(executable)
        )

    def _portals(self) -> tuple[str, ...]:
        gdbus = self._which("gdbus")
        if gdbus is None or not self._environ.get("DBUS_SESSION_BUS_ADDRESS"):
            return ()
        result = self._runner.run(
            (
                gdbus,
                "introspect",
                "--session",
                "--dest",
                "org.freedesktop.portal.Desktop",
                "--object-path",
                "/org/freedesktop/portal/desktop",
            )
        )
        if result.returncode != 0:
            return ()
        portals = ["desktop"]
        if "org.freedesktop.portal.Screenshot" in result.stdout:
            portals.append("screenshot")
        return tuple(portals)

    def _monitors(self) -> tuple[tuple[str, ...], bool | None]:
        doctor = self._which("kscreen-doctor")
        if doctor is None:
            return (), None
        result = self._runner.run((doctor, "-o"))
        if result.returncode != 0:
            return (), None
        monitors: list[str] = []
        scales: list[float] = []
        for match in _KSCREEN_OUTPUT_PATTERN.finditer(result.stdout):
            rest = match.group("rest").lower()
            if "connected" in rest and "disabled" not in rest:
                monitors.append(match.group("name"))
        scales.extend(
            float(match.group("scale"))
            for match in _KSCREEN_SCALE_PATTERN.finditer(result.stdout)
        )
        mixed = len({round(scale, 4) for scale in scales}) > 1 if scales else None
        return tuple(monitors), mixed

    def _login_manager(self) -> str | None:
        service = self._root / "etc" / "systemd" / "system" / "display-manager.service"
        try:
            target = str(service.resolve(strict=True)).lower()
        except OSError:
            target = ""
        if "plasmalogin" in target:
            return "plasmalogin"
        if "sddm" in target:
            return "sddm"
        if target:
            return Path(target).stem
        return None

    def _nix_capability(self, os_release: Mapping[str, str]) -> ComponentCapability:
        nixos = os_release.get("ID", "").lower() == "nixos"
        installed = nixos or self._which("nix") is not None
        evidence = "/etc/os-release" if nixos else ("nix executable" if installed else None)
        return ComponentCapability(installed=installed, active=nixos, evidence=evidence)

    def _plasma_manager_capability(self) -> ComponentCapability:
        candidates = (
            self._home / ".config" / "home-manager" / "home.nix",
            self._home / ".config" / "home-manager" / "flake.nix",
        )
        for path in candidates:
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                if "plasma-manager" in path.read_text(encoding="utf-8", errors="ignore"):
                    return ComponentCapability(True, True, str(path))
            except OSError:
                continue
        return ComponentCapability(False, False, None)

    def _union_capability(self) -> ComponentCapability:
        # Union is still experimental and has no stable public capability probe.
        # Unknown is safer than inferring support from a Plasma version.
        return ComponentCapability(None, None, "No stable capability probe is available")

    @staticmethod
    def _immutable_host(
        package_manager: str | None, os_release: Mapping[str, str]
    ) -> bool | None:
        if package_manager in {"rpm-ostree", "transactional-update"}:
            return True
        variant = " ".join(
            (os_release.get("ID", ""), os_release.get("VARIANT_ID", ""))
        ).lower()
        if any(marker in variant for marker in ("silverblue", "kinoite", "immutable")):
            return True
        return False if os_release else None


def parse_os_release(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value.replace(r"\"", '"').replace(r"\\", "\\")
    return values


def extract_version(text: str) -> str | None:
    match = _VERSION_PATTERN.search(text)
    return match.group(1) if match else None


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _first_nonempty(*values: str | None) -> str | None:
    return next((value.strip() for value in values if value and value.strip()), None)


def _color_apply_supported(
    *,
    host_os: str,
    plasma_version: str | None,
    session: str | None,
    desktop: str | None,
    plasma_apply: tuple[str, ...],
    kreadconfig_available: bool,
    plasma_manager_active: bool,
) -> bool:
    if (
        host_os != "linux"
        or plasma_version is None
        or session not in {"wayland", "x11"}
        or desktop is None
        or "kde" not in desktop.lower()
        or plasma_manager_active
    ):
        return False
    parts = tuple(int(part) for part in plasma_version.split("."))
    supported_version = (6, 6) <= parts[:2] <= (6, 8)
    return supported_version and "colorscheme" in plasma_apply and kreadconfig_available
