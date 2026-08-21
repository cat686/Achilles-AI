from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from goal_verifier.capture import capture_command
from goal_verifier.evidence import load_profile, verification_path, write_json
from goal_verifier.schema import SchemaError
from goal_verifier.sealing import load_seal, seal_verification

from tests.helpers import initialize_root, obligation, requirement


class SealingTests(unittest.TestCase):
    def test_seal_is_idempotent_before_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = initialize_root(root, [requirement()], sealed=False)
            first, created = seal_verification(root, plan, load_profile(root))
            second, created_again = seal_verification(root, plan, load_profile(root))
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(first["session_id"], second["session_id"])

    def test_plan_drift_invalidates_seal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = initialize_root(root, [requirement()])
            plan["goal"] = "Changed after approval"
            write_json(verification_path(root) / "plan.json", plan)
            with self.assertRaisesRegex(SchemaError, "plan digest"):
                seal_verification(root, plan, load_profile(root))

    def test_generated_artifact_drift_blocks_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            planned = obligation(
                source="generated_test",
                artifacts=[".verification/generated/test_acceptance.py"],
            )
            plan = initialize_root(root, [requirement(obligations=[planned])])
            (root / ".verification" / "generated" / "test_acceptance.py").write_text(
                "tampered\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(SchemaError, "sealed artifact changed"):
                capture_command(
                    root=root,
                    plan=plan,
                    profile=load_profile(root),
                    seal=load_seal(root),
                    requirement_id="R1",
                    obligation_id="R1-O1",
                )

    def test_reseal_is_rejected_after_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = initialize_root(root, [requirement()])
            capture_command(
                root=root,
                plan=plan,
                profile=load_profile(root),
                seal=load_seal(root),
                requirement_id="R1",
                obligation_id="R1-O1",
            )
            with self.assertRaisesRegex(SchemaError, "after evidence"):
                seal_verification(root, plan, load_profile(root))


if __name__ == "__main__":
    unittest.main()
