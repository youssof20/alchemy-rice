from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from alchemy.services.creator_capture import CreatorCaptureService, capture_component_names
from alchemy.services.debug_info import build_debug_info
from alchemy.services.dependency_service import DependencyService
from alchemy.services.environment_probe import EnvironmentProbe
from alchemy.services.gallery_service import GalleryService
from alchemy.services.rice_service import RiceService
from alchemy.services.transaction_service import TransactionFailedError, TransactionService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alchemy",
        description="Inspect, capture, resolve, and transactionally change reviewed KDE state.",
    )
    subcommands = parser.add_subparsers(dest="command")

    inspect_parser = subcommands.add_parser(
        "inspect", help="Show detected capabilities and settings"
    )
    inspect_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    subcommands.add_parser("debug-info", help="Print a redacted local debug preview")
    subcommands.add_parser("gui", help="Open the capability inspector")
    subcommands.add_parser("gallery", help="Open the offline-first cached gallery browser")
    plan_parser = subcommands.add_parser("plan-color", help="Plan a color-scheme change")
    plan_parser.add_argument("scheme", help="Installed KDE color-scheme name")
    apply_parser = subcommands.add_parser("apply-color", help="Apply one planned color scheme")
    apply_parser.add_argument("scheme", help="Installed KDE color-scheme name")
    apply_parser.add_argument(
        "--yes", action="store_true", help="Confirm the exact operation shown by plan-color"
    )
    subcommands.add_parser("list-settings", help="List transactional setting drivers")
    setting_plan = subcommands.add_parser(
        "plan-setting", help="Plan one reviewed Plasma setting change"
    )
    setting_plan.add_argument("setting", help="Setting name from list-settings")
    setting_plan.add_argument("value", help="Desired setting value")
    setting_apply = subcommands.add_parser(
        "apply-setting", help="Apply one reviewed Plasma setting change"
    )
    setting_apply.add_argument("setting", help="Setting name from list-settings")
    setting_apply.add_argument("value", help="Desired setting value")
    setting_apply.add_argument(
        "--yes", action="store_true", help="Confirm the exact operation shown by plan-setting"
    )
    subcommands.add_parser("inspect-panels", help="Inspect the current semantic panel layout")
    panel_plan = subcommands.add_parser(
        "plan-panels", help="Preview panel layout and logical screen mapping"
    )
    panel_plan.add_argument("layout", help="Declarative panel-layout JSON file")
    panel_apply = subcommands.add_parser(
        "apply-panels", help="Apply a reviewed declarative panel layout"
    )
    panel_apply.add_argument("layout", help="Declarative panel-layout JSON file")
    panel_apply.add_argument(
        "--yes", action="store_true", help="Confirm the exact output shown by plan-panels"
    )
    panel_apply.add_argument(
        "--plan-token", required=True, help="Confirmation token emitted by plan-panels"
    )
    revert_parser = subcommands.add_parser("revert", help="Revert a committed transaction")
    revert_parser.add_argument("--last", action="store_true", help="Revert the latest commit")
    recovery = subcommands.add_parser("recovery", help="Inspect or restore incomplete journals")
    recovery.add_argument("--list", action="store_true", help="List incomplete transactions")
    recovery.add_argument("--rollback", metavar="TRANSACTION_ID", help="Restore one transaction")
    rice_inspect = subcommands.add_parser(
        "rice-inspect", help="Validate a canonical rice and check this environment"
    )
    rice_inspect.add_argument("file", help="Canonical .rice file")
    rice_inspect.add_argument("--sha256", help="Expected canonical SHA-256")
    rice_inspect.add_argument("--override", help="Sparse override JSON bound to this rice")
    rice_export = subcommands.add_parser(
        "rice-export", help="Validate JSON and export a canonical .rice file"
    )
    rice_export.add_argument("source", help="Rice v2 JSON source")
    rice_export.add_argument("destination", help="New .rice output path")
    rice_import = subcommands.add_parser(
        "rice-import", help="Validate and store a canonical rice without applying it"
    )
    rice_import.add_argument("file", help="Canonical .rice file")
    rice_import.add_argument("--sha256", help="Expected canonical SHA-256")
    rice_import.add_argument("--override", help="Sparse override JSON bound to this rice")
    rice_resolve = subcommands.add_parser(
        "rice-resolve", help="Resolve a base rice and bound sparse override"
    )
    rice_resolve.add_argument("base", help="Canonical base .rice file")
    rice_resolve.add_argument("override", help="Sparse override JSON")
    capture_draft = subcommands.add_parser(
        "capture-draft", help="Capture a sanitized, reviewable rice draft"
    )
    capture_draft.add_argument("metadata", help="Creator and immutable source metadata JSON")
    _add_capture_exclusions(capture_draft)
    capture_export = subcommands.add_parser(
        "capture-export", help="Capture and export a sanitized canonical rice"
    )
    capture_export.add_argument("metadata", help="Creator and immutable source metadata JSON")
    capture_export.add_argument("destination", help="New .rice output path")
    _add_capture_exclusions(capture_export)
    dependency_resolve = subcommands.add_parser(
        "dependency-resolve", help="Resolve rice dependencies without installing them"
    )
    dependency_resolve.add_argument("file", help="Canonical .rice file")
    dependency_resolve.add_argument("--sha256", help="Expected canonical SHA-256")
    dependency_resolve.add_argument(
        "--allow-known-incompatible",
        action="store_true",
        help="Plan despite confirmed breakage after reviewing the warning",
    )
    dependency_install = subcommands.add_parser(
        "dependency-install", help="Install one separately reviewed dependency plan"
    )
    dependency_install.add_argument("file", help="Canonical .rice file")
    dependency_install.add_argument("dependency", help="Exact dependency id")
    dependency_install.add_argument("--sha256", help="Expected canonical SHA-256")
    dependency_install.add_argument(
        "--plan-token", required=True, help="Token from the latest dependency-resolve"
    )
    dependency_install.add_argument(
        "--yes", action="store_true", help="Approve this exact separate package operation"
    )
    dependency_install.add_argument(
        "--allow-known-incompatible",
        action="store_true",
        help="Install despite confirmed breakage after reviewing the warning",
    )
    gallery_validate = subcommands.add_parser(
        "gallery-validate", help="Validate gallery metadata without executing contributor code"
    )
    gallery_validate.add_argument("entries", help="Directory containing gallery entry JSON")
    gallery_validate.add_argument(
        "--verify-remote",
        action="store_true",
        help="Verify pinned ownership, rice, and screenshot bytes over HTTPS",
    )
    gallery_build = subcommands.add_parser(
        "gallery-build", help="Build a deterministic static gallery snapshot"
    )
    gallery_build.add_argument("entries", help="Directory containing gallery entry JSON")
    gallery_build.add_argument("destination", help="Static gallery.json destination")
    gallery_build.add_argument("--metrics", help="Trusted aggregate metrics JSON")
    gallery_build.add_argument(
        "--check", action="store_true", help="Fail unless destination is already current"
    )
    subcommands.add_parser(
        "gallery-refresh", help="Explicitly fetch and cache the public static gallery snapshot"
    )
    gallery_cache = subcommands.add_parser(
        "gallery-cache", help="Validate and cache a local gallery snapshot"
    )
    gallery_cache.add_argument("snapshot", help="Local gallery.json file")
    gallery_cache.add_argument("--sha256", help="Expected snapshot SHA-256")
    gallery_list = subcommands.add_parser(
        "gallery-list", help="Browse entries from the local gallery cache"
    )
    gallery_list.add_argument("--query", help="Search names, summaries, authors, and tags")
    gallery_list.add_argument("--tag", help="Require one gallery tag")
    gallery_list.add_argument(
        "--sort",
        default="updated",
        choices=("new", "updated", "downloads", "confirmed", "compatible"),
        help="Deterministic gallery ordering",
    )
    gallery_show = subcommands.add_parser(
        "gallery-show", help="Show one entry from the local gallery cache"
    )
    gallery_show.add_argument("entry_id", help="Exact gallery entry id")
    gallery_report = subcommands.add_parser(
        "gallery-report", help="Preview a local report and generate a GitHub form URL"
    )
    gallery_report.add_argument("entry_id", help="Exact gallery entry id")
    gallery_report.add_argument("--result", required=True, choices=("success", "failure"))
    gallery_report.add_argument("--failed-component")
    gallery_report.add_argument("--error-class")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    command = arguments.command or "inspect"
    if command == "gui":
        from alchemy.ui.main_window import run_gui

        return run_gui()
    if command == "gallery":
        from alchemy.ui.gallery_window import run_gallery

        return run_gallery()

    if command.startswith("gallery-"):
        try:
            return _run_gallery_command(command, arguments)
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"Alchemy: {exc}", file=sys.stderr)
            return 1

    if command in {"capture-draft", "capture-export"}:
        try:
            return asyncio.run(_run_capture_command(command, arguments))
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"Alchemy: {exc}", file=sys.stderr)
            return 1

    if command in {"dependency-resolve", "dependency-install"}:
        try:
            return asyncio.run(_run_dependency_command(command, arguments))
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"Alchemy: {exc}", file=sys.stderr)
            return 1

    if command in {"rice-inspect", "rice-export", "rice-import", "rice-resolve"}:
        try:
            return _run_rice_command(command, arguments)
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"Alchemy: {exc}", file=sys.stderr)
            return 1

    if command in {
        "plan-color",
        "apply-color",
        "list-settings",
        "plan-setting",
        "apply-setting",
        "inspect-panels",
        "plan-panels",
        "apply-panels",
        "revert",
        "recovery",
    }:
        try:
            return _run_transaction_command(command, arguments)
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"Alchemy: {exc}", file=sys.stderr)
            return 1

    report = EnvironmentProbe().inspect()
    if command == "debug-info":
        print(build_debug_info(report))
        return 0
    if getattr(arguments, "json", False):
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        _print_report(report.to_dict())
    return 0


