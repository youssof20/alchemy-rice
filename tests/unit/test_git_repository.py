from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alchemy.platform.git_repository import (
    MAX_ANALYZED_FILE_BYTES,
    BareGitRepository,
    GitTreeEntry,
    git_fetch_arguments,
)


class FakeExecutor:
    def __init__(self, outputs: list[bytes]) -> None:
        self.outputs = outputs
        self.calls: list[tuple[str, ...]] = []

    def run(
        self,
        arguments: tuple[str, ...],
        *,
        timeout: float,
        maximum_output: int = 4 * 1024 * 1024,
        monitored_directory: Path | None = None,
    ) -> bytes:
        self.calls.append(arguments)
        return self.outputs.pop(0)


class GitRepositoryTests(unittest.TestCase):
    def test_fetch_is_shallow_filtered_and_never_recurses_submodules(self) -> None:
        arguments = git_fetch_arguments(
            "git",
            Path("cache.git"),
            "https://github.com/example/dotfiles.git",
            "a" * 40,
        )

        self.assertIn("--depth=1", arguments)
        self.assertIn("--no-tags", arguments)
        self.assertIn("--no-recurse-submodules", arguments)
        self.assertIn("--no-auto-maintenance", arguments)
        self.assertIn(f"--filter=blob:limit={MAX_ANALYZED_FILE_BYTES + 1}", arguments)
        self.assertIn("protocol.allow=never", arguments)
        self.assertIn("protocol.https.allow=always", arguments)
        self.assertNotIn("checkout", arguments)
        self.assertNotIn("clone", arguments)

    def test_bare_reader_parses_nul_tree_and_reads_blob_by_object_id(self) -> None:
        oid = "b" * 40
        tree = f"100644 blob {oid} 4\t.config/kdeglobals\0".encode()
        executor = FakeExecutor([tree, b"data"])
        with tempfile.TemporaryDirectory() as temporary:
            repository = BareGitRepository(
                "git", Path(temporary), "a" * 40, executor
            )

            entries = repository.list_entries()
            payload = repository.read_blob(entries[0])

        self.assertEqual(
            entries,
            (GitTreeEntry(".config/kdeglobals", "100644", "blob", oid, 4),),
        )
        self.assertEqual(payload, b"data")
        self.assertEqual(executor.calls[1][-3:], ("cat-file", "blob", oid))

    def test_reader_refuses_oversized_or_non_regular_objects(self) -> None:
        executor = FakeExecutor([])
        repository = BareGitRepository("git", Path("cache"), "a" * 40, executor)
        oversized = GitTreeEntry("large.conf", "100644", "blob", "b" * 40, 1024 * 1024 + 1)
        symlink = GitTreeEntry("link", "120000", "blob", "c" * 40, 6)

        with self.assertRaisesRegex(ValueError, "per-file"):
            repository.read_blob(oversized)
        with self.assertRaisesRegex(ValueError, "regular"):
            repository.read_blob(symlink)
        self.assertEqual(executor.calls, [])


if __name__ == "__main__":
    unittest.main()
