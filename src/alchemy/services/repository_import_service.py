from __future__ import annotations

import getpass
import json
import socket
from pathlib import Path
from typing import Any

from alchemy.domain.repository_import import (
    MAX_ANALYZED_FILE_BYTES,
    MAX_ANALYZED_TOTAL_BYTES,
    RepositoryDocument,
    analyze_repository,
    should_read_repository_blob,
    validate_repository_source,
)
from alchemy.domain.rice import canonical_json_bytes
from alchemy.domain.sanitizer import SanitizationContext
from alchemy.platform.atomic import write_bytes_atomic
from alchemy.platform.git_repository import BareGitRepository, GitRepositoryStore, GitTreeEntry

METADATA_MAX_BYTES = 64 * 1024


class RepositoryImportService:
    def __init__(
        self,
        *,
        store: GitRepositoryStore | None = None,
        sanitizer_context: SanitizationContext | None = None,
    ) -> None:
        self.store = store or GitRepositoryStore()
        self.sanitizer_context = sanitizer_context or _sanitizer_context()

    def import_repository(
        self,
        repository_url: str,
        commit: str,
        metadata_path: str,
        *,
        draft_destination: str | None = None,
    ) -> dict[str, Any]:
        validate_repository_source(repository_url, commit)
        metadata = _load_metadata(metadata_path)
        acquired = self.store.acquire(repository_url, commit)
        documents = self._load_documents(
            acquired.repository, acquired.repository.list_entries()
        )
        result = analyze_repository(
            documents,
            metadata,
            repository_url=repository_url,
            commit=commit,
            sanitizer_context=self.sanitizer_context,
        )
        payload = result.to_dict()
        payload["cache_hit"] = acquired.cache_hit
        payload["analyzed_bytes"] = sum(
            len(document.data) for document in documents if document.data is not None
        )
        payload["draft_path"] = None
        if draft_destination is not None:
            if not result.manifest_safe:
                raise RuntimeError("Unsafe publication findings prevent writing a rice draft")
            destination = _draft_path(draft_destination)
            write_bytes_atomic(
                destination,
                canonical_json_bytes(result.manifest),
                overwrite=False,
            )
            payload["draft_path"] = str(destination)
        return payload

    def _load_documents(
        self,
        repository: BareGitRepository,
        entries: tuple[GitTreeEntry, ...],
    ) -> tuple[RepositoryDocument, ...]:
        documents: list[RepositoryDocument] = []
        total = 0
        for entry in entries:
            data: bytes | None = None
            reason: str | None = None
            if entry.object_type != "blob" or entry.mode in {"120000", "160000"}:
                reason = "non-regular Git entry"
            elif entry.mode == "100755":
                reason = "executable file content is not read"
            elif entry.mode != "100644":
                reason = "unsupported Git mode"
            elif entry.size is None:
                reason = "blob size is unavailable"
            elif entry.size > MAX_ANALYZED_FILE_BYTES:
                reason = "file exceeds the 1024 KiB analysis limit"
            elif not should_read_repository_blob(entry.path):
                reason = "binary, sensitive, or unsupported extension"
            elif total + entry.size > MAX_ANALYZED_TOTAL_BYTES:
                reason = "repository exceeds the 8 MiB text-analysis limit"
            else:
                try:
                    data = repository.read_blob(entry)
                except (OSError, RuntimeError, ValueError):
                    reason = "blob was unavailable within the import limits"
                else:
                    total += len(data)
            documents.append(
                RepositoryDocument(
                    entry.path,
                    entry.mode,
                    entry.object_type,
                    entry.size,
                    data,
                    reason,
                )
            )
        return tuple(documents)


def _load_metadata(path_value: str) -> dict[str, Any]:
    candidate = Path(path_value).expanduser().absolute()
    if candidate.is_symlink():
        raise ValueError("Repository metadata must be a regular, non-symlink file")
    path = candidate.resolve(strict=True)
    if not path.is_file():
        raise ValueError("Repository metadata must be a regular, non-symlink file")
    with path.open("rb") as stream:
        raw = stream.read(METADATA_MAX_BYTES + 1)
    if len(raw) > METADATA_MAX_BYTES:
        raise ValueError("Repository metadata exceeds the 64 KiB input limit")
    try:
        parsed = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Repository metadata must be valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Repository metadata must be a JSON object")
    return parsed


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Repository metadata contains duplicate key: {key}")
        result[key] = value
    return result


def _draft_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser().absolute()
    if candidate.suffix != ".rice":
        raise ValueError("Repository draft destination must use the .rice extension")
    if candidate.is_symlink():
        raise ValueError("Repository draft destination cannot be a symlink")
    if not candidate.parent.is_dir():
        raise ValueError("Repository draft destination directory does not exist")
    return candidate


def _sanitizer_context() -> SanitizationContext:
    return SanitizationContext(
        home=str(Path.home()),
        username=getpass.getuser(),
        hostname=socket.gethostname(),
    )
