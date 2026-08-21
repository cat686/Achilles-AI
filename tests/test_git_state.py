from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from goal_verifier.git_state import capture_file_snapshot, capture_git_state, compare_snapshots


class GitStateTests(unittest.TestCase):
    def test_commit_and_dirty_state_are_captured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "initial"], check=True)

            clean = capture_git_state(root)
            self.assertTrue(clean["available"])
            self.assertRegex(clean["commit"], r"^[0-9a-f]{40}$")
            self.assertFalse(clean["dirty"])

            (root / "tracked.txt").write_text("two\n", encoding="utf-8")
            dirty = capture_git_state(root)
            self.assertTrue(dirty["dirty"])
            self.assertTrue(any("tracked.txt" in line for line in dirty["status_porcelain"]))

    def test_non_git_directory_records_unavailable_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = capture_git_state(Path(temporary))
            self.assertFalse(state["available"])
            self.assertIsNone(state["commit"])
            self.assertIsNone(state["dirty"])

    def test_snapshot_detects_changes_but_excludes_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source.txt").write_text("before", encoding="utf-8")
            before = capture_file_snapshot(root)
            (root / ".verification").mkdir()
            (root / ".verification" / "ignored.txt").write_text("ignored", encoding="utf-8")
            (root / "source.txt").write_text("after", encoding="utf-8")
            (root / "added.txt").write_text("added", encoding="utf-8")
            after = capture_file_snapshot(root)
            changes = compare_snapshots(before, after)
            self.assertEqual(changes["modified"], ["source.txt"])
            self.assertEqual(changes["added"], ["added.txt"])
            self.assertFalse(any(".verification" in path for paths in changes.values() for path in paths))


if __name__ == "__main__":
    unittest.main()

