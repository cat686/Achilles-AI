from __future__ import annotations

import argparse
import json


parser = argparse.ArgumentParser()
parser.add_argument("--json", action="store_true")
args = parser.parse_args()
if args.json:
    print(json.dumps({"status": "ok"}))
else:
    print("status: ok")

