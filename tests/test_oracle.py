from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from goal_verifier.oracle import evaluate_oracle


class OracleTests(unittest.TestCase):
    def test_stdout_json_accepts_one_document(self) -> None:
        assessment, _, result = evaluate_oracle(
            root=Path.cwd(),
            oracle={"kind": "stdout_json", "expected_exit_code": 0},
            exit_code=0,
            stdout=b'{"ok": true}\n',
        )
        self.assertEqual(assessment, "SUPPORTS")
        self.assertTrue(result["valid_json"])

    def test_differential_json_uses_semantic_equality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "baseline.json").write_text('{"a": 1, "b": 2}\n', encoding="utf-8")
            assessment, _, result = evaluate_oracle(
                root=root,
                oracle={
                    "kind": "differential",
                    "expected_exit_code": 0,
                    "baseline": "baseline.json",
                    "comparison": "json",
                },
                exit_code=0,
                stdout=b'{"b":2,"a":1}',
            )
            self.assertEqual(assessment, "SUPPORTS")
            self.assertTrue(result["matched"])

    def test_performance_rejects_insufficient_runs(self) -> None:
        oracle = {
            "kind": "performance",
            "expected_exit_code": 0,
            "metric_pointer": "/metrics/latency",
            "runs_pointer": "/runs",
            "operator": "lt",
            "threshold": 100,
            "minimum_runs": 5,
            "method": "wall clock",
            "unit": "ms",
        }
        assessment, _, result = evaluate_oracle(
            root=Path.cwd(), oracle=oracle, exit_code=0, stdout=json.dumps({"metrics": {"latency": 10}, "runs": 2}).encode()
        )
        self.assertEqual(assessment, "CONTRADICTS")
        self.assertFalse(result["matched"])

    def test_performance_rejects_non_finite_metric(self) -> None:
        oracle = {
            "kind": "performance",
            "expected_exit_code": 0,
            "metric_pointer": "/value",
            "runs_pointer": "/runs",
            "operator": "lt",
            "threshold": 100,
            "minimum_runs": 1,
            "method": "wall clock",
            "unit": "ms",
        }
        assessment, _, result = evaluate_oracle(
            root=Path.cwd(), oracle=oracle, exit_code=0, stdout=b'{"value": NaN, "runs": 1}'
        )
        self.assertEqual(assessment, "CONTRADICTS")
        self.assertFalse(result["valid_measurement"])


if __name__ == "__main__":
    unittest.main()
