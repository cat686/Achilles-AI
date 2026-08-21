from __future__ import annotations

import argparse


parser = argparse.ArgumentParser()
parser.add_argument("--json", action="store_true")
args = parser.parse_args()
if args.json:
    # Intentional bug: Python repr uses single quotes and is not valid JSON.
    print({"status": "ok"})
else:
    print("status: ok")

