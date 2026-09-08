from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

EVIDENCE_SCHEMA_URI = (
    "https://raw.githubusercontent.com/youssof20/alchemy-rice/main/"
    "schemas/release-evidence-v1.schema.json"
)
EVIDENCE_MAX_BYTES = 256 * 1024
MIN_EXTERNAL_BETA_REPORTS = 5

REQUIRED_PACKAGE_PATHS = {
    "arch": "packaging/arch/PKGBUILD",
    "debian": "debian/control",
}
REQUIRED_VM_IDS = (
    "arch-plasma-6.7-wayland",
    "fedora-kde-current-wayland",
    "kde-neon-plm-transition",
    "kubuntu-supported-wayland",
    "plasma-6.8-wayland",
    "hardware-multimonitor-scaling",
    "nixos-plasma-manager",
)
REQUIRED_DESTRUCTIVE_IDS = (
    "kill-gui-mid-apply",
    "kill-worker-mid-apply",
    "forced-verification-failure",
    "unwritable-snapshot-directory",
    "dependency-removed-after-plan",
    "incomplete-journal-recovery",
    "malformed-rice",
    "rice-hash-mismatch",
    "config-symlink",
    "repository-secret-fixtures",
)
REQUIRED_PUBLIC_FILES = (
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "PRIVACY.md",
    "ARCHITECTURE.md",
    "RICE_FORMAT.md",
    "COMPATIBILITY.md",
    "PACKAGING.md",
    "CHANGELOG.md",
    "RELEASE.md",
)

_HASH = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_PEP440_RELEASE = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+|\.dev[0-9]+)?$"
)
_PLASMA = re.compile(r"^6\.[0-9]+(?:\.[0-9]+)?$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")
_STATUS = {"pending", "passed", "failed"}


def read_release_evidence(path_value: str | Path) -> dict[str, Any]:
    candidate = Path(path_value).expanduser().absolute()
    if candidate.is_symlink():
        raise ValueError("Release evidence must be a regular, non-symlink file")
    path = candidate.resolve(strict=True)
    if not path.is_file():
        raise ValueError("Release evidence must be a regular, non-symlink file")
    with path.open("rb") as stream:
        raw = stream.read(EVIDENCE_MAX_BYTES + 1)
    return parse_release_evidence(raw)


def parse_release_evidence(raw: bytes) -> dict[str, Any]:
    if len(raw) > EVIDENCE_MAX_BYTES:
        raise ValueError("Release evidence exceeds the 256 KiB input limit")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Release evidence must be valid UTF-8 JSON") from exc
    evidence = _object(value, "Release evidence")
    allowed = {
        "$schema",
        "format_version",
        "release",
        "source_commit",
        "packages",
        "vm_results",
        "destructive_tests",
        "beta_reports",
        "recording",
        "community_rice",
    }
    _strict(evidence, allowed, allowed, "Release evidence")
    if evidence["$schema"] != EVIDENCE_SCHEMA_URI:
        raise ValueError("Release evidence uses an unsupported schema URI")
    if evidence["format_version"] != 1 or isinstance(evidence["format_version"], bool):
        raise ValueError("Release evidence format_version must be 1")
    release = _text(evidence["release"], "Release version", 32)
    if _PEP440_RELEASE.fullmatch(release) is None:
        raise ValueError("Release version must be a normalized PEP 440 release")
    commit = _text(evidence["source_commit"], "Source commit", 40)
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("Source commit must be a full lowercase SHA-1 commit")

    packages = _packages(evidence["packages"])
    vm_results = _vm_results(evidence["vm_results"])
    destructive = _destructive_tests(evidence["destructive_tests"])
    beta_reports = _beta_reports(evidence["beta_reports"])
    recording = _recording(evidence["recording"])
    community_rice = _community_rice(evidence["community_rice"])
    return {
        "$schema": EVIDENCE_SCHEMA_URI,
        "format_version": 1,
        "release": release,
        "source_commit": commit,
        "packages": packages,
        "vm_results": vm_results,
        "destructive_tests": destructive,
        "beta_reports": beta_reports,
        "recording": recording,
        "community_rice": community_rice,
    }


