from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from alchemy.platform.snapshots import SnapshotError, SnapshotStore


class SnapshotStoreTests(unittest.TestCase):
    def test_restores_existing_and_absent_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            existing = home / ".config" / "kdeglobals"
            existing.parent.mkdir()
            existing.write_bytes(b"original\n")
            absent = home / ".config" / "not-created-yet"
            store = SnapshotStore(root / "snapshots", home=home)

            manifest = store.create(
                (existing, absent),
                driver="color_scheme",
                plasma_version="6.7.4",
                reason="test",
            )
            existing.write_bytes(b"changed\n")
            absent.write_bytes(b"created\n")

            store.restore(str(manifest["snapshot_id"]))

            self.assertEqual(existing.read_bytes(), b"original\n")
            self.assertFalse(absent.exists())
            self.assertEqual(
                manifest["entries"][0]["sha256"], hashlib.sha256(b"original\n").hexdigest()
            )

    def test_rejects_paths_outside_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            store = SnapshotStore(root / "snapshots", home=home)

            with self.assertRaises(SnapshotError):
                store.create(
                    (root / "outside",),
                    driver="color_scheme",
                    plasma_version=None,
                    reason="test",
                )


if __name__ == "__main__":
    unittest.main()
