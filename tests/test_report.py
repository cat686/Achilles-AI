from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from goal_verifier.capture import capture_command
from goal_verifier.evidence import load_profile, read_json, verification_path, write_json
from goal_verifier.report import calculate_overall, generate_reports
from goal_verifier.sealing import load_seal

from tests.helpers import initialize_root, obligation, requirement


class OverallVerdictTests(unittest.TestCase):
    def _items(self, *verdicts: str) -> list[dict[str, str]]:
        return [{"priority": "MUST", "verdict": verdict} for verdict in verdicts]

    def test_must_fail_makes_overall_fail(self) -> None:
        self.assertEqual(calculate_overall(self._items("PASS", "FAIL")), "FAIL")

    def test_must_partial_makes_overall_partial(self) -> None:
        self.assertEqual(calculate_overall(self._items("PASS", "PARTIAL")), "PARTIAL")

    def test_must_unknown_makes_overall_unknown(self) -> None:
        self.assertEqual(calculate_overall(self._items("PASS", "UNKNOWN")), "UNKNOWN")

    def test_all_must_pass_makes_overall_pass(self) -> None:
        self.assertEqual(calculate_overall(self._items("PASS", "PASS")), "PASS")

    def test_should_failure_does_not_make_overall_fail(self) -> None:
        items = [
            {"priority": "MUST", "verdict": "PASS"},
            {"priority": "SHOULD", "verdict": "FAIL"},
        ]
        self.assertEqual(calculate_overall(items), "PASS")


class ReportTests(unittest.TestCase):
    def _capture(self, root: Path, plan: dict, requirement_id: str, obligation_id: str) -> dict:
        return capture_command(
            root=root,
            plan=plan,
            profile=load_profile(root),
            seal=load_seal(root),
            requirement_id=requirement_id,
            obligation_id=obligation_id,
        )

    def test_pass_and_fail_trace_to_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = initialize_root(
                root,
                [
                    requirement("R1", obligations=[obligation("R1-O1", "TEST")]),
                    requirement(
                        "R2",
                        obligations=[
                            obligation(
                                "R2-O1",
                                "TEST",
                                argv=[sys.executable, "-B", "-c", "raise SystemExit(1)"],
                            )
                        ],
                    ),
                ],
            )
            self._capture(root, plan, "R1", "R1-O1")
            self._capture(root, plan, "R2", "R2-O1")
            report = generate_reports(root, plan)
            by_id = {item["id"]: item for item in report["requirements"]}
            self.assertEqual(by_id["R1"]["verdict"], "PASS")
            self.assertEqual(by_id["R1"]["evidence"], ["E0001"])
            self.assertEqual(by_id["R2"]["verdict"], "FAIL")
            self.assertEqual(by_id["R2"]["evidence"], ["E0002"])
            self.assertEqual(report["overall_verdict"], "FAIL")
            self.assertTrue((verification_path(root) / "report.md").is_file())
            persisted = read_json(verification_path(root) / "report.json")
            self.assertEqual(persisted["overall_verdict"], "FAIL")

    def test_some_supported_obligations_make_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = initialize_root(
                root,
                [
                    requirement(
                        obligations=[obligation("R1-O1", "TEST"), obligation("R1-O2", "RUNTIME")]
                    )
                ],
            )
            self._capture(root, plan, "R1", "R1-O1")
            report = generate_reports(root, plan)
            self.assertEqual(report["requirements"][0]["verdict"], "PARTIAL")
            self.assertEqual(report["overall_verdict"], "PARTIAL")

    def test_no_evidence_makes_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = initialize_root(
                root, [requirement(obligations=[obligation("R1-O1", "HUMAN")])]
            )
            report = generate_reports(root, plan)
            self.assertEqual(report["requirements"][0]["verdict"], "UNKNOWN")
            self.assertEqual(report["overall_verdict"], "UNKNOWN")

    def test_non_verification_change_is_reported_and_blocks_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "production.py"
            source.write_text("value = 1\n", encoding="utf-8")
            plan = initialize_root(root, [requirement()])
            self._capture(root, plan, "R1", "R1-O1")
            source.write_text("value = 2\n", encoding="utf-8")
            report = generate_reports(root, plan)
            self.assertEqual(report["requirements_verdict"], "UNKNOWN")
            self.assertEqual(report["overall_verdict"], "UNKNOWN")
            self.assertTrue(report["integrity"]["violation"])
            self.assertEqual(report["integrity"]["non_verification_changes"]["modified"], ["production.py"])
            markdown = (verification_path(root) / "report.md").read_text(encoding="utf-8")
            self.assertIn("State: **STALE**", markdown)
            self.assertIn("production.py", markdown)

    def test_mismatched_evidence_link_is_excluded_and_blocks_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = initialize_root(
                root,
                [
                    requirement("R1", obligations=[obligation("R1-O1", "TEST")]),
                    requirement("R2", priority="SHOULD", obligations=[obligation("R2-O1", "TEST")]),
                ],
            )
            captured = self._capture(root, plan, "R1", "R1-O1")
            evidence_path = verification_path(root) / "evidence" / "E0001.json"
            captured["requirement_id"] = "R2"
            write_json(evidence_path, captured)
            report = generate_reports(root, plan)
            self.assertEqual(report["requirements"][0]["verdict"], "UNKNOWN")
            self.assertEqual(report["overall_verdict"], "UNKNOWN")
            self.assertEqual(report["invalid_evidence"][0]["id"], "E0001")


if __name__ == "__main__":
    unittest.main()
