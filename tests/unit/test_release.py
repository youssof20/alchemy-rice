from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from alchemy.domain.release import (
    EVIDENCE_SCHEMA_URI,
    MIN_EXTERNAL_BETA_REPORTS,
    REQUIRED_DESTRUCTIVE_IDS,
    REQUIRED_VM_IDS,
    evaluate_release,
    parse_release_evidence,
)

ROOT = Path(__file__).parents[2]
EVIDENCE_PATH = ROOT / "release" / "evidence-v1.json"


def complete_evidence() -> dict[str, object]:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    evidence["release"] = "0.1.0b1"
    evidence["source_commit"] = "a" * 40
    packages = evidence["packages"]
    assert isinstance(packages, dict)
    for name, record in packages.items():
        record.update(
            status="passed",
            evidence_url=f"https://github.com/youssof20/alchemy-rice/issues/{name}",
        )
    vm_results = evidence["vm_results"]
    assert isinstance(vm_results, list)
    for index, record in enumerate(vm_results, start=1):
        record["plasma_version"] = "6.8.0" if record["id"] == "plasma-6.8-wayland" else "6.7.4"
        record["status"] = "passed"
        record["evidence_url"] = (
            f"https://github.com/youssof20/alchemy-rice/issues/{100 + index}"
        )
    destructive = evidence["destructive_tests"]
    assert isinstance(destructive, list)
    for index, record in enumerate(destructive, start=1):
        record["status"] = "passed"
        record["evidence_url"] = (
            f"https://github.com/youssof20/alchemy-rice/issues/{200 + index}"
        )
    evidence["beta_reports"] = [
        {
            "report_url": f"https://github.com/youssof20/alchemy-rice/issues/{300 + index}",
            "distro": "arch" if index % 2 else "fedora",
            "plasma_version": "6.7.4" if index < 3 else "6.8.0",
            "session": "wayland",
            "outcome": "passed",
        }
        for index in range(MIN_EXTERNAL_BETA_REPORTS)
    ]
    evidence["recording"] = {
        "url": "https://github.com/youssof20/alchemy-rice/releases/download/v0.1.0b1/demo.webm",
        "sha256": "b" * 64,
        "duration_seconds": 30,
        "plasma_version": "6.7.4",
        "session": "wayland",
        "shows_apply": True,
        "shows_verify": True,
        "shows_revert": True,
        "multiple_applications": True,
        "generated_visuals": False,
    }
    evidence["community_rice"] = {
        "source_url": "https://github.com/example/desktop-rice",
        "commit": "c" * 40,
        "rice_sha256": "d" * 64,
        "apply_report_url": "https://github.com/youssof20/alchemy-rice/issues/400",
        "status": "passed",
    }
    return evidence


class ReleaseEvidenceTests(unittest.TestCase):
    def test_pending_repository_evidence_is_valid_and_blocks_beta_and_launch(self) -> None:
        evidence = parse_release_evidence(EVIDENCE_PATH.read_bytes())

        report = evaluate_release(evidence, ROOT)

        self.assertEqual(evidence["$schema"], EVIDENCE_SCHEMA_URI)
        self.assertFalse(report["beta_ready"])
        self.assertFalse(report["launch_ready"])
        beta_gates = {item["gate"] for item in report["beta_blockers"]}
        self.assertIn("source.commit", beta_gates)
        self.assertIn("package.arch", beta_gates)
        launch_gates = {item["gate"] for item in report["launch_blockers"]}
        self.assertIn("recording", launch_gates)
        self.assertIn("beta.report_count", launch_gates)

    def test_complete_multi_distro_evidence_passes_both_gates(self) -> None:
        report = evaluate_release(complete_evidence(), ROOT)

        self.assertTrue(report["beta_ready"])
        self.assertTrue(report["launch_ready"])
        self.assertEqual(report["beta_blockers"], [])
        self.assertEqual(report["launch_blockers"], [])

    def test_matrix_ids_and_evidence_urls_are_strict(self) -> None:
        evidence = complete_evidence()
        vm_results = evidence["vm_results"]
        assert isinstance(vm_results, list)
        duplicate = copy.deepcopy(evidence)
        duplicate_results = duplicate["vm_results"]
        assert isinstance(duplicate_results, list)
        duplicate_results[0]["id"] = duplicate_results[1]["id"]
        with self.assertRaisesRegex(ValueError, "required matrix"):
            evaluate_release(duplicate, ROOT)

        vm_results[0]["evidence_url"] = "http://insecure.example/result"
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            evaluate_release(evidence, ROOT)

        vm_results[0]["evidence_url"] = "https://127.0.0.1/result"
        with self.assertRaisesRegex(ValueError, "private or local"):
            evaluate_release(evidence, ROOT)

    def test_published_schema_is_json_and_has_runtime_matrix_sizes(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "release-evidence-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(schema["$id"], EVIDENCE_SCHEMA_URI)
        self.assertEqual(schema["properties"]["vm_results"]["minItems"], len(REQUIRED_VM_IDS))
        self.assertEqual(
            schema["properties"]["destructive_tests"]["minItems"],
            len(REQUIRED_DESTRUCTIVE_IDS),
        )


if __name__ == "__main__":
    unittest.main()
