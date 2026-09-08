from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from alchemy.domain.transactions import Operation, TransactionState, VerificationResult
from alchemy.platform.journal import JournalStore


class JournalStoreTests(unittest.TestCase):
    def test_persists_every_state_transition_and_finds_incomplete_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JournalStore(Path(temporary))
            operation = Operation(
                "operation-id",
                "color_scheme",
                "kde.color_scheme",
                "Change scheme",
                "BreezeLight",
                "BreezeDark",
                ("plasma-apply-colorscheme", "BreezeDark"),
                ("/home/test/.config/kdeglobals",),
            )
            record = store.create(
                operation=operation,
                snapshot_id="snapshot-id",
                environment={"plasma_version": "6.7.4"},
            )

            record = store.transition(record, TransactionState.APPLYING, current_operation_index=0)
            self.assertEqual(len(store.incomplete()), 1)
            record = store.transition(
                record,
                TransactionState.COMMITTED,
                current_operation_index=0,
                verification=VerificationResult(True, "BreezeDark", "matched"),
            )

            loaded = store.load(str(record["transaction_id"]))
            self.assertEqual(loaded["state"], "committed")
            self.assertEqual(store.incomplete(), ())
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(store.directory.stat().st_mode), 0o700)
                self.assertEqual(
                    stat.S_IMODE(store.path_for(str(record["transaction_id"])).stat().st_mode),
                    0o600,
                )

    def test_rejects_invalid_state_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JournalStore(Path(temporary))
            operation = Operation("op", "driver", "target", "desc", "a", "b", (), ())
            record = store.create(
                operation=operation, snapshot_id="snapshot", environment={}
            )

            with self.assertRaises(ValueError):
                store.transition(record, TransactionState.COMMITTED)


if __name__ == "__main__":
    unittest.main()
