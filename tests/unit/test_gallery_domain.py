from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from alchemy.domain.gallery import (
    ENTRY_SCHEMA_URI,
    SNAPSHOT_SCHEMA_URI,
    build_gallery_snapshot,
    ownership_url,
    parse_gallery_entry_bytes,
    parse_gallery_snapshot_bytes,
    resource_belongs_to_source,
)
from alchemy.domain.rice import canonical_json_bytes
from tests.unit.test_rice_domain import manifest_data


def gallery_fixture() -> tuple[dict[str, object], dict[str, object], bytes]:
    image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (100).to_bytes(4, "big") + (80).to_bytes(4, "big")
    image_hash = hashlib.sha256(image).hexdigest()
    rice = manifest_data()
    source = {
        "repo": "https://github.com/creator/rice",
        "release": "v1.2.0",
        "commit": "a" * 40,
    }
    screenshot = {
        "url": f"https://raw.githubusercontent.com/creator/rice/{'a' * 40}/desktop.png",
        "sha256": image_hash,
        "alt": "A dark Plasma desktop with two application windows",
    }
    rice["source"] = source
    rice["gallery"] = {"screenshots": [screenshot], "reddit_url": None, "tip_url": None}
    rice_bytes = canonical_json_bytes(rice)
    entry: dict[str, object] = {
        "$schema": ENTRY_SCHEMA_URI,
        "entry_version": 1,
        "id": rice["id"],
        "name": rice["name"],
        "version": rice["version"],
        "summary": "A restrained dark workbench for Plasma.",
        "author": rice["author"],
        "source": source,
        "rice": {
            "url": "https://github.com/creator/rice/releases/download/v1.2.0/night.rice",
            "sha256": hashlib.sha256(rice_bytes).hexdigest(),
        },
        "compatibility": rice["compatibility"],
        "components": sorted(rice["components"]),
        "dependencies": [],
        "licenses": rice["licenses"],
        "screenshots": [{**screenshot, "license": "CC-BY-4.0"}],
        "tags": ["dark", "productivity"],
        "published_at": "2026-01-02",
        "updated_at": "2026-02-03",
    }
    return entry, rice, image


class GalleryDomainTests(unittest.TestCase):
    def test_entry_is_strict_pinned_and_creator_owned(self) -> None:
        entry, _, _ = gallery_fixture()
        parsed = parse_gallery_entry_bytes(json.dumps(entry).encode())

        self.assertEqual(parsed.data["id"], "github:creator/rice:night")

        hostile = dict(entry)
        hostile["summary"] = "<img src=x onerror=alert(1)>"
        with self.assertRaisesRegex(ValueError, "plain text"):
            parse_gallery_entry_bytes(json.dumps(hostile).encode())

        foreign = json.loads(json.dumps(entry))
        foreign["rice"]["url"] = "https://github.com/other/rice/releases/download/v1.2.0/night.rice"
        with self.assertRaisesRegex(ValueError, "owned"):
            parse_gallery_entry_bytes(json.dumps(foreign).encode())

        mutable = json.loads(json.dumps(entry))
        mutable["source"]["release"] = "latest"
        with self.assertRaisesRegex(ValueError, "immutable"):
            parse_gallery_entry_bytes(json.dumps(mutable).encode())

    def test_snapshot_is_deterministic_and_derived_fields_are_verified(self) -> None:
        entry, _, _ = gallery_fixture()
        parsed = parse_gallery_entry_bytes(json.dumps(entry).encode())
        first = build_gallery_snapshot([parsed])
        second = build_gallery_snapshot([parsed])

        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.entries[0]["badges"][0]["id"], "schema_valid")
        self.assertEqual(first.entries[0]["community"]["confirmed_reports"], 0)
        self.assertFalse(first.entries[0]["community"]["official_repo_dependencies_only"])

        tampered = json.loads(first.canonical_bytes)
        tampered["entries"][0]["badges"][0]["label"] = "Trust me"
        with self.assertRaisesRegex(ValueError, "badges"):
            parse_gallery_snapshot_bytes(canonical_json_bytes(tampered))

        duplicate = build_gallery_snapshot([parsed])
        data = json.loads(duplicate.canonical_bytes)
        data["entries"].append(data["entries"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_gallery_snapshot_bytes(canonical_json_bytes(data))

    def test_duplicate_json_keys_and_oversized_documents_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse_gallery_entry_bytes(b'{"entry_version":1,"entry_version":1}')
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            parse_gallery_entry_bytes(b" " * (256 * 1024 + 1))

    def test_codeberg_release_raw_paths_and_ownership_are_commit_pinned(self) -> None:
        entry_data, _, _ = gallery_fixture()
        entry_data["source"] = {
            "repo": "https://codeberg.org/creator/rice",
            "release": "v1.2.0",
            "commit": "b" * 40,
        }
        entry_data["rice"] = {
            "url": "https://codeberg.org/creator/rice/releases/download/v1.2.0/night.rice",
            "sha256": "c" * 64,
        }
        entry_data["screenshots"] = [
            {
                "url": f"https://codeberg.org/creator/rice/raw/commit/{'b' * 40}/desktop.png",
                "sha256": "d" * 64,
                "alt": "Two application windows on a Plasma desktop",
                "license": "CC-BY-4.0",
            }
        ]
        parsed = parse_gallery_entry_bytes(canonical_json_bytes(entry_data))

        self.assertIn("/raw/commit/", ownership_url(parsed))
        self.assertTrue(
            resource_belongs_to_source(
                parsed.data["screenshots"][0]["url"],
                parsed.data["source"],
                allow_raw=True,
            )
        )

    def test_published_gallery_schemas_have_runtime_ids(self) -> None:
        root = Path(__file__).parents[2]
        entry_schema = json.loads(
            (root / "schemas" / "gallery-entry-v1.schema.json").read_text(encoding="utf-8")
        )
        snapshot_schema = json.loads(
            (root / "schemas" / "gallery-v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(entry_schema["$id"], ENTRY_SCHEMA_URI)
        self.assertEqual(snapshot_schema["$id"], SNAPSHOT_SCHEMA_URI)


if __name__ == "__main__":
    unittest.main()
