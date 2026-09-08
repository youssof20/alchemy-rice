from __future__ import annotations

from typing import Protocol, cast


class PlasmaShell(Protocol):
    def evaluate(self, script: str) -> str: ...


class QtPlasmaShell:
    """Call Plasma's reviewed scripting endpoint through the session bus."""

    def evaluate(self, script: str) -> str:
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusMessage
        except ImportError as exc:
            raise RuntimeError("PySide6 QtDBus is required to inspect wallpapers") from exc

        message = QDBusMessage.createMethodCall(
            "org.kde.plasmashell",
            "/PlasmaShell",
            "org.kde.PlasmaShell",
            "evaluateScript",
        )
        message.setArguments([script])
        reply = QDBusConnection.sessionBus().call(message)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            raise RuntimeError(reply.errorMessage() or "Plasma rejected the wallpaper query")
        arguments = reply.arguments()
        if not arguments:
            raise RuntimeError("Plasma returned no wallpaper state")
        return cast(str, arguments[0])
