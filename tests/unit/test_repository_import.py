from __future__ import annotations

import unittest

from alchemy.domain.repository_import import (
    RepositoryDocument,
    analyze_repository,
    should_read_repository_blob,
    validate_repository_source,
)
from alchemy.domain.sanitizer import SanitizationContext

REPOSITORY = "https://github.com/example/dotfiles.git"
COMMIT = "a" * 40


def metadata() -> dict[str, object]:
    return {
        "id": "github:example/dotfiles:import",
        "name": "Imported dotfiles",
        "version": "1.0.0",
        "author": {"name": "Example author"},
        "source": {
            "repo": REPOSITORY,
            "release": "v1.0.0",
            "commit": COMMIT,
        },
        "compatibility": {
            "plasma": ">=6.0,<7.0",
            "session": ["wayland"],
            "tested": [],
        },
        "licenses": [],
    }


def document(
    path: str,
    data: bytes | None,
    *,
    mode: str = "100644",
    object_type: str = "blob",
    reason: str | None = None,
) -> RepositoryDocument:
    return RepositoryDocument(
        path,
        mode,
        object_type,
        len(data) if data is not None else None,
        data,
        reason,
    )


class RepositoryImportDomainTests(unittest.TestCase):
    def test_maps_allowlisted_kde_values_and_reports_every_other_kind(self) -> None:
        documents = (
            document(
                ".config/kdeglobals",
                b"[General]\nColorScheme=BreezeDark\nfont=Noto Sans,10\nIgnored=value\n"
                b"[Icons]\nTheme=Breeze\n",
            ),
            document(".config/kcminputrc", b"[Mouse]\ncursorTheme=Breeze\ncursorSize=24\n"),
            document("terminal/kitty.conf", b"font_family Noto Sans Mono\n"),
            document("scripts/install.sh", None, mode="100755"),
            document("wallpapers/night.png", None, reason="binary reference"),
            document("packages.txt", b"git\n# note\nstarship\ninvalid package\n"),
            document("notes.xml", None, reason="unsupported extension"),
            document("vendor", None, mode="160000", object_type="commit"),
        )

        result = analyze_repository(
            documents,
            metadata(),
            repository_url=REPOSITORY,
            commit=COMMIT,
            sanitizer_context=SanitizationContext(),
        )

        self.assertEqual(result.manifest["components"]["colors"]["scheme"], "BreezeDark")
        self.assertEqual(result.manifest["components"]["cursor"]["size"], 24)
        self.assertEqual(result.dependency_candidates, ("git", "starship"))
        kinds = {item.kind for item in result.recognized}
        self.assertIn("kde_kconfig", kinds)
        self.assertIn("Kitty configuration", kinds)
        self.assertIn("installer_script", kinds)
        self.assertIn("wallpaper_asset", kinds)
        self.assertIn("dependency_manifest", kinds)
        self.assertIn("git_submodule", kinds)
        self.assertEqual(result.unsupported[0].path, "notes.xml")
        self.assertFalse(result.export_ready)
        payload = result.to_dict()
        self.assertFalse(payload["applied"])
        self.assertFalse(payload["executed_repository_code"])
        self.assertEqual(
            payload["recognized"][0]["source_url"],
            f"https://github.com/example/dotfiles/blob/{COMMIT}/.config/kdeglobals",
        )

    def test_conflicts_are_omitted_instead_of_resolved_by_file_order(self) -> None:
        documents = (
            document("one/kdeglobals", b"[General]\nColorScheme=BreezeDark\n"),
            document("two/kdeglobals", b"[General]\nColorScheme=Oxygen\n"),
        )

        result = analyze_repository(
            documents,
            metadata(),
            repository_url=REPOSITORY,
            commit=COMMIT,
            sanitizer_context=SanitizationContext(),
        )

        self.assertEqual(result.manifest["components"], {})
        self.assertIn("conflicting_setting", {finding.code for finding in result.findings})
        self.assertFalse(result.export_ready)

    def test_secret_content_is_quarantined_and_personal_path_is_redacted(self) -> None:
        token = "ghp_" + "A" * 24
        documents = (
            document("home/alice/kitty.conf", f"token={token}\n".encode()),
            document(".env", None, reason="sensitive"),
        )

        result = analyze_repository(
            documents,
            metadata(),
            repository_url=REPOSITORY,
            commit=COMMIT,
            sanitizer_context=SanitizationContext(username="alice"),
        )

        serialized = str(result.to_dict())
        self.assertNotIn("alice", serialized)
        self.assertNotIn(token, serialized)
        self.assertIn("<redacted-path:", serialized)
        self.assertIn("content_token_like_value", serialized)
        self.assertIn("sensitive_file_omitted", serialized)

    def test_source_validation_rejects_mutable_or_credentialed_inputs(self) -> None:
        invalid = (
            (REPOSITORY, "main"),
            ("http://github.com/example/dotfiles.git", COMMIT),
            ("https://user:secret@github.com/example/dotfiles.git", COMMIT),
            ("https://example.com/example/dotfiles.git", COMMIT),
            ("https://github.com:444/example/dotfiles.git", COMMIT),
            ("https://github.com/example/dotfiles.git?ref=main", COMMIT),
        )
        for url, commit in invalid:
            with self.subTest(url=url, commit=commit), self.assertRaises(ValueError):
                validate_repository_source(url, commit)

    def test_blob_policy_reads_only_bounded_static_text_candidates(self) -> None:
        self.assertTrue(should_read_repository_blob(".config/kdeglobals"))
        self.assertTrue(should_read_repository_blob("config/starship.toml"))
        self.assertFalse(should_read_repository_blob("wallpaper.png"))
        self.assertFalse(should_read_repository_blob(".env"))
        self.assertFalse(should_read_repository_blob("archive.zip"))


if __name__ == "__main__":
    unittest.main()