def _run_rice_command(command: str, arguments: argparse.Namespace) -> int:
    service = RiceService()
    if command == "rice-inspect":
        result = service.inspect(
            arguments.file,
            expected_sha256=arguments.sha256,
            override_path=arguments.override,
        )
    elif command == "rice-export":
        result = service.export(arguments.source, arguments.destination)
    elif command == "rice-import":
        result = service.import_manifest(
            arguments.file,
            expected_sha256=arguments.sha256,
            override_path=arguments.override,
        )
    else:
        result = service.resolve(arguments.base, arguments.override)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run_gallery_command(command: str, arguments: argparse.Namespace) -> int:
    service = GalleryService()
    if command == "gallery-validate":
        result = service.validate_directory(
            arguments.entries, verify_remote=arguments.verify_remote
        )
    elif command == "gallery-build":
        result = service.build(
            arguments.entries,
            arguments.destination,
            metrics_path=arguments.metrics,
            check=arguments.check,
        )
    elif command == "gallery-refresh":
        result = service.refresh()
    elif command == "gallery-cache":
        result = service.cache_local(
            arguments.snapshot, expected_sha256=arguments.sha256
        )
    elif command == "gallery-list":
        result = service.browse(
            query=arguments.query, tag=arguments.tag, sort_by=arguments.sort
        )
    elif command == "gallery-show":
        result = service.show(arguments.entry_id)
    else:
        result = service.report(
            arguments.entry_id,
            result=arguments.result,
            failed_component=arguments.failed_component,
            error_class=arguments.error_class,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


async def _run_capture_command(command: str, arguments: argparse.Namespace) -> int:
    service = CreatorCaptureService()
    excluded = frozenset(arguments.exclude)
    if command == "capture-draft":
        result = (await service.draft(arguments.metadata, excluded=excluded)).to_dict()
    else:
        result = await service.export(
            arguments.metadata, arguments.destination, excluded=excluded
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _add_capture_exclusions(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        choices=capture_component_names(),
        help="Omit one component after reviewing the draft; repeat as needed",
    )


async def _run_dependency_command(command: str, arguments: argparse.Namespace) -> int:
    service = DependencyService()
    if command == "dependency-resolve":
        result = (
            await service.resolve(
                arguments.file,
                expected_sha256=arguments.sha256,
                allow_known_incompatible=arguments.allow_known_incompatible,
            )
        ).to_dict()
    else:
        if not arguments.yes:
            raise RuntimeError(
                "Dependency installation requires --yes after reviewing dependency-resolve"
            )
        result = await service.install(
            arguments.file,
            arguments.dependency,
            arguments.plan_token,
            expected_sha256=arguments.sha256,
            allow_known_incompatible=arguments.allow_known_incompatible,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run_transaction_command(command: str, arguments: argparse.Namespace) -> int:
    service = TransactionService()
    if command == "plan-color":
        operations = asyncio.run(service.plan_color_scheme(arguments.scheme))
        print(json.dumps([operation.to_dict() for operation in operations], indent=2))
        return 0
    if command == "apply-color":
        if not arguments.yes:
            raise TransactionFailedError("Apply requires --yes after reviewing plan-color output")
        record = asyncio.run(service.apply_color_scheme(arguments.scheme))
        print(json.dumps(_public_transaction(record), indent=2, sort_keys=True))
        return 0
    if command == "list-settings":
        print("\n".join(service.setting_names()))
        return 0
    if command == "plan-setting":
        operations = asyncio.run(service.plan_component(arguments.setting, arguments.value))
        print(json.dumps([operation.to_dict() for operation in operations], indent=2))
        return 0
    if command == "apply-setting":
        if not arguments.yes:
            raise TransactionFailedError("Apply requires --yes after reviewing plan-setting output")
        record = asyncio.run(service.apply_component(arguments.setting, arguments.value))
        print(json.dumps(_public_transaction(record), indent=2, sort_keys=True))
        return 0
    if command == "inspect-panels":
        print(json.dumps(asyncio.run(service.inspect_panels()), indent=2, sort_keys=True))
        return 0
    if command == "plan-panels":
        plan = asyncio.run(service.plan_panels(arguments.layout))
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if command == "apply-panels":
        if not arguments.yes:
            raise TransactionFailedError("Apply requires --yes after reviewing plan-panels output")
        record = asyncio.run(service.apply_panels(arguments.layout, arguments.plan_token))
        print(json.dumps(_public_transaction(record), indent=2, sort_keys=True))
        return 0
    if command == "revert":
        if not arguments.last:
            raise TransactionFailedError("Specify --last")
        print(
            json.dumps(
                _public_transaction(asyncio.run(service.revert_last())),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if arguments.rollback:
        recovered = asyncio.run(service.recover(arguments.rollback))
        print(json.dumps(_public_transaction(recovered), indent=2, sort_keys=True))
        return 0
    incomplete = service.journals.incomplete()
    print(
        json.dumps(
            [_public_transaction(record) for record in incomplete], indent=2, sort_keys=True
        )
    )
    return 0


def _public_transaction(record: dict[str, object] | None) -> dict[str, object]:
    if record is None:
        return {"state": "no_change"}
    public = {
        key: record.get(key)
        for key in (
            "transaction_id",
            "state",
            "started_at",
            "updated_at",
            "snapshot_id",
            "rollback_status",
            "error",
        )
    }
    operations = record.get("operations")
    if isinstance(operations, list) and operations and isinstance(operations[0], dict):
        public["driver"] = operations[0].get("driver")
        public["description"] = operations[0].get("description")
    return public


def _print_report(report: dict[str, object]) -> None:
    capabilities = report["capabilities"]
    assert isinstance(capabilities, dict)
    print("Alchemy read-only inspector")
    print("Apply: reviewed settings and panel layouts when capability checks pass")
    print()
    for key, value in capabilities.items():
        print(f"{key.replace('_', ' ').title():22} {_display(value)}")
    print("\nSettings")
    settings = report["settings"]
    assert isinstance(settings, list)
    for setting in settings:
        assert isinstance(setting, dict)
        value = setting["value"] if setting["available"] else f"unavailable: {setting['detail']}"
        print(f"{setting['label']:22} {_display(value)}")
    warnings = report["warnings"]
    assert isinstance(warnings, list)
    if warnings:
        print("\nWarnings")
        for warning in warnings:
            print(f"- {warning}")


def _display(value: object) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


if __name__ == "__main__":
    sys.exit(main())
