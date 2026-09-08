from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from alchemy.drivers.kconfig import KConfigDriver, KConfigSpec
from alchemy.drivers.wallpaper import WallpaperDriver
from alchemy.platform.commands import Runner
from alchemy.platform.kde_notifications import KdeNotifier, Notifier, RefreshAction
from alchemy.platform.plasma_shell import PlasmaShell, QtPlasmaShell

_PLACEMENT = frozenset({"Smart", "Maximizing", "Random", "Centered", "ZeroCornered", "UnderMouse"})
_BOOLEAN = frozenset({"true", "false"})

SPECS: dict[str, KConfigSpec] = {
    "icons.theme": KConfigSpec(
        "icons.theme",
        "kde.icons.theme",
        "icon theme",
        "kdeglobals",
        "Icons",
        "Theme",
        RefreshAction.ICON,
    ),
    "cursor.theme": KConfigSpec(
        "cursor.theme",
        "kde.cursor.theme",
        "cursor theme",
        "kcminputrc",
        "Mouse",
        "cursorTheme",
        RefreshAction.CURSOR,
    ),
    "cursor.size": KConfigSpec(
        "cursor.size",
        "kde.cursor.size",
        "cursor size",
        "kcminputrc",
        "Mouse",
        "cursorSize",
        RefreshAction.CURSOR,
        minimum_integer=0,
        maximum_integer=512,
    ),
    "plasma.theme": KConfigSpec(
        "plasma.theme",
        "kde.plasma.theme",
        "Plasma theme",
        "plasmarc",
        "Theme",
        "name",
        RefreshAction.NONE,
    ),
    "fonts.general": KConfigSpec(
        "fonts.general",
        "kde.fonts.general",
        "general font",
        "kdeglobals",
        "General",
        "font",
        RefreshAction.FONT,
    ),
    "fonts.fixed": KConfigSpec(
        "fonts.fixed",
        "kde.fonts.fixed",
        "fixed-width font",
        "kdeglobals",
        "General",
        "fixed",
        RefreshAction.FONT,
    ),
    "fonts.small": KConfigSpec(
        "fonts.small",
        "kde.fonts.small",
        "small font",
        "kdeglobals",
        "General",
        "smallestReadableFont",
        RefreshAction.FONT,
    ),
    "fonts.toolbar": KConfigSpec(
        "fonts.toolbar",
        "kde.fonts.toolbar",
        "toolbar font",
        "kdeglobals",
        "General",
        "toolBarFont",
        RefreshAction.FONT,
    ),
    "fonts.menu": KConfigSpec(
        "fonts.menu",
        "kde.fonts.menu",
        "menu font",
        "kdeglobals",
        "General",
        "menuFont",
        RefreshAction.FONT,
    ),
    "fonts.window_title": KConfigSpec(
        "fonts.window_title",
        "kde.fonts.window_title",
        "window-title font",
        "kdeglobals",
        "WM",
        "activeFont",
        RefreshAction.FONT,
    ),
    "application_style.theme": KConfigSpec(
        "application_style.theme",
        "kde.application_style.theme",
        "application style",
        "kdeglobals",
        "KDE",
        "widgetStyle",
        RefreshAction.STYLE,
    ),
    "decoration.plugin": KConfigSpec(
        "decoration.plugin",
        "kde.decoration.plugin",
        "decoration plugin",
        "kwinrc",
        "org.kde.kdecoration2",
        "library",
        RefreshAction.KWIN,
    ),
    "decoration.theme": KConfigSpec(
        "decoration.theme",
        "kde.decoration.theme",
        "decoration theme",
        "kwinrc",
        "org.kde.kdecoration2",
        "theme",
        RefreshAction.KWIN,
    ),
    "decoration.border_size": KConfigSpec(
        "decoration.border_size",
        "kde.decoration.border_size",
        "window border size",
        "kwinrc",
        "org.kde.kdecoration2",
        "BorderSize",
        RefreshAction.KWIN,
        frozenset(
            {
                "None",
                "NoSides",
                "Tiny",
                "Normal",
                "Large",
                "VeryLarge",
                "Huge",
                "VeryHuge",
                "Oversized",
            }
        ),
    ),
    "decoration.border_auto": KConfigSpec(
        "decoration.border_auto",
        "kde.decoration.border_auto",
        "automatic window border",
        "kwinrc",
        "org.kde.kdecoration2",
        "BorderSizeAuto",
        RefreshAction.KWIN,
        _BOOLEAN,
    ),
    "kwin.placement": KConfigSpec(
        "kwin.placement",
        "kde.kwin.placement",
        "window placement",
        "kwinrc",
        "Windows",
        "Placement",
        RefreshAction.KWIN,
        _PLACEMENT,
    ),
    "kwin.borderless_maximized": KConfigSpec(
        "kwin.borderless_maximized",
        "kde.kwin.borderless_maximized",
        "borderless maximized windows",
        "kwinrc",
        "Windows",
        "BorderlessMaximizedWindows",
        RefreshAction.KWIN,
        _BOOLEAN,
    ),
}


class DriverRegistry:
    def __init__(
        self,
        runner: Runner,
        which: Callable[[str], str | None],
        *,
        home: Path,
        config_root: Path | None = None,
        notifier: Notifier | None = None,
        plasma_shell: PlasmaShell | None = None,
    ) -> None:
        self.runner = runner
        self.which = which
        self.home = home
        self.config_root = config_root or home / ".config"
        self.notifier = notifier or KdeNotifier()
        self.plasma_shell = plasma_shell or QtPlasmaShell()

    def names(self) -> tuple[str, ...]:
        return (*SPECS, WallpaperDriver.name)

    def create(self, name: str) -> KConfigDriver | WallpaperDriver:
        if name == WallpaperDriver.name:
            wallpaper_tool = self.which("plasma-apply-wallpaperimage")
            if not wallpaper_tool:
                raise RuntimeError("plasma-apply-wallpaperimage is required")
            return WallpaperDriver(
                self.runner,
                self.plasma_shell,
                apply_tool=wallpaper_tool,
                config_path=(self.config_root / "plasma-org.kde.plasma.desktop-appletsrc"),
            )
        try:
            spec = SPECS[name]
        except KeyError as exc:
            raise ValueError(f"Unknown setting driver: {name}") from exc
        kreadconfig = self.which("kreadconfig6")
        kwriteconfig = self.which("kwriteconfig6")
        if not kreadconfig or not kwriteconfig:
            raise RuntimeError("kreadconfig6 and kwriteconfig6 are required")
        apply_tool: str | None = None
        if name == "cursor.theme":
            apply_tool = self.which("plasma-apply-cursortheme")
        elif name == "plasma.theme":
            apply_tool = self.which("plasma-apply-desktoptheme")
        if name in {"cursor.theme", "plasma.theme"} and not apply_tool:
            raise RuntimeError(f"The official KDE apply tool for {spec.label} is unavailable")
        return KConfigDriver(
            spec,
            self.runner,
            self.notifier,
            kreadconfig=kreadconfig,
            kwriteconfig=kwriteconfig,
            config_path=self.config_root / spec.config_file,
            apply_tool=apply_tool,
        )
