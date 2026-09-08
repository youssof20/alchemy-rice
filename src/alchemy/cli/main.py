from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from alchemy.services.debug_info import build_debug_info
from alchemy.services.environment_probe import EnvironmentProbe


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    command = arguments.command or "inspect"
    if command == "gui":
        from alchemy.ui.main_window import run_gui

        return run_gui()

    report = EnvironmentProbe().inspect()
    if command == "debug-info":
        print(build_debug_info(report))
        return 0
    if getattr(arguments, "json", False):
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        _print_report(report.to_dict())
    return 0


def _print_report(report: dict[str, object]) -> None:
    capabilities = report["capabilities"]
    assert isinstance(capabilities, dict)
    print("Alchemy read-only inspector")
    print("Apply: disabled (Phase 0)")
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
