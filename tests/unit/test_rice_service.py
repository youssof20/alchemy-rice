from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from alchemy.domain.rice import canonical_json_bytes
from alchemy.services.rice_service import RiceService
from tests.unit.test_rice_domain import capability, manifest_data


class FakeProbe:
    class Report:
        capabilities = capability()

    def inspect(self) -> Report:
        return self.Report()


class RiceServiceTests(unittest.TestCase):
    def test_export_import_and_inspect_do_not_apply_anything(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "draft.json"
            source.write_text(json.dumps(manifest_data(), indent=2), encoding="utf-8")
            destination = root / "night.rice"
            service = RiceService(
                data_root=root / "data", probe=FakeProbe()  # type: ignore[arg-type]
            )

            exported = service.export(str(source), str(destination))
            inspected = service.inspect(str(destination), expected_sha256=exported["sha256"])
            imported = service.import_manifest(
                str(destination), expected_sha256=exported["sha256"]
            )

            self.assertEqual(destination.read_bytes(), canonical_json_bytes(manifest_data()))
            self.assertTrue(inspected["valid"])
            self.assertFalse(imported["applied"])
            self.assertEqual(
                Path(imported["path"]).read_bytes(), destination.read_bytes()
            )

    def test_export_refuses_overwrite_and_import_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "draft.json"
            source.write_text(json.dumps(manifest_data()), encoding="utf-8")
            destination = root / "night.rice"
            service = RiceService(
                data_root=root / "data", probe=FakeProbe()  # type: ignore[arg-type]
            )
            service.export(str(source), str(destination))

            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                service.export(str(source), str(destination))
            with self.assertRaisesRegex(ValueError, "mismatch"):
                service.import_manifest(str(destination), expected_sha256="0" * 64)

    def test_import_detects_tampered_hash_named_cache_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "night.rice"
            canonical = canonical_json_bytes(manifest_data())
            source.write_bytes(canonical)
            service = RiceService(
                data_root=root / "data", probe=FakeProbe()  # type: ignore[arg-type]
            )
            imported = service.import_manifest(str(source))
            Path(imported["path"]).write_bytes(b"tampered")

            with self.assertRaisesRegex(RuntimeError, "integrity verification"):
                service.import_manifest(str(source))

    def test_invalid_override_does_not_partially_import_base(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "night.rice"
            source.write_bytes(canonical_json_bytes(manifest_data()))
            override = root / "override.json"
            override.write_text(
                json.dumps(
                    {
                        "override_version": 1,
                        "base": {
                            "id": "wrong:base",
                            "version": "1.2.0",
                            "sha256": "0" * 64,
                        },
                        "components": {"cursor": {"size": 48}},
                    }
                ),
                encoding="utf-8",
            )
            service = RiceService(
                data_root=root / "data", probe=FakeProbe()  # type: ignore[arg-type]
            )

            with self.assertRaisesRegex(ValueError, "does not match"):
                service.import_manifest(str(source), override_path=str(override))

            self.assertFalse((root / "data").exists())


if __name__ == "__main__":
    unittest.main()
