"""Evidence sufficiency, verdict aggregation, and report rendering."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .capture import utc_now
from .evidence import list_evidence, read_json, verification_path, write_json
from .git_state import capture_file_snapshot, capture_git_state, compare_snapshots, has_changes
from .schema import validate_plan, validate_verdict


def calculate_overall(requirements: list[dict[str, Any]]) -> str:
    must_verdicts = [item["verdict"] for item in requirements if item["priority"] == "MUST"]
    for verdict in must_verdicts:
        validate_verdict(verdict)
    if "FAIL" in must_verdicts:
        return "FAIL"
    if "PARTIAL" in must_verdicts:
        return "PARTIAL"
    if "UNKNOWN" in must_verdicts or not must_verdicts:
        return "UNKNOWN"
    return "PASS"


def _assess_requirement(requirement: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    obligation_results: list[dict[str, Any]] = []
    all_supporting: list[str] = []
    all_contradicting: list[str] = []
    all_inconclusive: list[str] = []
    for obligation in requirement["obligations"]:
        matching = [item for item in evidence if item["obligation_id"] == obligation["id"]]
        supporting = [item["id"] for item in matching if item["assessment"] == "SUPPORTS"]
        contradicting = [item["id"] for item in matching if item["assessment"] == "CONTRADICTS"]
        inconclusive = [item["id"] for item in matching if item["assessment"] == "INCONCLUSIVE"]
        if contradicting:
            state = "CONTRADICTED"
        elif supporting:
            state = "SATISFIED"
        elif inconclusive:
            state = "INCONCLUSIVE"
        else:
            state = "MISSING"
        obligation_results.append(
            {
                **obligation,
                "state": state,
                "evidence": [item["id"] for item in matching],
                "supporting_evidence": supporting,
                "contradicting_evidence": contradicting,
                "inconclusive_evidence": inconclusive,
            }
        )
        all_supporting.extend(supporting)
        all_contradicting.extend(contradicting)
        all_inconclusive.extend(inconclusive)

    mandatory = [item for item in obligation_results if item["mandatory"]]
    if all_contradicting:
        verdict = "FAIL"
        references = all_contradicting
        reason = "Contradictory evidence provides a concrete counterexample."
    elif mandatory and all(item["state"] == "SATISFIED" for item in mandatory):
        verdict = "PASS"
        references = all_supporting
        reason = "All mandatory evidence obligations are satisfied with no contradictory evidence."
    elif all_supporting:
        verdict = "PARTIAL"
        references = all_supporting + all_inconclusive
        missing = [item["id"] for item in mandatory if item["state"] != "SATISFIED"]
        reason = f"Some evidence supports the requirement, but mandatory obligations remain unsatisfied: {', '.join(missing)}."
    else:
        verdict = "UNKNOWN"
        references = all_inconclusive
        reason = "No sufficient supporting evidence or concrete counterexample is available."
    validate_verdict(verdict)
    return {
        "id": requirement["id"],
        "text": requirement["text"],
        "source_text": requirement["source_text"],
        "priority": requirement["priority"],
        "notes": requirement.get("notes", ""),
        "verdict": verdict,
        "evidence": list(dict.fromkeys(references)),
        "reason": reason,
        "obligations": obligation_results,
    }


def build_report(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    validate_plan(plan)
    evidence = list_evidence(root)
    known_requirements = {item["id"] for item in plan["requirements"]}
    obligation_owners = {
        obligation["id"]: (requirement["id"], obligation["type"])
        for requirement in plan["requirements"]
        for obligation in requirement["obligations"]
    }
    orphaned: list[str] = []
    invalid_evidence: list[dict[str, str]] = []
    usable_evidence: list[dict[str, Any]] = []
    for item in evidence:
        owner = obligation_owners.get(item["obligation_id"])
        if item["requirement_id"] not in known_requirements or owner is None:
            orphaned.append(item["id"])
            invalid_evidence.append({"id": item["id"], "reason": "Unknown requirement or obligation link."})
        elif owner[0] != item["requirement_id"]:
            invalid_evidence.append({"id": item["id"], "reason": "Obligation belongs to a different requirement."})
        elif owner[1] != item["type"]:
            invalid_evidence.append({"id": item["id"], "reason": "Evidence type does not match the planned obligation."})
        else:
            usable_evidence.append(item)
    assessed = [_assess_requirement(requirement, usable_evidence) for requirement in plan["requirements"]]
    requirements_verdict = calculate_overall(assessed)

    session_path = verification_path(root) / "session.json"
    current_snapshot = capture_file_snapshot(root)
    current_git = capture_git_state(root)
    if session_path.is_file():
        session = read_json(session_path)
        before_snapshot = session.get("files_before", {"files": {}})
        before_git = session.get("repository_before", {})
        changes = compare_snapshots(before_snapshot, current_snapshot)
        snapshot_available = True
    else:
        before_git = {}
        changes = {"added": [], "modified": [], "deleted": []}
        snapshot_available = False
    integrity_violation = has_changes(changes)
    snapshot_errors = (
        (before_snapshot.get("errors", []) if snapshot_available else []) + current_snapshot.get("errors", [])
    )
    overall = requirements_verdict
    integrity_reason = None
    if not snapshot_available:
        integrity_reason = "Initialization snapshot is missing; verification integrity cannot be established."
        if overall == "PASS":
            overall = "UNKNOWN"
    elif integrity_violation:
        integrity_reason = "Non-.verification paths changed after verification initialization."
        if overall == "PASS":
            overall = "UNKNOWN"
    elif snapshot_errors:
        integrity_reason = "One or more project files could not be hashed; verification integrity is incomplete."
        if overall == "PASS":
            overall = "UNKNOWN"
    if invalid_evidence and overall == "PASS":
        overall = "UNKNOWN"
    validate_verdict(overall)
    counts = Counter(item["verdict"] for item in assessed)
    return {
        "version": "0",
        "generated_at": utc_now(),
        "goal": plan["goal"],
        "overall_verdict": overall,
        "requirements_verdict": requirements_verdict,
        "counts": {verdict: counts.get(verdict, 0) for verdict in ("PASS", "FAIL", "PARTIAL", "UNKNOWN")},
        "requirements": assessed,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "unverified_risks": [item["reason"] for item in assessed if item["verdict"] in {"PARTIAL", "UNKNOWN"}],
        "integrity": {
            "snapshot_available": snapshot_available,
            "violation": integrity_violation,
            "reason": integrity_reason,
            "non_verification_changes": changes,
            "repository_before": before_git,
            "repository_after": current_git,
            "snapshot_errors_before": before_snapshot.get("errors", []) if snapshot_available else [],
            "snapshot_errors_after": current_snapshot.get("errors", []),
        },
        "orphaned_evidence": orphaned,
        "invalid_evidence": invalid_evidence,
        "scope_notice": "Verdicts apply only to requirements evaluated under this verification plan.",
    }


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Verification Report",
        "",
        "## Overall Verdict",
        "",
        f"**{report['overall_verdict']}**",
        "",
        (
            f"Requirements: {report['counts']['PASS']} PASS · {report['counts']['FAIL']} FAIL · "
            f"{report['counts']['PARTIAL']} PARTIAL · {report['counts']['UNKNOWN']} UNKNOWN"
        ),
        "",
        "## Goal",
        "",
        report["goal"],
        "",
        "## Summary",
        "",
        "| Requirement | Priority | Verdict | Evidence |",
        "|---|---|---|---|",
    ]
    for requirement in report["requirements"]:
        evidence = ", ".join(requirement["evidence"]) or "—"
        lines.append(
            f"| {_escape_cell(requirement['id'])} | {requirement['priority']} | "
            f"{requirement['verdict']} | {evidence} |"
        )
    for requirement in report["requirements"]:
        lines.extend(
            [
                "",
                f"## {requirement['id']} — {requirement['verdict']}",
                "",
                f"Requirement: {requirement['text']}",
                "",
                f"Reason: {requirement['reason']}",
                "",
                "Verification obligations:",
                "",
            ]
        )
        for obligation in requirement["obligations"]:
            refs = ", ".join(obligation["evidence"]) or "no evidence"
            mandatory = "mandatory" if obligation["mandatory"] else "optional"
            lines.append(
                f"- {obligation['id']} `{obligation['type']}` ({mandatory}): "
                f"{obligation['state']} — {refs}. {obligation['description']}"
            )
        lines.extend(["", "Evidence:", ""])
        matching_ids = {item for obligation in requirement["obligations"] for item in obligation["evidence"]}
        for item in report["evidence"]:
            if item["id"] not in matching_ids:
                continue
            if item.get("command"):
                observation = f"exit_code={item['exit_code']}, duration={item['duration_seconds']}s, status={item['status']}"
                paths = f"stdout=`{item['stdout_path']}`, stderr=`{item['stderr_path']}`"
                lines.append(
                    f"- **{item['id']}** {item['assessment']}: `{item['command']}`; {observation}; {paths}. "
                    f"{item['assessment_reason']}"
                )
                if item.get("measurement"):
                    measurement = item["measurement"]
                    lines.append(
                        "  - Performance: "
                        f"threshold={measurement.get('threshold')}; observed={measurement.get('observed_value')}; "
                        f"method={measurement.get('measurement_method')}; runs={measurement.get('number_of_runs')}."
                    )
                if item.get("baseline"):
                    lines.append(f"  - Baseline: {item['baseline']}")
            else:
                lines.append(
                    f"- **{item['id']}** {item['assessment']}: {item.get('description', item['assessment_reason'])} "
                    f"(source: `{item.get('source_path') or item['source']}`)."
                )
        if not matching_ids:
            lines.append("- No evidence captured.")

    lines.extend(["", "## Unverified Risks", ""])
    if report["unverified_risks"]:
        lines.extend(f"- {risk}" for risk in report["unverified_risks"])
    else:
        lines.append("- None identified within the declared plan.")

    integrity = report["integrity"]
    lines.extend(["", "## Verification Integrity", ""])
    if not integrity["snapshot_available"]:
        lines.append("**UNKNOWN:** initialization snapshot missing.")
    elif integrity["violation"]:
        lines.append("**INTEGRITY WARNING:** non-`.verification/` paths changed during verification.")
    elif integrity["snapshot_errors_before"] or integrity["snapshot_errors_after"]:
        lines.append("**INTEGRITY UNKNOWN:** one or more project files could not be hashed.")
    else:
        lines.append("No non-`.verification/` changes were detected after initialization.")
    for kind in ("added", "modified", "deleted"):
        paths = integrity["non_verification_changes"][kind]
        if paths:
            lines.append(f"- {kind.title()}: {', '.join(f'`{path}`' for path in paths)}")
    if report["invalid_evidence"]:
        lines.extend(["", "Invalid evidence links were excluded:", ""])
        lines.extend(f"- {item['id']}: {item['reason']}" for item in report["invalid_evidence"])

    before = integrity["repository_before"]
    after = integrity["repository_after"]
    lines.extend(
        [
            "",
            "## Environment / Reproduction",
            "",
            "Commands, working directories, timestamps, duration, environment, and stdout/stderr paths are stored in each evidence JSON.",
            "",
            "## Repository State",
            "",
            f"- Before commit: `{before.get('commit') or 'unavailable'}`",
            f"- Before dirty: `{before.get('dirty')}`",
            f"- After commit: `{after.get('commit') or 'unavailable'}`",
            f"- After dirty: `{after.get('dirty')}`",
            "",
            f"> {report['scope_notice']}",
            "",
        ]
    )
    return "\n".join(lines)


def generate_reports(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    report = build_report(root, plan)
    directory = verification_path(root)
    write_json(directory / "report.json", report)
    (directory / "report.md").write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return report


# Public imports now resolve to the artifact-schema-v1 report implementation.
from .report_v1 import *  # noqa: E402,F401,F403
