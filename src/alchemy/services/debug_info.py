from __future__ import annotations

import getpass
import json
import re
import socket
from pathlib import Path
from typing import Any

from alchemy.domain.capabilities import EnvironmentReport

_IPV4_PATTERN = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_MAC_PATTERN = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])")
_TOKEN_PATTERN = re.compile(
    r"(?i)(\b(?:token|api[_-]?key|secret|password)\b\s*[:=]\s*)[^\s,;]+"
)


def build_debug_info(report: EnvironmentReport) -> str:
    """Return a local, deterministic, redacted debug preview."""

    payload: dict[str, Any] = {
        "capabilities": report.capabilities.to_dict(),
        "settings": [setting.to_dict() for setting in report.settings],
        "warnings": list(report.warnings),
    }
    return redact(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def redact(text: str) -> str:
    replacements = {
        str(Path.home()): "<home>",
        str(Path.home()).replace("\\", "/"): "<home>",
        getpass.getuser(): "<user>",
        socket.gethostname(): "<host>",
    }
    redacted = text
    for sensitive, replacement in sorted(replacements.items(), key=lambda item: -len(item[0])):
        if sensitive:
            redacted = redacted.replace(sensitive, replacement)
    redacted = _IPV4_PATTERN.sub("<ip-address>", redacted)
    redacted = _MAC_PATTERN.sub("<mac-address>", redacted)
    return _TOKEN_PATTERN.sub(r"\1<redacted>", redacted)
