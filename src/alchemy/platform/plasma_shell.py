from __future__ import annotations

from typing import Protocol, cast


class PlasmaShell(Protocol):
    def evaluate(self, script: str) -> str: ...

    def dump_layout(self) -> str: ...


class QtPlasmaShell:
    """Call Plasma's reviewed scripting endpoint through the session bus."""

    def evaluate(self, script: str) -> str:
        return self._call("evaluateScript", script)

    def dump_layout(self) -> str:
        return self._call("dumpCurrentLayoutJS")

    @staticmethod
    def _call(method: str, *arguments: str) -> str:
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusMessage
        except ImportError as exc:
            raise RuntimeError("PySide6 QtDBus is required to inspect Plasma") from exc

        message = QDBusMessage.createMethodCall(
            "org.kde.plasmashell",
            "/PlasmaShell",
            "org.kde.PlasmaShell",
            method,
        )
        message.setArguments(list(arguments))
        reply = QDBusConnection.sessionBus().call(message)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            raise RuntimeError(reply.errorMessage() or f"Plasma rejected {method}")
        values = reply.arguments()
        if not values:
            raise RuntimeError(f"Plasma returned no result for {method}")
        value = values[0]
        if isinstance(value, bytes):
            return value.decode("utf-8")
        try:
            byte_value = bytes(value)
        except (TypeError, ValueError):
            return cast(str, value)
        return byte_value.decode("utf-8")
