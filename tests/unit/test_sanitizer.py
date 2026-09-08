from __future__ import annotations

import unittest

from alchemy.domain.sanitizer import SanitizationContext, scan_publication


class SanitizerTests(unittest.TestCase):
    def test_detects_publication_hazards_without_echoing_values(self) -> None:
        secret = "ghp_123456789012345678901234567890"
        payload = {
            "path": "/home/localuser/Pictures/wallpaper.png",
            "contact": "person@example.com",
            "credential": secret,
            "recent_files": ["work"],
            "clientSecret": "not-even-token-shaped",
            "sessionState": "opaque",
            "key": "-----BEGIN PRIVATE KEY-----",
            "network": "Office Secret WiFi",
            "machine": "desktop-host",
        }
        report = scan_publication(
            payload,
            SanitizationContext(
                home="/home/localuser",
                username="localuser",
                hostname="desktop-host",
                wifi_names=("Office Secret WiFi",),
            ),
        )

        codes = {finding.code for finding in report.findings}
        self.assertFalse(report.safe)
        self.assertTrue(
            {
                "absolute_or_home_path",
                "home_directory",
                "username",
                "email_address",
                "token_like_value",
                "non_visual_or_sensitive_key",
                "private_key",
                "wifi_name",
                "hostname",
            }.issubset(codes)
        )
        self.assertNotIn(secret, str(report.to_dict()))

    def test_allows_https_sources_and_visual_identifiers(self) -> None:
        report = scan_publication(
            {
                "repo": "https://example.com/creator/rice",
                "theme": "Breeze Dark",
                "font": "Noto Sans,10,-1,5,50,0,0,0,0,0",
            },
            SanitizationContext(home="/home/localuser", username="localuser"),
        )

        self.assertTrue(report.safe)


if __name__ == "__main__":
    unittest.main()
