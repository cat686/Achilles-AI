from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from goal_verifier.cli import main
from goal_verifier.evidence import create_layout, write_json
from goal_verifier.report import generate_reports

from tests.helpers import requirement


class LegacyArtifactTests(unittest.TestCase):
    def test_v0_report_is_forced_to_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = create_layout(root)
            legacy_requirement = requirement()
            legacy_requirement["obligations"][0].pop("experiment")
            legacy_requirement["obligations"][0].pop("oracle")
            plan = {
                "version": "0",
                "goal": "Legacy goal",
                "created_at": "2026-01-01T00:00:00Z",
                "repository": {"root": str(root), "git_commit": None, "worktree_dirty": None},
                "requirements": [legacy_requirement],
            }
            write_json(directory / "plan.json", plan)
            report = generate_reports(root, plan)
            self.assertEqual(report["verification_state"], "LEGACY")
            self.assertEqual(report["overall_verdict"], "UNKNOWN")
            self.assertEqual(main(["--root", str(root), "run", "--requirement", "R1", "--obligation", "R1-O1"]), 2)


if __name__ == "__main__":
    unittest.main()
