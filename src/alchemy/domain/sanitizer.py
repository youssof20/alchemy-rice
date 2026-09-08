from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_POSIX_HOME = re.compile(r"^/(?:home|Users)/[^/]+(?:/|$)")
_TOKEN_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*", re.IGNORECASE),
)
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"oauth|password|passwd|private[_-]?key|recent(?:[_-]?files?)?|history)(?:$|[_-])",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SanitizationContext:
    home: str | None = None
    username: str | None = None
    hostname: str | None = None
    wifi_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SanitizationFinding:
    code: str
    path: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SanitizationReport:
    findings: tuple[SanitizationFinding, ...]

    @property
    def safe(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "safe": self.safe,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def scan_publication(value: Any, context: SanitizationContext) -> SanitizationReport:
    """Find publication hazards without retaining or returning matched values."""

    findings: list[SanitizationFinding] = []

    def add(code: str, path: str, detail: str) -> None:
        finding = SanitizationFinding(code, path or "/", detail)
        if finding not in findings:
            findings.append(finding)

    def visit(item: Any, path: str) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = f"{path}/{_pointer(str(key))}"
                if _sensitive_key(str(key)):
                    add(
                        "non_visual_or_sensitive_key",
                        child_path,
                        "A sensitive or history key is forbidden",
                    )
                visit(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}/{index}")
        elif isinstance(item, str):
            _scan_string(item, path or "/", context, add)

    visit(value, "")
    return SanitizationReport(tuple(findings))


def _scan_string(
    value: str,
    path: str,
    context: SanitizationContext,
    add: Callable[[str, str, str], None],
) -> None:
    if _EMAIL.search(value):
        add("email_address", path, "An email address may identify the creator")
    if _PRIVATE_KEY.search(value) or "ssh-private-key" in value.lower():
        add("private_key", path, "A private-key marker is forbidden")
    if any(pattern.search(value) for pattern in _TOKEN_PATTERNS):
        add("token_like_value", path, "A credential-shaped value is forbidden")

    stripped = value.strip()
    is_https_url = urlsplit(stripped).scheme.lower() == "https"
    normalized = stripped.replace("\\", "/")
    if not is_https_url and (
        _WINDOWS_PATH.match(stripped)
        or _POSIX_HOME.match(normalized)
        or normalized.startswith(("/", "~/"))
        or "$HOME" in stripped
        or "${HOME}" in stripped
        or "%USERPROFILE%" in stripped.upper()
        or "$ENV:USERPROFILE" in stripped.upper()
    ):
        add("absolute_or_home_path", path, "A local or home-relative path is forbidden")

    home = _normalized_path(context.home)
    if home and home.casefold() in normalized.casefold():
        add("home_directory", path, "The current home directory is forbidden")
    if _contains_identity(value, context.username):
        add("username", path, "The current local username may identify the creator")
    if _contains_identity(value, context.hostname):
        add("hostname", path, "The current hostname may identify the creator")
    for wifi_name in context.wifi_names:
        if wifi_name and wifi_name.casefold() in value.casefold():
            add("wifi_name", path, "A known Wi-Fi network name may identify a location")
            break


def _contains_identity(value: str, identity: str | None) -> bool:
    if identity is None or len(identity.strip()) < 3:
        return False
    pattern = rf"(?<![A-Za-z0-9]){re.escape(identity.strip())}(?![A-Za-z0-9])"
    return re.search(pattern, value, re.I) is not None


def _sensitive_key(value: str) -> bool:
    if _SENSITIVE_KEY.search(value):
        return True
    flattened = re.sub(r"[^a-z0-9]", "", value.casefold())
    return any(
        marker in flattened
        for marker in (
            "apikey",
            "accesstoken",
            "authtoken",
            "clientsecret",
            "oauthsecret",
            "privatekey",
            "recentfile",
            "recentdocument",
            "sessionstate",
            "windowgeometry",
            "lastopened",
        )
    ) or flattened in {"history", "password", "passwd", "state"}


def _normalized_path(value: str | None) -> str | None:
    if not value:
        return None
    return str(Path(value)).replace("\\", "/").rstrip("/") or None


def _pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")
