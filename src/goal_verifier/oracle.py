"""Typed, runtime-evaluated executable oracles."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .digest import resolve_relative_file, sha256_bytes


def _json_document(value: bytes) -> Any:
    def reject_constant(token: str) -> None:
        raise ValueError(f"non-standard JSON constant: {token}")

    return json.loads(value.decode("utf-8"), parse_constant=reject_constant)


def _json_pointer(document: Any, pointer: str) -> Any:
    current = document
    for raw_token in pointer.split("/")[1:]:
        if "~" in raw_token.replace("~0", "").replace("~1", ""):
            raise KeyError(pointer)
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit():
                raise KeyError(pointer)
            index = int(token)
            if index >= len(current):
                raise KeyError(pointer)
            current = current[index]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise KeyError(pointer)
    return current


def _exit_mismatch(exit_code: int, expected: int) -> tuple[str, str, dict[str, Any]] | None:
    if exit_code == expected:
        return None
    return (
        "CONTRADICTS",
        f"Expected exit code {expected}, observed {exit_code}.",
        {"expected_exit_code": expected, "observed_exit_code": exit_code, "matched": False},
    )


def evaluate_oracle(
    *, root: Path, oracle: dict[str, Any], exit_code: int, stdout: bytes
) -> tuple[str, str, dict[str, Any]]:
    """Return assessment, reason, and structured observations."""
    kind = oracle["kind"]
    if kind == "exit_code":
        mismatch = _exit_mismatch(exit_code, oracle["expected"])
        if mismatch:
            return mismatch
        return (
            "SUPPORTS",
            f"The sealed command met the exit-code oracle ({oracle['expected']}).",
            {"expected_exit_code": oracle["expected"], "observed_exit_code": exit_code, "matched": True},
        )

    mismatch = _exit_mismatch(exit_code, oracle["expected_exit_code"])
    if mismatch:
        return mismatch

    if kind == "stdout_json":
        try:
            document = _json_document(stdout)
        except (UnicodeDecodeError, ValueError) as exc:
            return (
                "CONTRADICTS",
                f"stdout is not one valid UTF-8 JSON document: {exc}",
                {"valid_json": False, "error": str(exc)},
            )
        return (
            "SUPPORTS",
            "stdout is one valid UTF-8 JSON document and the expected exit code was observed.",
            {"valid_json": True, "document_type": type(document).__name__},
        )

    if kind == "differential":
        baseline_path = resolve_relative_file(root, oracle["baseline"], "differential baseline")
        baseline = baseline_path.read_bytes()
        result: dict[str, Any] = {
            "comparison": oracle["comparison"],
            "baseline": oracle["baseline"],
            "baseline_sha256": sha256_bytes(baseline),
            "observed_sha256": sha256_bytes(stdout),
        }
        if oracle["comparison"] == "bytes":
            matched = stdout == baseline
        else:
            try:
                matched = _json_document(stdout) == _json_document(baseline)
            except (UnicodeDecodeError, ValueError) as exc:
                result.update({"matched": False, "error": str(exc)})
                return "CONTRADICTS", f"Differential JSON could not be parsed: {exc}", result
        result["matched"] = matched
        if not matched:
            return "CONTRADICTS", "Observed stdout does not match the sealed baseline.", result
        return "SUPPORTS", "Observed stdout matches the sealed baseline.", result

    if kind == "performance":
        try:
            document = _json_document(stdout)
            observed = _json_pointer(document, oracle["metric_pointer"])
            runs = _json_pointer(document, oracle["runs_pointer"])
        except (UnicodeDecodeError, ValueError, KeyError) as exc:
            return (
                "CONTRADICTS",
                f"Performance measurement does not satisfy the sealed JSON protocol: {exc}",
                {"valid_measurement": False, "error": str(exc)},
            )
        if (
            isinstance(observed, bool)
            or not isinstance(observed, (int, float))
            or not math.isfinite(observed)
            or isinstance(runs, bool)
            or not isinstance(runs, int)
        ):
            return (
                "CONTRADICTS",
                "Performance metric must be finite numeric data and run count must be an integer.",
                {"valid_measurement": False, "observed": observed, "number_of_runs": runs},
            )
        result = {
            "valid_measurement": True,
            "observed": observed,
            "threshold": oracle["threshold"],
            "operator": oracle["operator"],
            "unit": oracle["unit"],
            "number_of_runs": runs,
            "minimum_runs": oracle["minimum_runs"],
            "method": oracle["method"],
        }
        if runs < oracle["minimum_runs"]:
            result["matched"] = False
            return "CONTRADICTS", "Performance measurement used fewer runs than the sealed minimum.", result
        operations = {
            "lt": lambda left, right: left < right,
            "lte": lambda left, right: left <= right,
            "gt": lambda left, right: left > right,
            "gte": lambda left, right: left >= right,
            "eq": lambda left, right: left == right,
        }
        matched = operations[oracle["operator"]](observed, oracle["threshold"])
        result["matched"] = matched
        if not matched:
            return "CONTRADICTS", "Observed performance does not meet the sealed threshold.", result
        return "SUPPORTS", "Observed performance meets the sealed threshold.", result

    raise ValueError(f"unsupported oracle kind: {kind}")
