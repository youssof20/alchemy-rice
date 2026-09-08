from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CommandResult:
    arguments: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


class Runner(Protocol):
    def run(self, arguments: Sequence[str], *, timeout: float = 3.0) -> CommandResult: ...


class CommandRunner:
    """Run reviewed commands as argument vectors, never through a shell.

    The inspector invokes this runner outside the Qt event loop. GUI refreshes run
    it in a worker thread so a slow desktop service cannot block the interface.
    """

    def __init__(self, *, environment: Mapping[str, str] | None = None) -> None:
        self._environment = environment

    def run(self, arguments: Sequence[str], *, timeout: float = 3.0) -> CommandResult:
        argv = tuple(str(argument) for argument in arguments)
        if not argv:
            raise ValueError("A command requires at least one argument")
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                check=False,
                env=self._environment,
                shell=False,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                arguments=argv,
                returncode=-1,
                stdout=_coerce_text(exc.stdout),
                stderr=_coerce_text(exc.stderr),
                timed_out=True,
            )
        except OSError as exc:
            return CommandResult(argv, -1, "", str(exc))
        return CommandResult(argv, completed.returncode, completed.stdout, completed.stderr)


def executable_name(path: str | Path | None) -> str | None:
    if path is None:
        return None
    return Path(path).name


def _coerce_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value
