from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from alchemy.domain.gallery import build_gallery_snapshot, ownership_url, parse_gallery_entry_bytes
from alchemy.domain.rice import canonical_json_bytes
from alchemy.platform.gallery_http import HttpDocument
from alchemy.services.gallery_service import GALLERY_SNAPSHOT_URL, GalleryService
from tests.unit.test_gallery_domain import gallery_fixture
from tests.unit.test_rice_domain import capability


class FakeProbe:
    class Report:
        capabilities = capability()

    def inspect(self) -> Report:
        return self.Report()


class FakeHttpClient:
    def __init__(self, documents: dict[str, HttpDocument]) -> None:
        self.documents = documents
        self.requests: list[tuple[str, int, str | None]] = []

    def fetch(self, url: str, *, maximum: int, etag: str | None = None) -> HttpDocument:
        self.requests.append((url, maximum, etag))
        return self.documents[url]


class GalleryServiceTests(unittest.TestCase):
    def test_remote_validation_checks_ownership_rice_projection_and_image_hash(self) -> None:
        entry_data, rice, image = gallery_fixture()
        entry = parse_gallery_entry_bytes(canonical_json_bytes(entry_data))
        ownership = canonical_json_bytes(
            {
                "entry_id": entry.data["id"],
                "challenge": f"alchemy-gallery:{entry.data['id']}",
            }
        )
        documents = {
            ownership_url(entry): HttpDocument(200, ownership, None, ownership_url(entry)),
            entry.data["rice"]["url"]: HttpDocument(
                200, canonical_json_bytes(rice), None, entry.data["rice"]["url"]
            ),
            entry.data["screenshots"][0]["url"]: HttpDocument(
                200, image, None, entry.data["screenshots"][0]["url"]
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entries = root / "entries"
            entries.mkdir()
            (entries / "night.json").write_bytes(entry.canonical_bytes)
            service = GalleryService(
                data_root=root / "data",
                client=FakeHttpClient(documents),
                probe=FakeProbe(),  # type: ignore[arg-type]
            )

            result = service.validate_directory(str(entries), verify_remote=True)

        self.assertEqual(result["remote_verified"], 1)
        self.assertFalse(result["executed_contributor_code"])

    def test_remote_validation_rejects_changed_release_bytes(self) -> None:
        entry_data, _, _ = gallery_fixture()
        entry = parse_gallery_entry_bytes(canonical_json_bytes(entry_data))
        ownership = canonical_json_bytes(
            {"entry_id": entry.data["id"], "challenge": f"alchemy-gallery:{entry.data['id']}"}
        )
        documents = {
            ownership_url(entry): HttpDocument(200, ownership, None, ownership_url(entry)),
            entry.data["rice"]["url"]: HttpDocument(
                200, b"changed", None, entry.data["rice"]["url"]
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entries = root / "entries"
            entries.mkdir()
            (entries / "night.json").write_bytes(entry.canonical_bytes)
            service = GalleryService(
                data_root=root / "data",
                client=FakeHttpClient(documents),
                probe=FakeProbe(),  # type: ignore[arg-type]
            )
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                service.validate_directory(str(entries), verify_remote=True)

    def test_build_cache_browse_and_explicit_report_are_offline(self) -> None:
        entry_data, _, _ = gallery_fixture()
        entry = parse_gallery_entry_bytes(canonical_json_bytes(entry_data))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entries = root / "entries"
            entries.mkdir()
            (entries / "night.json").write_bytes(entry.canonical_bytes)
            destination = root / "gallery.json"
            client = FakeHttpClient({})
            service = GalleryService(
                data_root=root / "data",
                client=client,
                probe=FakeProbe(),  # type: ignore[arg-type]
            )

            built = service.build(str(entries), str(destination))
            service.build(str(entries), str(destination), check=True)
            cached = service.cache_local(str(destination), expected_sha256=built["sha256"])
            browsed = service.browse(query="workbench", sort_by="compatible")
            report = service.report(entry.data["id"], result="success")

        self.assertEqual(cached["action"], "cached")
        self.assertEqual(len(browsed["entries"]), 1)
        self.assertEqual(report["report"]["plasma"], "6.7.4")
        self.assertFalse(report["uploaded"])
        self.assertIn("github.com", report["github_url"])
        self.assertEqual(client.requests, [])

    def test_refresh_uses_etag_and_retains_valid_cache_on_not_modified(self) -> None:
        entry_data, _, _ = gallery_fixture()
        entry = parse_gallery_entry_bytes(canonical_json_bytes(entry_data))
        snapshot = build_gallery_snapshot([entry])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_client = FakeHttpClient(
                {
                    GALLERY_SNAPSHOT_URL: HttpDocument(
                        200, snapshot.canonical_bytes, '"v1"', GALLERY_SNAPSHOT_URL
                    )
                }
            )
            service = GalleryService(
                data_root=root / "data",
                client=first_client,
                probe=FakeProbe(),  # type: ignore[arg-type]
            )
            service.refresh()

            second_client = FakeHttpClient(
                {
                    GALLERY_SNAPSHOT_URL: HttpDocument(
                        304, b"", '"v1"', GALLERY_SNAPSHOT_URL
                    )
                }
            )
            service.client = second_client
            result = service.refresh()

        self.assertEqual(result["action"], "not_modified")
        self.assertEqual(second_client.requests[0][2], '"v1"')

    def test_cache_hash_mismatch_does_not_replace_existing_snapshot(self) -> None:
        entry_data, _, _ = gallery_fixture()
        snapshot = build_gallery_snapshot(
            [parse_gallery_entry_bytes(canonical_json_bytes(entry_data))]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "gallery.json"
            source.write_bytes(snapshot.canonical_bytes)
            service = GalleryService(
                data_root=root / "data",
                client=FakeHttpClient({}),
                probe=FakeProbe(),  # type: ignore[arg-type]
            )
            with self.assertRaisesRegex(ValueError, "mismatch"):
                service.cache_local(str(source), expected_sha256="0" * 64)
            self.assertFalse(service.cache_path.exists())
            self.assertNotEqual(hashlib.sha256(b"changed").hexdigest(), snapshot.sha256)


if __name__ == "__main__":
    unittest.main()
