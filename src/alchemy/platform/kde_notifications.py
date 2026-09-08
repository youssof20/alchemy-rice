from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Protocol


class GlobalChange(IntEnum):
    PALETTE = 0
    FONT = 1
    STYLE = 2
    SETTINGS = 3
    ICON = 4
    CURSOR = 5


class RefreshAction(StrEnum):
    NONE = "none"
    PALETTE = "palette"
    FONT = "font"
    STYLE = "style"
    ICON = "icon"
    CURSOR = "cursor"
    KWIN = "kwin"


class Notifier(Protocol):
    def refresh(self, action: RefreshAction) -> None: ...


class KdeNotifier:
    """Emit the same session-bus signals used by Plasma 6 KCMs."""

    def refresh(self, action: RefreshAction) -> None:
        if action is RefreshAction.NONE:
            return
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusMessage
        except ImportError as exc:
            raise RuntimeError("PySide6 QtDBus is required to refresh KDE settings") from exc

        if action is RefreshAction.KWIN:
            message = QDBusMessage.createSignal("/KWin", "org.kde.KWin", "reloadConfig")
        elif action is RefreshAction.FONT:
            message = QDBusMessage.createSignal(
                "/KDEPlatformTheme", "org.kde.KDEPlatformTheme", "refreshFonts"
            )
        else:
            change = {
                RefreshAction.PALETTE: GlobalChange.PALETTE,
                RefreshAction.STYLE: GlobalChange.STYLE,
                RefreshAction.ICON: GlobalChange.ICON,
                RefreshAction.CURSOR: GlobalChange.CURSOR,
            }[action]
            message = QDBusMessage.createSignal(
                "/KGlobalSettings", "org.kde.KGlobalSettings", "notifyChange"
            )
            message.setArguments([int(change), 0])
        if not QDBusConnection.sessionBus().send(message):
            raise RuntimeError(f"Could not send KDE refresh signal: {action.value}")
