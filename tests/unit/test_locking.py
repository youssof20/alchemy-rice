from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from pathlib import Path

from alchemy.platform.locking import MutationLock, TransactionLockedError


class MutationLockTests(unittest.TestCase):
    def test_prevents_two_writers_and_releases_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "apply.lock"
            first = MutationLock(path)
            first.acquire()
            try:
                with self.assertRaises(TransactionLockedError):
                    MutationLock(path).acquire()
            finally:
                first.release()

            self.assertFalse(path.exists())

    def test_removes_a_dead_local_process_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "apply.lock"
            path.write_text(
                json.dumps({"pid": 2_000_000_000, "hostname": socket.gethostname()}),
                encoding="utf-8",
            )
            lock = MutationLock(path)

            lock.acquire()
            try:
                owner = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(owner["pid"], os.getpid())
            finally:
                lock.release()


if __name__ == "__main__":
    unittest.main()
