from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from goal_verifier.cli import main
from goal_verifier.evidence import read_json

from tests.helpers import obligation, requirement


class CliTests(unittest.TestCase):
    def test_init_run_status_and_report_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "oracle.txt").write_text("sealed oracle artifact\n", encoding="utf-8")
            requirements_path = root / "requirements.json"
            requirements_path.write_text(json.dumps([requirement()]), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    main(
                        [
                            "--root",
                            str(root),
                            "init",
                            "--goal",
                            "The acceptance command succeeds",
                            "--requirements",
                            str(requirements_path),
                        ]
                    ),
                    0,
                )
                self.assertEqual(main(["--root", str(root), "seal"]), 0)
                self.assertEqual(
                    main(
                        [
                            "--root",
                            str(root),
                            "run",
                            "--requirement",
                            "R1",
                            "--obligation",
                            "R1-O1",
                        ]
                    ),
                    0,
                )
                self.assertEqual(main(["--root", str(root), "report"]), 0)
                self.assertEqual(main(["--root", str(root), "status"]), 0)
            self.assertIn("Evidence E0001 recorded", output.getvalue())
            report = read_json(root / ".verification" / "report.json")
            self.assertEqual(report["overall_verdict"], "PASS")

    def test_record_static_evidence_via_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("Feature exists.\n", encoding="utf-8")
            requirements_path = root / "requirements.json"
            requirements_path.write_text(
                json.dumps([requirement(obligations=[obligation("R1-O1", "STATIC")])]), encoding="utf-8"
            )
            self.assertEqual(
                main(["--root", str(root), "init", "--goal", "Document feature", "--requirements", str(requirements_path)]),
                0,
            )
            self.assertEqual(
                main(["--root", str(root), "seal"]),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "--root",
                        str(root),
                        "record",
                        "--requirement",
                        "R1",
                        "--obligation",
                        "R1-O1",
                        "--description",
                        "Feature is documented",
                        "--assessment",
                        "SUPPORTS",
                    ]
                ),
                0,
            )

    def test_run_rejects_unknown_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "oracle.txt").write_text("sealed oracle artifact\n", encoding="utf-8")
            requirements_path = root / "requirements.json"
            requirements_path.write_text(json.dumps([requirement()]), encoding="utf-8")
            self.assertEqual(
                main(["--root", str(root), "init", "--goal", "Goal", "--requirements", str(requirements_path)]),
                0,
            )
            self.assertEqual(main(["--root", str(root), "seal"]), 0)
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                result = main(
                    [
                        "--root",
                        str(root),
                        "run",
                        "--requirement",
                        "R9",
                        "--obligation",
                        "R9-O1",
                    ]
                )
            self.assertEqual(result, 2)
            self.assertIn("requirement not found", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
