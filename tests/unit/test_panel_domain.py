from __future__ import annotations

import unittest

from alchemy.domain.panels import PANEL_SPACER, parse_panel_layout, resolve_panel_layout


def _panel(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "logical_id": "main",
        "location": "bottom",
        "floating": True,
        "height": {
            "unit": "screen_percent",
            "value": 4,
            "min_px": 32,
            "max_px": 64,
        },
        "screen_role": "primary",
        "widgets": [
            {"plugin": "org.kde.plasma.kickoff", "slot": "left"},
            {"plugin": "org.kde.plasma.icontasks", "slot": "center"},
            {"plugin": "org.kde.plasma.digitalclock", "slot": "right"},
        ],
    }
    value.update(overrides)
    return value


class PanelDomainTests(unittest.TestCase):
    def test_resolves_primary_screen_percent_and_semantic_slots(self) -> None:
        layout = parse_panel_layout({"format_version": 1, "panels": [_panel()]})

        resolved = resolve_panel_layout(
            layout,
            [
                {"x": 0, "y": 0, "width": 1920, "height": 1080},
                {"x": 1920, "y": 0, "width": 2560, "height": 1440},
            ],
        )

        self.assertEqual(resolved["panels"][0]["screen"], 0)
        self.assertEqual(resolved["panels"][0]["height"], 43)
        self.assertEqual(
            [widget["plugin"] for widget in resolved["panels"][0]["widgets"]],
            [
                "org.kde.plasma.kickoff",
                PANEL_SPACER,
                "org.kde.plasma.icontasks",
                PANEL_SPACER,
                "org.kde.plasma.digitalclock",
            ],
        )
        self.assertEqual(resolved["mappings"][0]["screen_role"], "primary")

    def test_all_screen_role_expands_and_clamps(self) -> None:
        layout = parse_panel_layout(
            {
                "format_version": 1,
                "panels": [
                    _panel(
                        screen_role="all",
                        height={
                            "unit": "screen_percent",
                            "value": 20,
                            "min_px": 20,
                            "max_px": 80,
                        },
                    )
                ],
            }
        )

        resolved = resolve_panel_layout(
            layout,
            [
                {"x": 0, "y": 0, "width": 800, "height": 600},
                {"x": 800, "y": 0, "width": 1920, "height": 1080},
            ],
        )

        self.assertEqual([panel["screen"] for panel in resolved["panels"]], [0, 1])
        self.assertEqual([panel["height"] for panel in resolved["panels"]], [80, 80])
        self.assertEqual(resolved["panels"][1]["logical_id"], "main@screen-1")

    def test_duplicate_mapped_edge_is_refused(self) -> None:
        layout = parse_panel_layout(
            {
                "format_version": 1,
                "panels": [_panel(screen_role="all"), _panel(logical_id="other")],
            }
        )

        with self.assertRaisesRegex(ValueError, "More than one panel maps"):
            resolve_panel_layout(
                layout, [{"x": 0, "y": 0, "width": 1920, "height": 1080}]
            )

    def test_unknown_fields_and_explicit_spacers_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            parse_panel_layout(
                {"format_version": 1, "panels": [_panel(arbitrary_command="touch /tmp/x")]}
            )
        with self.assertRaisesRegex(ValueError, "spacer placement"):
            parse_panel_layout(
                {
                    "format_version": 1,
                    "panels": [
                        _panel(widgets=[{"plugin": PANEL_SPACER, "slot": "center"}])
                    ],
                }
            )

    def test_custom_length_requires_a_dimension(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires length"):
            parse_panel_layout(
                {"format_version": 1, "panels": [_panel(length_mode="custom")]}
            )


if __name__ == "__main__":
    unittest.main()
