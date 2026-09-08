from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class TransactionState(StrEnum):
    PLANNED = "planned"
    APPLYING = "applying"
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Operation:
    operation_id: str
    driver: str
    target: str
    description: str
    before: str | None
    after: str
    command: tuple[str, ...]
    affected_paths: tuple[str, ...]
    requires_privilege: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["command"] = list(self.command)
        payload["affected_paths"] = list(self.affected_paths)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Operation:
        return cls(
            operation_id=str(payload["operation_id"]),
            driver=str(payload["driver"]),
            target=str(payload["target"]),
            description=str(payload["description"]),
            before=_optional_string(payload.get("before")),
            after=str(payload["after"]),
            command=tuple(str(value) for value in payload["command"]),
            affected_paths=tuple(str(value) for value in payload["affected_paths"]),
            requires_privilege=bool(payload.get("requires_privilege", False)),
        )


@dataclass(frozen=True, slots=True)
class VerificationResult:
    matched: bool
    observed: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)
