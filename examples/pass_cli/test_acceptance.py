from __future__ import annotations

import json
import subprocess
import sys
import unittest


class JsonOutputAcceptanceTest(unittest.TestCase):
    def test_json_output_is_valid(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", "app.py", "--json"], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"status": "ok"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

