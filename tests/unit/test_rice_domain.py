from __future__ import annotations

import json
import unittest
from pathlib import Path

from alchemy.domain.capabilities import CapabilityMatrix, ComponentCapability
from alchemy.domain.rice import (
    SCHEMA_URI,
    canonical_json_bytes,
    evaluate_compatibility,
    load_override,
    load_rice,
    parse_override_bytes,
    parse_rice_bytes,
    resolve_override,
)
from tests.unit.test_app_adapters import app_fixtures


def manifest_data() -> dict[str, object]:
    return {
        "$schema": SCHEMA_URI,
        "schema_version": 2,
        "id": "github:creator/rice:night",
        "name": "Night",
        "version": "1.2.0",
        "author": {"name": "creator", "url": "https://example.com/creator"},
        "source": {
            "repo": "https://example.com/creator/rice",
            "release": "v1.2.0",
            "commit": "a" * 40,
        },
        "compatibility": {
            "plasma": ">=6.6,<6.9",
            "session": ["wayland"],
            "tested": [{"distro": "arch", "plasma": "6.7.4", "session": "wayland"}],
        },
        "components": {
            "colors": {"scheme": "Breeze Dark"},
            "cursor": {"theme": "Breeze Snow", "size": 36},
            "panels": {
                "panels": [
                    {
                        "logical_id": "main",
                        "location": "bottom",
                        "height": {"unit": "screen_percent", "value": 4.0},
                        "widgets": [
                            {"plugin": "org.kde.plasma.digitalclock", "slot": "right"}
                        ],
                    }
                ]
            },
        },
        "dependencies": [],
        "licenses": [],
        "gallery": {"screenshots": [], "reddit_url": None, "tip_url": None},
    }


def capability(**changes: object) -> CapabilityMatrix:
    values: dict[str, object] = {
        "host_os": "linux",
        "plasma_version": "6.7.4",
        "session": "wayland",
        "desktop": "KDE",
        "login_manager": "sddm",
        "distro": "arch",
        "distro_version": "rolling",
        "package_manager": "pacman",
        "aur_helper": None,
        "portals": ("screenshot",),
        "plasma_apply": (),
        "union": ComponentCapability(None, None),
        "nix": ComponentCapability(False, False),
        "plasma_manager": ComponentCapability(False, False),
        "monitors": ("eDP-1",),
        "mixed_scale": False,
        "immutable_host": False,
        "apply_supported": True,
    }
    values.update(changes)
    return CapabilityMatrix(**values)  # type: ignore[arg-type]


