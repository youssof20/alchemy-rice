from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from types import TracebackType


class TransactionLockedError(RuntimeError):
    pass


class MutationLock:
    """Cross-process single-writer lock with conservative stale detection."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except FileExistsError as exc:
            if self._remove_stale_lock():
                descriptor = os.open(self.path, flags, 0o600)
            else:
                raise TransactionLockedError(self.describe_owner()) from exc
        try:
            payload = {"pid": os.getpid(), "hostname": socket.gethostname()}
            os.write(descriptor, json.dumps(payload).encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._acquired = True

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            owner = self._read_owner()
            if owner.get("pid") == os.getpid() and owner.get("hostname") == socket.gethostname():
                self.path.unlink(missing_ok=True)
        finally:
            self._acquired = False

    def describe_owner(self) -> str:
        owner = self._read_owner()
        if owner:
            return f"Another Alchemy mutation is active (pid {owner.get('pid', 'unknown')})."
        return "Another Alchemy mutation is active."

    def _remove_stale_lock(self) -> bool:
        owner = self._read_owner()
        if owner.get("hostname") != socket.gethostname():
            return False
        pid = owner.get("pid")
        if not isinstance(pid, int) or _process_exists(pid):
            return False
        try:
            self.path.unlink()
        except OSError:
            return False
        return True

    def _read_owner(self) -> dict[str, object]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def __enter__(self) -> MutationLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.release()


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True
