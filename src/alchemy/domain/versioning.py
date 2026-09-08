from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION = re.compile(r"^(0|[1-9]\d{0,2})\.(0|[1-9]\d{0,2})(?:\.(0|[1-9]\d{0,2}))?$")
_CLAUSE = re.compile(r"^(>=|<=|==|>|<)(\d+\.\d+(?:\.\d+)?)$")


@dataclass(frozen=True, order=True, slots=True)
class Version:
    major: int
    minor: int
    patch: int = 0

    @classmethod
    def parse(cls, value: str) -> Version:
        match = _VERSION.fullmatch(value)
        if match is None:
            raise ValueError(f"Invalid numeric version: {value}")
        return cls(int(match[1]), int(match[2]), int(match[3] or 0))


@dataclass(frozen=True, slots=True)
class VersionClause:
    operator: str
    version: Version

    def matches(self, candidate: Version) -> bool:
        return {
            ">=": candidate >= self.version,
            ">": candidate > self.version,
            "<=": candidate <= self.version,
            "<": candidate < self.version,
            "==": candidate == self.version,
        }[self.operator]


@dataclass(frozen=True, slots=True)
class VersionRange:
    clauses: tuple[VersionClause, ...]

    @classmethod
    def parse(cls, value: str) -> VersionRange:
        if not value or len(value) > 128 or any(character.isspace() for character in value):
            raise ValueError("Version range has invalid whitespace or length")
        clauses: list[VersionClause] = []
        for raw_clause in value.split(","):
            match = _CLAUSE.fullmatch(raw_clause)
            if match is None:
                raise ValueError(f"Invalid version range clause: {raw_clause}")
            clauses.append(VersionClause(match[1], Version.parse(match[2])))
        version_range = cls(tuple(clauses))
        version_range._validate_possible()
        return version_range

    def matches(self, value: str | Version) -> bool:
        candidate = Version.parse(value) if isinstance(value, str) else value
        return all(clause.matches(candidate) for clause in self.clauses)

    def _validate_possible(self) -> None:
        equalities = {clause.version for clause in self.clauses if clause.operator == "=="}
        if len(equalities) > 1:
            raise ValueError("Version range contains conflicting equality clauses")
        if equalities:
            candidate = next(iter(equalities))
            if not all(clause.matches(candidate) for clause in self.clauses):
                raise ValueError("Version range cannot match any version")
            return
        lower: tuple[Version, bool] | None = None
        upper: tuple[Version, bool] | None = None
        for clause in self.clauses:
            if clause.operator in {">", ">="}:
                inclusive = clause.operator == ">="
                if lower is None or clause.version > lower[0]:
                    lower = (clause.version, inclusive)
                elif clause.version == lower[0]:
                    lower = (clause.version, lower[1] and inclusive)
            elif clause.operator in {"<", "<="}:
                inclusive = clause.operator == "<="
                if upper is None or clause.version < upper[0]:
                    upper = (clause.version, inclusive)
                elif clause.version == upper[0]:
                    upper = (clause.version, upper[1] and inclusive)
        if lower is None:
            candidate = Version(0, 0, 0)
        elif lower[1]:
            candidate = lower[0]
        else:
            candidate = Version(lower[0].major, lower[0].minor, lower[0].patch + 1)
        if not all(clause.matches(candidate) for clause in self.clauses):
            raise ValueError("Version range cannot match any version")