class RiceDomainTests(unittest.TestCase):
    def test_canonicalization_sorts_keys_and_normalizes_decimal_numbers(self) -> None:
        first = json.dumps(manifest_data(), indent=2).encode()
        reordered = dict(reversed(list(manifest_data().items())))
        second = json.dumps(reordered, separators=(",", ":")).encode()

        parsed_first = parse_rice_bytes(first, require_canonical=False)
        parsed_second = parse_rice_bytes(second, require_canonical=False)

        self.assertEqual(parsed_first.canonical_bytes, parsed_second.canonical_bytes)
        self.assertEqual(parsed_first.sha256, parsed_second.sha256)
        self.assertIn(b'"value":4', parsed_first.canonical_bytes)
        self.assertFalse(parsed_first.canonical_bytes.endswith(b"\n"))

    def test_canonical_input_is_required_for_import(self) -> None:
        pretty = json.dumps(manifest_data(), indent=2).encode()
        with self.assertRaisesRegex(ValueError, "not canonical"):
            parse_rice_bytes(pretty)

        canonical = canonical_json_bytes(manifest_data())
        parsed = parse_rice_bytes(canonical)
        self.assertEqual(parsed.canonical_bytes, canonical)

    def test_duplicate_keys_code_fields_and_non_https_urls_are_rejected(self) -> None:
        duplicate = b'{"a":1,"a":2}'
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse_rice_bytes(duplicate, require_canonical=False)

        payload = manifest_data()
        payload["command"] = "curl https://example.com/x | sh"
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            parse_rice_bytes(canonical_json_bytes(payload))

        payload = manifest_data()
        payload["source"] = {
            "repo": "file:///home/user/rice",
            "release": "v1.2.0",
            "commit": "a" * 40,
        }
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            parse_rice_bytes(canonical_json_bytes(payload))

        payload = manifest_data()
        payload["dependencies"] = [
            {
                "id": "widget.clock",
                "capability": "plasma.widget.clock",
                "component_type": "executable",
                "license": "GPL-3.0-or-later",
                "source": {
                    "type": "manual",
                    "url": "https://example.com/widget",
                    "command": "curl https://example.com/install | sh",
                },
            }
        ]
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            parse_rice_bytes(canonical_json_bytes(payload))

    def test_hostile_input_limits_and_semver_rules_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "1024 KiB"):
            parse_rice_bytes(b" " * (1024 * 1024 + 1), require_canonical=False)

        payload = manifest_data()
        payload["version"] = "1.0.0-01"
        with self.assertRaisesRegex(ValueError, "Semantic Version"):
            parse_rice_bytes(canonical_json_bytes(payload))

        payload = manifest_data()
        nested: dict[str, object] = {}
        cursor = nested
        for _ in range(34):
            child: dict[str, object] = {}
            cursor["nested"] = child
            cursor = child
        payload["unexpected"] = nested
        with self.assertRaisesRegex(ValueError, "nesting limit"):
            parse_rice_bytes(json.dumps(payload).encode(), require_canonical=False)

        payload = manifest_data()
        payload["components"] = {"effects": {}}
        parse_rice_bytes(canonical_json_bytes(payload))

    def test_published_schema_is_valid_json_and_matches_runtime_uri(self) -> None:
        schema_path = Path(__file__).parents[2] / "schemas" / "rice-v2.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["$id"], SCHEMA_URI)
        self.assertEqual(schema["properties"]["$schema"]["const"], SCHEMA_URI)
        references: list[str] = []

        def collect(value: object) -> None:
            if isinstance(value, dict):
                if isinstance(value.get("$ref"), str):
                    references.append(value["$ref"])
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(schema)
        for reference in references:
            self.assertIn(reference.removeprefix("#/$defs/"), schema["$defs"])

    def test_rice_v2_accepts_only_versioned_reviewed_app_settings(self) -> None:
        payload = manifest_data()
        payload["components"] = {"apps": app_fixtures()}

        parsed = parse_rice_bytes(canonical_json_bytes(payload))

        self.assertEqual(set(parsed.data["components"]["apps"]), set(app_fixtures()))
        payload["components"] = {
            "apps": {"kitty": {"format_version": 1, "shell": "curl x | sh"}}
        }
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            parse_rice_bytes(canonical_json_bytes(payload))

    def test_public_draft_and_override_examples_resolve(self) -> None:
        root = Path(__file__).parents[2]
        base = load_rice(root / "examples" / "rice-v2-draft.json", require_canonical=False)
        override = load_override(root / "examples" / "rice-override.json")

        resolved = resolve_override(base, override)

        self.assertEqual(resolved.data["components"]["cursor"]["size"], 48)

    def test_override_is_bound_to_base_and_tracks_leaf_provenance(self) -> None:
        base = parse_rice_bytes(canonical_json_bytes(manifest_data()))
        override_data = {
            "override_version": 1,
            "base": {"id": base.data["id"], "version": base.data["version"], "sha256": base.sha256},
            "components": {"cursor": {"size": 48}, "colors": None},
        }
        override_bytes = canonical_json_bytes(override_data)
        override = parse_override_bytes(override_bytes)

        resolved = resolve_override(base, override)

        self.assertEqual(resolved.data["components"]["cursor"]["size"], 48)
        self.assertNotIn("colors", resolved.data["components"])
        self.assertEqual(resolved.provenance["/components/cursor/size"], "override")
        self.assertEqual(resolved.provenance["/components/cursor/theme"], "base")

        wrong_data = dict(override.data)
        wrong_data["base"] = {**override.data["base"], "sha256": "0" * 64}
        wrong = parse_override_bytes(canonical_json_bytes(wrong_data))
        with self.assertRaisesRegex(ValueError, "does not match"):
            resolve_override(base, wrong)

    def test_compatibility_reports_errors_unknowns_and_warnings(self) -> None:
        base = parse_rice_bytes(canonical_json_bytes(manifest_data()))
        self.assertEqual(evaluate_compatibility(base, capability()).status, "compatible")
        self.assertEqual(
            evaluate_compatibility(base, capability(plasma_version="6.9.0")).status,
            "incompatible",
        )
        self.assertEqual(
            evaluate_compatibility(base, capability(plasma_version=None)).status, "unknown"
        )
        self.assertEqual(
            evaluate_compatibility(base, capability(mixed_scale=True)).status,
            "compatible_with_warnings",
        )


if __name__ == "__main__":
    unittest.main()