def evaluate_release(evidence: dict[str, Any], repository_root: Path) -> dict[str, Any]:
    validated = parse_release_evidence(
        json.dumps(evidence, ensure_ascii=False, separators=(",", ":")).encode()
    )
    root = repository_root.resolve(strict=True)
    beta_blockers: list[dict[str, str]] = []
    launch_blockers: list[dict[str, str]] = []

    if ".dev" in validated["release"] or re.search(r"a[0-9]+$", validated["release"]):
        _block(
            beta_blockers,
            "release.version",
            "Public beta evidence must use a beta, release-candidate, or stable version",
        )
    if set(validated["source_commit"]) == {"0"}:
        _block(beta_blockers, "source.commit", "Record the exact tested public commit")
    for relative in REQUIRED_PUBLIC_FILES:
        if not (root / relative).is_file():
            _block(beta_blockers, f"public.{relative}", f"Missing public file: {relative}")
    for package, relative in REQUIRED_PACKAGE_PATHS.items():
        if not (root / relative).is_file():
            _block(beta_blockers, f"package.{package}", f"Missing package path: {relative}")
        record = validated["packages"][package]
        if record["status"] != "passed":
            _block(
                beta_blockers,
                f"package.{package}",
                f"{package} package build/install/remove smoke test is not passed",
            )

    vm_by_id = {item["id"]: item for item in validated["vm_results"]}
    if vm_by_id["arch-plasma-6.7-wayland"]["status"] != "passed":
        _block(beta_blockers, "vm.arch", "Arch Plasma 6.7 Wayland baseline is not passed")
    non_arch_baselines = (
        "fedora-kde-current-wayland",
        "kde-neon-plm-transition",
        "kubuntu-supported-wayland",
    )
    if not any(vm_by_id[item]["status"] == "passed" for item in non_arch_baselines):
        _block(beta_blockers, "vm.non_arch", "No non-Arch KDE baseline is passed")

    destructive_by_id = {item["id"]: item for item in validated["destructive_tests"]}
    for test_id in REQUIRED_DESTRUCTIVE_IDS:
        if destructive_by_id[test_id]["status"] != "passed":
            _block(
                beta_blockers,
                f"destructive.{test_id}",
                "Destructive recovery scenario is not passed",
            )

    launch_blockers.extend(beta_blockers)
    for vm_id in REQUIRED_VM_IDS:
        if vm_by_id[vm_id]["status"] != "passed":
            _block(
                launch_blockers,
                f"vm.{vm_id}",
                "Required VM or hardware result is not passed",
            )

    accepted_reports = [
        item for item in validated["beta_reports"] if item["outcome"] in {"passed", "resolved"}
    ]
    if len(accepted_reports) < MIN_EXTERNAL_BETA_REPORTS:
        _block(
            launch_blockers,
            "beta.report_count",
            f"Need at least {MIN_EXTERNAL_BETA_REPORTS} external passed/resolved beta reports",
        )
    if len({item["distro"] for item in accepted_reports}) < 2:
        _block(launch_blockers, "beta.distros", "Beta evidence must cover multiple distros")
    plasma_points = {
        ".".join(item["plasma_version"].split(".")[:2]) for item in accepted_reports
    }
    if len(plasma_points) < 2:
        _block(
            launch_blockers,
            "beta.plasma_points",
            "Beta evidence must cover at least two Plasma point releases",
        )

    recording = validated["recording"]
    if recording is None:
        _block(
            launch_blockers,
            "recording",
            "A real 20-40 second Plasma 6.7 Wayland apply/verify/revert recording is missing",
        )
    else:
        required_recording_flags = (
            "shows_apply",
            "shows_verify",
            "shows_revert",
            "multiple_applications",
        )
        if not all(recording[flag] for flag in required_recording_flags):
            _block(launch_blockers, "recording.content", "Recording proof is incomplete")
        if recording["generated_visuals"]:
            _block(launch_blockers, "recording.authenticity", "Generated visuals are prohibited")
        if recording["session"] != "wayland" or not recording["plasma_version"].startswith("6.7"):
            _block(
                launch_blockers,
                "recording.environment",
                "Launch recording must show a real Plasma 6.7 Wayland session",
            )

    community_rice = validated["community_rice"]
    if community_rice is None or community_rice["status"] != "passed":
        _block(
            launch_blockers,
            "community_rice",
            "A pinned community-style rice import/apply report is not passed",
        )

    return {
        "release": validated["release"],
        "source_commit": validated["source_commit"],
        "beta_ready": not beta_blockers,
        "launch_ready": not launch_blockers,
        "beta_blockers": beta_blockers,
        "launch_blockers": launch_blockers,
        "policy": {
            "minimum_external_beta_reports": MIN_EXTERNAL_BETA_REPORTS,
            "required_package_paths": dict(REQUIRED_PACKAGE_PATHS),
            "required_vm_ids": list(REQUIRED_VM_IDS),
            "required_destructive_test_ids": list(REQUIRED_DESTRUCTIVE_IDS),
        },
    }


