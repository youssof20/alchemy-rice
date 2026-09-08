from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from alchemy.domain.compatibility_database import CompatibilityDatabase
from alchemy.domain.rice import load_rice


class CompatibilityDatabaseTests(unittest.TestCase):
    def test_public_database_loads_and_keeps_unknown_evidence_explicit(self) -> None:
        root = Path(__file__).parents[2] / "compatibility"

        database = CompatibilityDatabase.load(root)

        self.assertEqual(database.plasma_status("6.7.4"), "unknown")
        mapping = database.package_mapping("qt.style.kvantum", "arch")
        self.assertIsNotNone(mapping)
        assert mapping is not None
        self.assertEqual(mapping.provider, "pacman")
        self.assertEqual(mapping.repository, "official")
        self.assertEqual(database.component_status("missing.capability", "6.7.4"), "unknown")
        dependency_example = root.parent / "examples" / "rice-v2-dependencies.json"
        self.assertEqual(
            load_rice(dependency_example, require_canonical=False).data["schema_version"], 2
        )

    def test_rejects_duplicate_keys_and_unknown_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "plasma.json").write_text(
                '{"format_version":1,"format_version":1,"entries":[]}', encoding="utf-8"
            )
            (root / "components.json").write_text(
                json.dumps({"format_version": 1, "entries": []}), encoding="utf-8"
            )
            (root / "distro-packages.json").write_text(
                json.dumps({"format_version": 1, "entries": []}), encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "Duplicate"):
                CompatibilityDatabase.load(root)


if __name__ == "__main__":
    unittest.main()
