from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from alchemy.domain.repository_import import (
    MAX_ANALYZED_FILE_BYTES,
    MAX_REPOSITORY_FILES,
    validate_repository_source,
)

FETCH_TIMEOUT_SECONDS = 60.0
READ_TIMEOUT_SECONDS = 10.0
MAX_CACHE_BYTES = 128 * 1024 * 1024
MAX_GIT_OUTPUT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class GitTreeEntry:
    path: str
    mode: str
    object_type: str
    oid: str
    size: int | None


class GitCommandExecutor(Protocol):
    def run(
        self,
        arguments: Sequence[str],
        *,
        timeout: float,
        maximum_output: int = MAX_GIT_OUTPUT_BYTES,
        monitored_directory: Path | None = None,
    ) -> bytes: ...


class SubprocessGitExecutor:
    """Run fixed Git argument vectors with bounded output, time, and cache growth."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        self._environment = environment

    def run(
        self,
        arguments: Sequence[str],
        *,
        timeout: float,
        maximum_output: int = MAX_GIT_OUTPUT_BYTES,
        monitored_directory: Path | None = None,
    ) -> bytes:
        argv = tuple(str(argument) for argument in arguments)
        if not argv:
            raise ValueError("Git command cannot be empty")
        started = time.monotonic()
        with tempfile.TemporaryFile() as output:
            try:
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    env=self._environment,
                    shell=False,
                )
            except OSError as exc:
                raise RuntimeError("Unable to start the local Git executable") from exc
            failure: str | None = None
            while process.poll() is None:
                if time.monotonic() - started > timeout:
                    failure = "Git operation exceeded its time limit"
                    break
                if output.tell() > maximum_output:
                    failure = "Git operation exceeded its output limit"
                    break
                if (
                    monitored_directory is not None
                    and _directory_size(monitored_directory) > MAX_CACHE_BYTES
                ):
                    failure = "Git repository exceeded its cache size limit"
                    break
                time.sleep(0.05)
            if failure is not None:
                process.kill()
                process.wait(timeout=5)
                raise RuntimeError(failure)
            if process.returncode != 0:
                raise RuntimeError("Git rejected the pinned repository operation")
            if output.tell() > maximum_output:
                raise RuntimeError("Git operation exceeded its output limit")
            if (
                monitored_directory is not None
                and _directory_size(monitored_directory) > MAX_CACHE_BYTES
            ):
                raise RuntimeError("Git repository exceeded its cache size limit")
            output.seek(0)
            return output.read(maximum_output + 1)


@dataclass(frozen=True, slots=True)
class AcquiredRepository:
    repository: BareGitRepository
    cache_hit: bool


class BareGitRepository:
    def __init__(
        self,
        git_path: str,
        repository_path: Path,
        commit: str,
        executor: GitCommandExecutor,
    ) -> None:
        self._git_path = git_path
        self._repository_path = repository_path
        self.commit = commit
        self._executor = executor

    def list_entries(self) -> tuple[GitTreeEntry, ...]:
        raw = self._executor.run(
            git_tree_arguments(self._git_path, self._repository_path, self.commit),
            timeout=READ_TIMEOUT_SECONDS,
            maximum_output=MAX_GIT_OUTPUT_BYTES,
        )
        records = raw.split(b"\0")
        if records and not records[-1]:
            records.pop()
        if len(records) > MAX_REPOSITORY_FILES:
            raise ValueError(
                f"Repository contains more than {MAX_REPOSITORY_FILES} entries"
            )
        return tuple(_parse_tree_entry(record) for record in records)

    def read_blob(self, entry: GitTreeEntry) -> bytes:
        if entry.object_type != "blob" or entry.mode not in {"100644", "100755"}:
            raise ValueError("Only regular Git blobs can be read")
        if entry.size is None or entry.size > MAX_ANALYZED_FILE_BYTES:
            raise ValueError("Git blob exceeds the per-file analysis limit")
        raw = self._executor.run(
            git_blob_arguments(self._git_path, self._repository_path, entry.oid),
            timeout=READ_TIMEOUT_SECONDS,
            maximum_output=entry.size,
            monitored_directory=self._repository_path,
        )
        if len(raw) != entry.size:
            raise RuntimeError("Git blob size changed during import")
        return raw


class GitRepositoryStore:
    def __init__(
        self,
        *,
        cache_root: Path | None = None,
        git_path: str | None = None,
        executor: GitCommandExecutor | None = None,
    ) -> None:
        resolved_git = git_path or shutil.which("git")
        if resolved_git is None:
            raise RuntimeError("Repository import requires Git")
        self.git_path = resolved_git
        self.cache_root = (cache_root or _default_cache_root()).absolute()
        self.executor = executor or SubprocessGitExecutor(_isolated_git_environment())

    def acquire(self, repository_url: str, commit: str) -> AcquiredRepository:
        validate_repository_source(repository_url, commit)
        self.cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.cache_root.is_symlink() or not self.cache_root.is_dir():
            raise RuntimeError("Repository cache root must be a regular directory")
        cache_key = hashlib.sha256(
            f"{repository_url}\0{commit}".encode()
        ).hexdigest()
        destination = self.cache_root / f"{cache_key}.git"
        if destination.exists():
            if destination.is_symlink() or not destination.is_dir():
                raise RuntimeError("Repository cache entry is not a regular directory")
            if _directory_size(destination) > MAX_CACHE_BYTES:
                raise RuntimeError("Cached repository exceeds the cache size limit")
            self._verify_commit(destination, commit)
            return AcquiredRepository(
                BareGitRepository(
                    self.git_path, destination, commit, self.executor
                ),
                True,
            )

        temporary = self.cache_root / f".{cache_key}.{uuid.uuid4().hex}.git"
        template = self.cache_root / ".empty-template"
        template.mkdir(exist_ok=True, mode=0o700)
        try:
            self.executor.run(
                git_init_arguments(self.git_path, temporary, template),
                timeout=READ_TIMEOUT_SECONDS,
            )
            self.executor.run(
                git_fetch_arguments(
                    self.git_path, temporary, repository_url, commit
                ),
                timeout=FETCH_TIMEOUT_SECONDS,
                monitored_directory=temporary,
            )
            resolved = self._resolve_fetched_commit(temporary)
            if resolved != commit:
                raise RuntimeError("Fetched repository did not resolve to the pinned commit")
            try:
                temporary.rename(destination)
            except FileExistsError:
                _remove_cache_entry(temporary, self.cache_root)
            self._verify_commit(destination, commit)
        except Exception:
            _remove_cache_entry(temporary, self.cache_root)
            raise
        return AcquiredRepository(
            BareGitRepository(self.git_path, destination, commit, self.executor),
            False,
        )

    def _resolve_fetched_commit(self, repository_path: Path) -> str:
        raw = self.executor.run(
            git_resolve_arguments(
                self.git_path, repository_path, "refs/alchemy/import^{commit}"
            ),
            timeout=READ_TIMEOUT_SECONDS,
            maximum_output=128,
        )
        return _parse_resolved_commit(raw)

    def _verify_commit(self, repository_path: Path, commit: str) -> None:
        raw = self.executor.run(
            git_resolve_arguments(
                self.git_path, repository_path, "refs/alchemy/import^{commit}"
            ),
            timeout=READ_TIMEOUT_SECONDS,
            maximum_output=128,
        )
        if _parse_resolved_commit(raw) != commit:
            raise RuntimeError("Cached repository does not match the pinned commit")


def git_init_arguments(git_path: str, repository_path: Path, template: Path) -> tuple[str, ...]:
    return (
        git_path,
        "init",
        "--bare",
        f"--template={template}",
        str(repository_path),
    )


def git_fetch_arguments(
    git_path: str, repository_path: Path, repository_url: str, commit: str
) -> tuple[str, ...]:
    return (
        git_path,
        "-c",
        "core.hooksPath=NUL" if os.name == "nt" else "core.hooksPath=/dev/null",
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        "-c",
        "fetch.fsckObjects=true",
        "-c",
        "transfer.fsckObjects=true",
        "-c",
        "http.followRedirects=initial",
        "-c",
        "http.sslVerify=true",
        f"--git-dir={repository_path}",
        "fetch",
        "--depth=1",
        "--no-tags",
        "--no-recurse-submodules",
        "--no-auto-maintenance",
        f"--filter=blob:limit={MAX_ANALYZED_FILE_BYTES + 1}",
        repository_url,
        f"{commit}:refs/alchemy/import",
    )


def git_resolve_arguments(
    git_path: str, repository_path: Path, revision: str
) -> tuple[str, ...]:
    return (
        git_path,
        f"--git-dir={repository_path}",
        "rev-parse",
        "--verify",
        revision,
    )


def git_tree_arguments(
    git_path: str, repository_path: Path, commit: str
) -> tuple[str, ...]:
    return (
        git_path,
        f"--git-dir={repository_path}",
        "ls-tree",
        "-r",
        "-z",
        "-l",
        "--full-tree",
        commit,
    )


def git_blob_arguments(
    git_path: str, repository_path: Path, oid: str
) -> tuple[str, ...]:
    return (git_path, f"--git-dir={repository_path}", "cat-file", "blob", oid)


def _parse_tree_entry(record: bytes) -> GitTreeEntry:
    try:
        header, raw_path = record.split(b"\t", 1)
        mode, object_type, oid, raw_size = header.split(b" ", 3)
        mode_text = mode.decode("ascii")
        type_text = object_type.decode("ascii")
        oid_text = oid.decode("ascii")
        size_text = raw_size.decode("ascii")
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Git tree contains an unrepresentable entry") from exc
    if (
        len(oid_text) != 40
        or any(character not in "0123456789abcdef" for character in oid_text)
        or mode_text not in {"100644", "100755", "120000", "160000"}
        or type_text not in {"blob", "commit"}
    ):
        raise ValueError("Git tree contains an unsupported entry")
    size = None if size_text == "-" else int(size_text)
    if size is not None and size < 0:
        raise ValueError("Git tree reported a negative blob size")
    try:
        path = raw_path.decode("utf-8")
    except UnicodeDecodeError:
        digest = hashlib.sha256(raw_path).hexdigest()[:12]
        path = f"<non-utf8-path:{digest}>"
        type_text = "unsupported"
    return GitTreeEntry(path, mode_text, type_text, oid_text, size)


def _parse_resolved_commit(raw: bytes) -> str:
    value = raw.decode("ascii", errors="strict").strip()
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise RuntimeError("Git returned an invalid commit identity")
    return value


def _isolated_git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key in {
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_ASKPASS",
            "GIT_CONFIG_COUNT",
            "GIT_DIR",
            "GIT_EXEC_PATH",
            "GIT_OBJECT_DIRECTORY",
            "GIT_TEMPLATE_DIR",
            "GIT_WORK_TREE",
        } or key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
            environment.pop(key, None)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
        }
    )
    return environment


def _directory_size(path: Path) -> int:
    total = 0
    try:
        for directory, _, files in os.walk(path):
            for filename in files:
                try:
                    total += (Path(directory) / filename).stat().st_size
                except OSError:
                    continue
                if total > MAX_CACHE_BYTES:
                    return total
    except OSError:
        return MAX_CACHE_BYTES + 1
    return total


def _remove_cache_entry(path: Path, cache_root: Path) -> None:
    if not path.exists():
        return
    resolved_root = cache_root.resolve(strict=True)
    resolved_path = path.resolve(strict=True)
    if resolved_path.parent != resolved_root or not path.name.startswith("."):
        raise RuntimeError("Refusing to remove an unexpected repository cache path")
    shutil.rmtree(resolved_path)


def _default_cache_root() -> Path:
    configured = os.environ.get("XDG_CACHE_HOME")
    if configured:
        return Path(configured).expanduser() / "alchemy" / "repositories"
    return Path.home() / ".cache" / "alchemy" / "repositories"
