from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from alchemy.services.debug_info import build_debug_info
from alchemy.services.environment_probe import EnvironmentProbe
from alchemy.services.transaction_service import TransactionFailedError, TransactionService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alchemy", description="Inspect KDE Plasma state without changing it."
    )
    subcommands = parser.add_subparsers(dest="command")

    inspect_parser = subcommands.add_parser(
        "inspect", help="Show detected capabilities and settings"
    )
    inspect_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    subcommands.add_parser("debug-info", help="Print a redacted local debug preview")
    subcommands.add_parser("gui", help="Open the capability inspector")
    plan_parser = subcommands.add_parser("plan-color", help="Plan a color-scheme change")
    plan_parser.add_argument("scheme", help="Installed KDE color-scheme name")
    apply_parser = subcommands.add_parser("apply-color", help="Apply one planned color scheme")
    apply_parser.add_argument("scheme", help="Installed KDE color-scheme name")
    apply_parser.add_argument(
        "--yes", action="store_true", help="Confirm the exact operation shown by plan-color"
    )
    revert_parser = subcommands.add_parser("revert", help="Revert a committed transaction")
    revert_parser.add_argument("--last", action="store_true", help="Revert the latest commit")
    recovery = subcommands.add_parser("recovery", help="Inspect or restore incomplete journals")
    recovery.add_argument("--list", action="store_true", help="List incomplete transactions")
    recovery.add_argument("--rollback", metavar="TRANSACTION_ID", help="Restore one transaction")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    command = arguments.command or "inspect"
    if command == "gui":
        from alchemy.ui.main_window import run_gui

        return run_gui()

    if command in {"plan-color", "apply-color", "revert", "recovery"}:
        try:
            return _run_transaction_command(command, arguments)
        except (TransactionFailedError, ValueError, OSError) as exc:
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
        print(json.dumps(record or {"state": "no_change"}, indent=2, sort_keys=True))
        return 0
    if command == "revert":
        if not arguments.last:
            raise TransactionFailedError("Specify --last")
        print(json.dumps(asyncio.run(service.revert_last()), indent=2, sort_keys=True))
        return 0
    if arguments.rollback:
        recovered = asyncio.run(service.recover(arguments.rollback))
        print(json.dumps(recovered, indent=2, sort_keys=True))
        return 0
    incomplete = service.journals.incomplete()
    print(json.dumps(incomplete, indent=2, sort_keys=True))
    return 0


def _print_report(report: dict[str, object]) -> None:
    capabilities = report["capabilities"]
    assert isinstance(capabilities, dict)
    print("Alchemy read-only inspector")
    print("Apply: color scheme only when capability checks pass")
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
