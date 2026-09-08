from __future__ import annotations

import unittest

from alchemy.domain.app_adapters import (
    extract_repository_app,
    parse_owned_config,
    render_owned_config,
    validate_app_settings,
)


def app_fixtures() -> dict[str, dict[str, object]]:
    return {
        "konsole": {
            "format_version": 1,
            "color_scheme": "Breeze",
            "font_family": "JetBrains Mono",
            "font_size": 11,
            "bold_intense": True,
            "line_spacing": 1,
            "cursor_shape": "ibeam",
        },
        "kitty": {
            "format_version": 1,
            "font_family": "JetBrains Mono",
            "font_size": 11,
            "foreground": "#d8dee9",
            "background": "#2e3440",
            "cursor": "#88c0d0",
            "cursor_shape": "beam",
            "background_opacity": 0.95,
            "palette": [f"#{index:02x}{index:02x}{index:02x}" for index in range(16)],
        },
        "starship": {
            "format_version": 1,
            "add_newline": False,
            "palette": {"accent": "#88c0d0", "muted": "#4c566a"},
            "modules": ["directory", "git_branch", "git_status", "line_break", "character"],
            "character_symbol": "\u276f",
            "character_color": "#88c0d0",
            "directory_color": "#81a1c1",
            "git_branch_color": "#a3be8c",
        },
        "fastfetch": {
            "format_version": 1,
            "logo": {"type": "small", "source": "arch"},
            "separator": " :: ",
            "key_color": "blue",
            "title_color": "cyan",
            "output_color": "white",
            "bright_color": False,
            "modules": ["os", "kernel", "uptime", "de", "terminal", "memory"],
        },
    }


class AppAdapterDomainTests(unittest.TestCase):
    def test_each_owned_format_round_trips_its_normalized_settings(self) -> None:
        for app, settings in app_fixtures().items():
            with self.subTest(app=app):
                normalized = validate_app_settings(app, settings)
                rendered = render_owned_config(app, normalized)
                self.assertEqual(parse_owned_config(app, rendered), normalized)

    def test_owned_parsers_refuse_behavioral_or_identity_bearing_content(self) -> None:
        unsafe = {
            "konsole": b"[General]\nName=Alchemy\nParent=FALLBACK/\nCommand=ssh host\n",
            "kitty": b"font_size 12\nmap ctrl+x launch sh\n",
            "starship": b"add_newline=false\n[custom.test]\ncommand='whoami'\n",
            "fastfetch": b'{"modules":["title","os"]}',
        }
        for app, raw in unsafe.items():
            with self.subTest(app=app), self.assertRaises(ValueError):
                parse_owned_config(app, raw)

    def test_repository_extractors_keep_only_reviewed_visual_fields(self) -> None:
        inputs = {
            "konsole": (
                b"[Appearance]\nColorScheme=Breeze\nFont=Hack,12,-1,5\n"
                b"[General]\nName=Work\nCommand=ssh host\n",
                "color_scheme",
            ),
            "kitty": (b"font_size 12\nbackground #101010\nmap ctrl+x launch sh\n", "background"),
            "starship": (
                b"add_newline=false\npalette='nord'\n[palettes.nord]\nblue='#112233'\n"
                b"[custom.user]\ncommand='whoami'\n",
                "palette",
            ),
            "fastfetch": (
                b'{"display":{"separator":" -> "},"modules":["title","os"]}',
                "separator",
            ),
        }
        for app, (raw, expected) in inputs.items():
            with self.subTest(app=app):
                settings, ignored = extract_repository_app(app, raw)
                assert settings is not None
                self.assertIn(expected, settings)
                self.assertGreater(ignored, 0)

    def test_jsonc_parser_preserves_comment_markers_and_trailing_text_inside_strings(self) -> None:
        raw = b'''{
          // comment
          "display": {"separator": "https://example.test/,}"},
          "modules": ["os",],
        }'''

        settings, ignored = extract_repository_app("fastfetch", raw)

        assert settings is not None
        self.assertEqual(settings["separator"], "https://example.test/,}")
        self.assertEqual(ignored, 0)

        self.assertEqual(
            extract_repository_app(
                "fastfetch", b'{"display":{"brightColor":tr/* no join */ue}}'
            ),
            (None, 1),
        )

    def test_validation_rejects_unsafe_fastfetch_identity_and_partial_kitty_palette(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe"):
            validate_app_settings(
                "fastfetch", {"format_version": 1, "modules": ["title", "os"]}
            )
        with self.assertRaisesRegex(ValueError, "16"):
            validate_app_settings(
                "kitty", {"format_version": 1, "palette": ["#000000"]}
            )
        with self.assertRaisesRegex(ValueError, "unsupported characters"):
            validate_app_settings(
                "fastfetch",
                {"format_version": 1, "logo": {"type": "small", "source": "../logo"}},
            )
        with self.assertRaisesRegex(ValueError, "formatting markup"):
            validate_app_settings(
                "starship",
                {
                    "format_version": 1,
                    "character_symbol": "](red)",
                    "character_color": "#ffffff",
                },
            )


if __name__ == "__main__":
    unittest.main()
