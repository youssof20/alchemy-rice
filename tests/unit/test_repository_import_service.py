from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from alchemy.domain.sanitizer import SanitizationContext
from alchemy.platform.git_repository import GitTreeEntry
from alchemy.services.repository_import_service import RepositoryImportService
from tests.unit.test_repository_import import COMMIT, REPOSITORY, metadata


class FakeRepository:
    def __init__(self, entries: tuple[GitTreeEntry, ...], blobs: dict[str, bytes]) -> None:
        self.entries = entries
        self.blobs = blobs
        self.read_paths: list[str] = []

    def list_entries(self) -> tuple[GitTreeEntry, ...]:
        return self.entries

    def read_blob(self, entry: GitTreeEntry) -> bytes:
        self.read_paths.append(entry.path)
        return self.blobs[entry.path]


class FakeStore:
    def __init__(self, repository: FakeRepository) -> None:
        self.repository = repository

    def acquire(self, repository_url: str, commit: str) -> SimpleNamespace:
        if (repository_url, commit) != (REPOSITORY, COMMIT):
            raise AssertionError("unexpected repository identity")
        return SimpleNamespace(repository=self.repository, cache_hit=False)


class RepositoryImportServiceTests(unittest.TestCase):
    def test_import_reads_only_static_text_and_writes_nonapplying_draft(self) -> None:
        oid = "b" * 40
        config = b"[General]\nColorScheme=BreezeDark\n"
        entries = (
            GitTreeEntry(".config/kdeglobals", "100644", "blob", oid, len(config)),
            GitTreeEntry("wallpapers/night.png", "100644", "blob", "c" * 40, 100),
            GitTreeEntry("archive.zip", "100644", "blob", "d" * 40, 200),
            GitTreeEntry(".env", "100644", "blob", "e" * 40, 20),
            GitTreeEntry("install.sh", "100755", "blob", "f" * 40, 30),
        )
        repository = FakeRepository(entries, {".config/kdeglobals": config})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata_path = root / "metadata.json"
            metadata_path.write_text(json.dumps(metadata()), encoding="utf-8")
            destination = root / "imported.rice"
            service = RepositoryImportService(
                store=FakeStore(repository),  # type: ignore[arg-type]
                sanitizer_context=SanitizationContext(),
            )

            result = service.import_repository(
                REPOSITORY,
                COMMIT,
                str(metadata_path),
                draft_destination=str(destination),
            )

            self.assertEqual(repository.read_paths, [".config/kdeglobals"])
            self.assertEqual(result["analyzed_bytes"], len(config))
            self.assertEqual(result["draft_path"], str(destination))
            self.assertTrue(destination.is_file())
            self.assertFalse(result["applied"])
            self.assertFalse(result["executed_repository_code"])
            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                service.import_repository(
                    REPOSITORY,
                    COMMIT,
                    str(metadata_path),
                    draft_destination=str(destination),
                )

    def test_metadata_rejects_duplicate_keys_before_fetch(self) -> None:
        repository = FakeRepository((), {})
        store = FakeStore(repository)
        with tempfile.TemporaryDirectory() as temporary:
            metadata_path = Path(temporary) / "metadata.json"
            metadata_path.write_text('{"id":"one","id":"two"}', encoding="utf-8")
            service = RepositoryImportService(
                store=store,  # type: ignore[arg-type]
                sanitizer_context=SanitizationContext(),
            )

            with self.assertRaisesRegex(ValueError, "duplicate key"):
                service.import_repository(REPOSITORY, COMMIT, str(metadata_path))


if __name__ == "__main__":
    unittest.main()
