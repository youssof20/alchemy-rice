from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alchemy import __version__
from alchemy.domain.transactions import Operation, TransactionState, VerificationResult
from alchemy.platform.atomic import write_json_atomic

_ALLOWED_TRANSITIONS = {
    TransactionState.PLANNED: {
        TransactionState.APPLYING,
        TransactionState.ROLLING_BACK,
        TransactionState.FAILED,
    },
    TransactionState.APPLYING: {
        TransactionState.COMMITTED,
        TransactionState.ROLLING_BACK,
        TransactionState.FAILED,
    },
    TransactionState.COMMITTED: {TransactionState.ROLLING_BACK},
    TransactionState.ROLLING_BACK: {TransactionState.ROLLED_BACK, TransactionState.FAILED},
    TransactionState.ROLLED_BACK: set(),
    TransactionState.FAILED: {TransactionState.ROLLING_BACK},
}


class JournalStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def create(
        self,
        *,
        operation: Operation,
        snapshot_id: str,
        environment: dict[str, Any],
        rice: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        transaction_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        record: dict[str, Any] = {
            "transaction_id": transaction_id,
            "started_at": now,
            "updated_at": now,
            "application_version": __version__,
            "environment": environment,
            "rice": rice,
            "snapshot_id": snapshot_id,
            "operations": [operation.to_dict()],
            "current_operation_index": None,
            "verification": None,
            "rollback_status": None,
            "state": TransactionState.PLANNED.value,
            "error": None,
        }
        self.save(record)
        return record

    def transition(
        self,
        record: dict[str, Any],
        state: TransactionState,
        *,
        current_operation_index: int | None = None,
        verification: VerificationResult | None = None,
        rollback_status: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        current = TransactionState(record["state"])
        if state not in _ALLOWED_TRANSITIONS[current]:
            raise ValueError(f"Invalid journal transition: {current.value} -> {state.value}")
        updated = dict(record)
        updated.update(
            {
                "state": state.value,
                "updated_at": datetime.now(UTC).isoformat(),
                "current_operation_index": current_operation_index,
                "verification": (
                    verification.to_dict() if verification else record.get("verification")
                ),
                "rollback_status": rollback_status,
                "error": error,
            }
        )
        self.save(updated)
        return updated

    def save(self, record: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.path_for(str(record["transaction_id"])), record)

    def load(self, transaction_id: str) -> dict[str, Any]:
        payload = json.loads(self.path_for(transaction_id).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Transaction journal must be a JSON object")
        return payload

    def incomplete(self) -> tuple[dict[str, Any], ...]:
        active = {
            TransactionState.PLANNED.value,
            TransactionState.APPLYING.value,
            TransactionState.ROLLING_BACK.value,
        }
        return tuple(record for record in self.all() if record.get("state") in active)

    def latest(self, state: TransactionState | None = None) -> dict[str, Any] | None:
        records = self.all()
        if state is not None:
            records = tuple(record for record in records if record.get("state") == state.value)
        return max(records, key=lambda item: str(item.get("started_at", "")), default=None)

    def all(self) -> tuple[dict[str, Any], ...]:
        if not self.directory.exists():
            return ()
        records: list[dict[str, Any]] = []
        for path in self.directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return tuple(records)

    def path_for(self, transaction_id: str) -> Path:
        try:
            normalized = str(uuid.UUID(transaction_id))
        except ValueError as exc:
            raise ValueError("Invalid transaction id") from exc
        return self.directory / f"{normalized}.json"
