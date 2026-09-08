from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from alchemy.domain.capabilities import SettingObservation
from alchemy.platform.commands import Runner


@dataclass(frozen=True, slots=True)
class KConfigSettingReader:
    """Read one reviewed KDE setting through KConfig's read-only CLI."""

    component: str
    label: str
    config_file: str
    group: str
    key: str

    def read(self, runner: Runner, kreadconfig: str | None) -> SettingObservation:
        source = f"{self.config_file} [{self.group}] {self.key}"
        if kreadconfig is None:
            return SettingObservation(
                component=self.component,
                label=self.label,
                value=None,
                source=source,
                available=False,
                detail="kreadconfig6 is not available",
            )
        result = runner.run(
            (
                kreadconfig,
                "--file",
                self.config_file,
                "--group",
                self.group,
                "--key",
                self.key,
            )
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or f"kreadconfig6 exited with {result.returncode}"
            return SettingObservation(
                self.component, self.label, None, source, False, detail
            )
        value = result.stdout.rstrip("\r\n")
        return SettingObservation(
            self.component,
            self.label,
            value or None,
            source,
            True,
            None if value else "Setting is unset or inherited",
        )


def default_setting_readers() -> tuple[KConfigSettingReader, ...]:
    """Reviewed visual-setting allowlist; this list contains no mutation behavior."""

    return (
        KConfigSettingReader("colors", "Color scheme", "kdeglobals", "General", "ColorScheme"),
        KConfigSettingReader("icons", "Icon theme", "kdeglobals", "Icons", "Theme"),
        KConfigSettingReader("fonts", "General font", "kdeglobals", "General", "font"),
        KConfigSettingReader("fonts", "Fixed-width font", "kdeglobals", "General", "fixed"),
        KConfigSettingReader(
            "fonts", "Small font", "kdeglobals", "General", "smallestReadableFont"
        ),
        KConfigSettingReader(
            "fonts", "Toolbar font", "kdeglobals", "General", "toolBarFont"
        ),
        KConfigSettingReader("fonts", "Menu font", "kdeglobals", "General", "menuFont"),
        KConfigSettingReader(
            "fonts", "Window-title font", "kdeglobals", "WM", "activeFont"
        ),
        KConfigSettingReader("cursor", "Cursor theme", "kcminputrc", "Mouse", "cursorTheme"),
        KConfigSettingReader("cursor", "Cursor size", "kcminputrc", "Mouse", "cursorSize"),
        KConfigSettingReader("plasma_theme", "Plasma theme", "plasmarc", "Theme", "name"),
        KConfigSettingReader(
            "application_style", "Widget style", "kdeglobals", "KDE", "widgetStyle"
        ),
        KConfigSettingReader(
            "window_decoration", "Decoration theme", "kwinrc", "org.kde.kdecoration2", "theme"
        ),
        KConfigSettingReader(
            "window_decoration", "Decoration plugin", "kwinrc", "org.kde.kdecoration2", "library"
        ),
        KConfigSettingReader(
            "window_decoration",
            "Window border size",
            "kwinrc",
            "org.kde.kdecoration2",
            "BorderSize",
        ),
        KConfigSettingReader(
            "window_decoration",
            "Automatic window border",
            "kwinrc",
            "org.kde.kdecoration2",
            "BorderSizeAuto",
        ),
        KConfigSettingReader(
            "kwin", "Window placement", "kwinrc", "Windows", "Placement"
        ),
        KConfigSettingReader(
            "kwin",
            "Borderless maximized windows",
            "kwinrc",
            "Windows",
            "BorderlessMaximizedWindows",
        ),
    )


def read_all(
    readers: Iterable[KConfigSettingReader], runner: Runner, kreadconfig: str | None
) -> tuple[SettingObservation, ...]:
    return tuple(reader.read(runner, kreadconfig) for reader in readers)