def _packages(value: Any) -> dict[str, dict[str, Any]]:
    packages = _object(value, "Packages")
    expected = set(REQUIRED_PACKAGE_PATHS)
    _strict(packages, expected, expected, "Packages")
    return {name: _status_record(packages[name], f"Package {name}") for name in sorted(packages)}


def _vm_results(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(REQUIRED_VM_IDS):
        raise ValueError("VM results must contain every required matrix entry exactly once")
    results: list[dict[str, Any]] = []
    for item in value:
        record = _object(item, "VM result")
        allowed = {
            "id",
            "distro",
            "plasma_version",
            "session",
            "scenario",
            "status",
            "evidence_url",
        }
        _strict(record, allowed, allowed, "VM result")
        status = _choice(record["status"], "VM status", _STATUS)
        plasma = _nullable_plasma(record["plasma_version"])
        evidence_url = _nullable_url(record["evidence_url"], "VM evidence URL")
        _require_evidence(status, plasma, evidence_url, "VM result")
        results.append(
            {
                "id": _identifier(record["id"], "VM id"),
                "distro": _identifier(record["distro"], "VM distro"),
                "plasma_version": plasma,
                "session": _choice(record["session"], "VM session", {"wayland", "x11"}),
                "scenario": _text(record["scenario"], "VM scenario", 160),
                "status": status,
                "evidence_url": evidence_url,
            }
        )
    _exact_ids(results, REQUIRED_VM_IDS, "VM")
    return results


def _destructive_tests(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(REQUIRED_DESTRUCTIVE_IDS):
        raise ValueError("Destructive tests must contain every required scenario exactly once")
    results: list[dict[str, Any]] = []
    for item in value:
        record = _object(item, "Destructive test")
        fields = {"id", "status", "evidence_url"}
        _strict(record, fields, fields, "Destructive test")
        normalized = _status_record(record, "Destructive test", include_id=True)
        normalized["id"] = _identifier(record["id"], "Destructive test id")
        results.append(normalized)
    _exact_ids(results, REQUIRED_DESTRUCTIVE_IDS, "Destructive test")
    return results


def _beta_reports(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError("Beta reports must be an array with at most 100 entries")
    results: list[dict[str, Any]] = []
    urls: set[str] = set()
    for item in value:
        record = _object(item, "Beta report")
        allowed = {"report_url", "distro", "plasma_version", "session", "outcome"}
        _strict(record, allowed, allowed, "Beta report")
        url = _url(record["report_url"], "Beta report URL")
        if url in urls:
            raise ValueError("Beta report URLs must be unique")
        urls.add(url)
        results.append(
            {
                "report_url": url,
                "distro": _identifier(record["distro"], "Beta distro"),
                "plasma_version": _plasma(record["plasma_version"]),
                "session": _choice(
                    record["session"], "Beta session", {"wayland", "x11"}
                ),
                "outcome": _choice(
                    record["outcome"], "Beta outcome", {"passed", "resolved", "failed"}
                ),
            }
        )
    return results


def _recording(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    record = _object(value, "Recording")
    allowed = {
        "url",
        "sha256",
        "duration_seconds",
        "plasma_version",
        "session",
        "shows_apply",
        "shows_verify",
        "shows_revert",
        "multiple_applications",
        "generated_visuals",
    }
    _strict(record, allowed, allowed, "Recording")
    duration = record["duration_seconds"]
    if isinstance(duration, bool) or not isinstance(duration, int) or not 20 <= duration <= 40:
        raise ValueError("Recording duration must be 20 through 40 seconds")
    result: dict[str, Any] = {
        "url": _url(record["url"], "Recording URL"),
        "sha256": _sha256(record["sha256"], "Recording SHA-256"),
        "duration_seconds": duration,
        "plasma_version": _plasma(record["plasma_version"]),
        "session": _choice(record["session"], "Recording session", {"wayland", "x11"}),
    }
    for field in (
        "shows_apply",
        "shows_verify",
        "shows_revert",
        "multiple_applications",
        "generated_visuals",
    ):
        result[field] = _boolean(record[field], f"Recording {field}")
    return result


def _community_rice(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    record = _object(value, "Community rice")
    allowed = {"source_url", "commit", "rice_sha256", "apply_report_url", "status"}
    _strict(record, allowed, allowed, "Community rice")
    return {
        "source_url": _url(record["source_url"], "Community rice source URL"),
        "commit": _commit(record["commit"], "Community rice commit"),
        "rice_sha256": _sha256(record["rice_sha256"], "Community rice SHA-256"),
        "apply_report_url": _url(
            record["apply_report_url"], "Community rice apply report URL"
        ),
        "status": _choice(record["status"], "Community rice status", _STATUS),
    }


def _status_record(
    value: Any, context: str, *, include_id: bool = False
) -> dict[str, Any]:
    record = _object(value, context)
    allowed = {"status", "evidence_url"} | ({"id"} if include_id else set())
    _strict(record, allowed, allowed, context)
    status = _choice(record["status"], f"{context} status", _STATUS)
    evidence_url = _nullable_url(record["evidence_url"], f"{context} evidence URL")
    _require_evidence(status, None, evidence_url, context)
    return {"status": status, "evidence_url": evidence_url}


def _require_evidence(
    status: str, plasma: str | None, evidence_url: str | None, context: str
) -> None:
    if status != "pending" and evidence_url is None:
        raise ValueError(f"{context} requires an evidence URL when it is not pending")
    if status != "pending" and plasma is None and context == "VM result":
        raise ValueError("VM result requires a Plasma version when it is not pending")


def _exact_ids(
    items: list[dict[str, Any]], expected: tuple[str, ...], context: str
) -> None:
    actual = [str(item["id"]) for item in items]
    if len(set(actual)) != len(actual) or set(actual) != set(expected):
        raise ValueError(f"{context} ids must match the required matrix exactly")


def _block(items: list[dict[str, str]], gate: str, detail: str) -> None:
    finding = {"gate": gate, "detail": detail}
    if finding not in items:
        items.append(finding)


def _nullable_plasma(value: Any) -> str | None:
    return None if value is None else _plasma(value)


def _plasma(value: Any) -> str:
    result = _text(value, "Plasma version", 16)
    if _PLASMA.fullmatch(result) is None:
        raise ValueError("Plasma version must be a Plasma 6 version")
    return result


def _nullable_url(value: Any, context: str) -> str | None:
    return None if value is None else _url(value, context)


def _url(value: Any, context: str) -> str:
    result = _text(value, context, 2048)
    parsed = urlsplit(result)
    hostname = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or hostname == "localhost"
        or hostname.endswith(".local")
        or "." not in hostname
    ):
        raise ValueError(f"{context} must be a plain HTTPS URL")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError(f"{context} must not use a private or local address")
    return result


def _identifier(value: Any, context: str) -> str:
    result = _text(value, context, 64)
    if _IDENTIFIER.fullmatch(result) is None:
        raise ValueError(f"{context} contains unsupported characters")
    return result


def _commit(value: Any, context: str) -> str:
    result = _text(value, context, 40)
    if _COMMIT.fullmatch(result) is None:
        raise ValueError(f"{context} must be a full lowercase SHA-1 commit")
    return result


def _sha256(value: Any, context: str) -> str:
    result = _text(value, context, 64)
    if _HASH.fullmatch(result) is None:
        raise ValueError(f"{context} must be a lowercase SHA-256")
    return result


def _boolean(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context} must be a boolean")
    return value


def _choice(value: Any, context: str, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{context} is unsupported")
    return value


def _text(value: Any, context: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{context} contains unsupported text")
    return value


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be an object")
    return value


def _strict(
    value: dict[str, Any], required: set[str], allowed: set[str], context: str
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ValueError(f"{context} is missing: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{context} contains unsupported fields: {', '.join(unknown)}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result
