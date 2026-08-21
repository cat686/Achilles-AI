"""Evidence validation, verdict aggregation, and v1 report rendering."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .capture_v1 import utc_now
from .digest import sha256_file, sha256_json
from .evidence import (
    list_evidence_with_errors,
    load_profile,
    validate_ledger,
    verification_path,
    write_json,
)
from .git_state import capture_file_snapshot, capture_git_state, capture_paths_snapshot, compare_snapshots
from .oracle import evaluate_oracle
from .schema_v1 import CURRENT_VERSION, LEGACY_VERSION, validate_plan, validate_verdict
from .sealing import load_seal, seal_sha256, validate_seal_state


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
    supporting_all: list[str] = []
    contradicting_all: list[str] = []
    inconclusive_all: list[str] = []
    for obligation in requirement["obligations"]:
        matching = [item for item in evidence if item["obligation_id"] == obligation["id"]]
        supporting = [item["id"] for item in matching if item["assessment"] == "SUPPORTS"]
        contradicting = [item["id"] for item in matching if item["assessment"] == "CONTRADICTS"]
        inconclusive = [item["id"] for item in matching if item["assessment"] == "INCONCLUSIVE"]
        state = (
            "CONTRADICTED"
            if contradicting
            else "SATISFIED"
            if supporting
            else "INCONCLUSIVE"
            if inconclusive
            else "MISSING"
        )
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
        supporting_all.extend(supporting)
        contradicting_all.extend(contradicting)
        inconclusive_all.extend(inconclusive)
    mandatory = [item for item in obligation_results if item["mandatory"]]
    if contradicting_all:
        verdict, references = "FAIL", contradicting_all
        reason = "Contradictory evidence provides a concrete counterexample."
    elif mandatory and all(item["state"] == "SATISFIED" for item in mandatory):
        verdict, references = "PASS", supporting_all
        reason = "All mandatory evidence obligations are satisfied with no contradictory evidence."
    elif supporting_all:
        verdict, references = "PARTIAL", supporting_all + inconclusive_all
        missing = [item["id"] for item in mandatory if item["state"] != "SATISFIED"]
        reason = f"Some evidence supports the requirement, but mandatory obligations remain unsatisfied: {', '.join(missing)}."
    else:
        verdict, references = "UNKNOWN", inconclusive_all
        reason = "No sufficient supporting evidence or concrete counterexample is available."
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


def _payload_issues(root: Path, evidence: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    if evidence.get("version") != CURRENT_VERSION or not evidence.get("command"):
        return [], {}
    issues: list[str] = []
    actual: dict[str, str] = {}
    directory = verification_path(root).resolve()
    for path_field, hash_field in (
        ("stdout_path", "stdout_sha256"),
        ("stderr_path", "stderr_sha256"),
        ("fs_events_path", "fs_events_sha256"),
    ):
        relative = evidence.get(path_field)
        try:
            path = (directory / relative).resolve()
            path.relative_to(directory)
        except (TypeError, ValueError):
            issues.append(f"{path_field} escapes the verification directory")
            continue
        if not path.is_file():
            issues.append(f"{relative} is missing")
            continue
        digest = sha256_file(path)
        actual[relative] = digest
        if digest != evidence.get(hash_field):
            issues.append(f"{relative} digest mismatch")
    return issues, actual


def verification_state(
    root: Path, plan: dict[str, Any], profile: dict[str, Any] | None = None
) -> tuple[str, str | None, list[str]]:
    root = root.resolve()
    if plan.get("version") == LEGACY_VERSION:
        return "LEGACY", None, ["artifact schema v0 is unsealed and cannot retain PASS"]
    if not (verification_path(root) / "seal.json").is_file():
        return "UNSEALED", None, []
    profile = profile or load_profile(root)
    seal = load_seal(root)
    issues = validate_seal_state(root, plan, profile, seal)
    current_seal = seal_sha256(root)
    evidence, evidence_errors = list_evidence_with_errors(root)
    issues.extend(item["reason"] for item in evidence_errors)
    valid_ids, ledger_errors, ledger_head = validate_ledger(
        root, session_id=seal["session_id"], seal_sha256=current_seal
    )
    issues.extend(item["reason"] for item in ledger_errors)
    payloads: dict[str, dict[str, str]] = {}
    for item in evidence:
        payload_issues, actual = _payload_issues(root, item)
        issues.extend(f"{item['id']}: {reason}" for reason in payload_issues)
        payloads[item["id"]] = actual
        if item["id"] not in valid_ids:
            issues.append(f"{item['id']}: evidence is not valid in the ledger")
    protected = capture_paths_snapshot(root, seal["protected_paths"])
    input_digest = sha256_json(
        {
            "seal_sha256": current_seal,
            "ledger_head": ledger_head,
            "protected_snapshot": protected,
            "payloads": payloads,
        }
    )
    return ("STALE" if issues else "SEALED"), input_digest, issues


def _legacy_report(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    evidence, errors = list_evidence_with_errors(root, allow_legacy=True)
    assessed = [_assess_requirement(item, evidence) for item in plan["requirements"]]
    return {
        "version": CURRENT_VERSION,
        "legacy_artifact_version": LEGACY_VERSION,
        "generated_at": utc_now(),
        "goal": plan.get("goal", "Legacy verification"),
        "verification_state": "LEGACY",
        "overall_verdict": "UNKNOWN",
        "requirements_verdict": calculate_overall(assessed),
        "counts": {verdict: sum(item["verdict"] == verdict for item in assessed) for verdict in ("PASS", "FAIL", "PARTIAL", "UNKNOWN")},
        "requirements": assessed,
        "evidence_count": len(evidence) + len(errors),
        "evidence": evidence,
        "unverified_risks": ["Legacy artifact schema v0 was not sealed; historical verdicts are untrusted."],
        "integrity": {
            "state": "LEGACY",
            "violation": True,
            "reason": "Artifact schema v0 cannot establish sealed verification integrity.",
            "non_verification_changes": {"added": [], "modified": [], "deleted": []},
            "repository_before": {},
            "repository_after": capture_git_state(root),
        },
        "invalid_evidence": errors,
        "inputs_digest": None,
        "scope_notice": "Legacy evidence is displayed for audit only; the overall verdict is UNKNOWN.",
    }


def build_report(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    validate_plan(plan, allow_legacy=True)
    if plan.get("version") == LEGACY_VERSION:
        return _legacy_report(root, plan)
    profile = load_profile(root)
    state, inputs_digest, state_issues = verification_state(root, plan, profile)
    seal = load_seal(root)
    current_seal = seal_sha256(root)
    evidence, load_errors = list_evidence_with_errors(root)
    valid_ids, ledger_errors, _ = validate_ledger(root, session_id=seal["session_id"], seal_sha256=current_seal)
    invalid_evidence = list(load_errors) + list(ledger_errors)
    known_requirements = {item["id"] for item in plan["requirements"]}
    obligation_owners = {
        obligation["id"]: (requirement["id"], obligation["type"], obligation)
        for requirement in plan["requirements"]
        for obligation in requirement["obligations"]
    }
    usable: list[dict[str, Any]] = []
    for item in evidence:
        reason: str | None = None
        owner = obligation_owners.get(item["obligation_id"])
        payload_issues, _ = _payload_issues(root, item)
        if item["id"] not in valid_ids:
            reason = "Evidence is not valid in the sealed ledger."
        elif item["requirement_id"] not in known_requirements or owner is None:
            reason = "Unknown requirement or obligation link."
        elif owner[0] != item["requirement_id"] or owner[1] != item["type"]:
            reason = "Evidence link or type does not match the sealed plan."
        elif item.get("session_id") != seal["session_id"] or item.get("seal_sha256") != current_seal:
            reason = "Evidence is bound to a different seal."
        elif payload_issues:
            reason = "; ".join(payload_issues)
        else:
            planned_obligation = owner[2]
            expected_artifacts = {
                path: seal["artifact_sha256"][path]
                for path in sorted(
                    set(planned_obligation.get("experiment", {}).get("artifacts", []))
                    | ({planned_obligation["oracle"]["baseline"]} if planned_obligation.get("oracle", {}).get("kind") == "differential" else set())
                    | ({planned_obligation["record"]["source_path"]} if "record" in planned_obligation else set())
                )
            }
            if item.get("artifact_sha256") != expected_artifacts:
                reason = "Evidence artifact digests do not match the sealed obligation."
            elif "experiment" in planned_obligation and (
                item.get("command_args") != planned_obligation["experiment"]["argv"]
                or item.get("source") != planned_obligation["experiment"]["source"]
                or item.get("oracle") != planned_obligation["oracle"]
                or Path(item.get("cwd", "")).resolve()
                != (root / planned_obligation["experiment"]["cwd"]).resolve()
            ):
                reason = "Evidence command or oracle does not match the sealed obligation."
            elif "experiment" in planned_obligation and not item.get("integrity", {}).get("valid", False):
                if item.get("assessment") != "INCONCLUSIVE":
                    reason = "Integrity-invalid command evidence must be INCONCLUSIVE."
            elif (
                "experiment" in planned_obligation
                and item.get("status") == "EXECUTED"
                and item.get("exit_code") is not None
            ):
                stdout_file = verification_path(root) / item["stdout_path"]
                expected_assessment, expected_reason, expected_result = evaluate_oracle(
                    root=root,
                    oracle=planned_obligation["oracle"],
                    exit_code=item["exit_code"],
                    stdout=stdout_file.read_bytes(),
                )
                expected_result["evaluated"] = True
                if (
                    item.get("assessment") != expected_assessment
                    or item.get("assessment_reason") != expected_reason
                    or item.get("oracle_result") != expected_result
                ):
                    reason = "Stored assessment does not match runtime re-evaluation of the sealed oracle."
            elif "experiment" in planned_obligation and item.get("assessment") != "INCONCLUSIVE":
                reason = "Unexecuted command evidence must be INCONCLUSIVE."
            elif "record" in planned_obligation and (
                item.get("source_path") != planned_obligation["record"]["source_path"]
                or item.get("line") != planned_obligation["record"].get("line")
            ):
                reason = "Static evidence source does not match the sealed obligation."
        if reason:
            if not any(entry["id"] == item["id"] for entry in invalid_evidence):
                invalid_evidence.append({"id": item["id"], "reason": reason})
        elif state != "STALE":
            usable.append(item)
    assessed = [_assess_requirement(requirement, usable) for requirement in plan["requirements"]]
    requirements_verdict = calculate_overall(assessed)
    final_state = "STALE" if invalid_evidence and state == "SEALED" else state
    overall = requirements_verdict
    if final_state != "SEALED" and overall == "PASS":
        overall = "UNKNOWN"
    current_snapshot = capture_file_snapshot(root)
    repository_changes = compare_snapshots(seal["repository_snapshot"], current_snapshot)
    protected_current = capture_paths_snapshot(root, seal["protected_paths"])
    protected_violation = sha256_json(protected_current) != seal["protected_snapshot_sha256"]
    counts = Counter(item["verdict"] for item in assessed)
    risks = [item["reason"] for item in assessed if item["verdict"] in {"PARTIAL", "UNKNOWN"}]
    risks.extend(state_issues)
    return {
        "version": CURRENT_VERSION,
        "generated_at": utc_now(),
        "goal": plan["goal"],
        "verification_state": final_state,
        "overall_verdict": overall,
        "requirements_verdict": requirements_verdict,
        "counts": {verdict: counts.get(verdict, 0) for verdict in ("PASS", "FAIL", "PARTIAL", "UNKNOWN")},
        "requirements": assessed,
        "evidence_count": len(evidence) + len(load_errors),
        "evidence": evidence,
        "unverified_risks": list(dict.fromkeys(risks)),
        "integrity": {
            "state": final_state,
            "violation": final_state != "SEALED" or protected_violation,
            "reason": "; ".join(state_issues) if state_issues else None,
            "protected_violation": protected_violation,
            "non_verification_changes": repository_changes,
            "repository_before": seal["git_state"],
            "repository_after": capture_git_state(root),
        },
        "invalid_evidence": invalid_evidence,
        "inputs_digest": inputs_digest,
        "scope_notice": "Verdicts apply only to requirements and sealed oracles in this verification plan.",
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
        f"Verification state: **{report['verification_state']}**",
        "",
        f"Requirements: {report['counts']['PASS']} PASS · {report['counts']['FAIL']} FAIL · "
        f"{report['counts']['PARTIAL']} PARTIAL · {report['counts']['UNKNOWN']} UNKNOWN",
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
        refs = ", ".join(requirement["evidence"]) or "—"
        lines.append(
            f"| {_escape_cell(requirement['id'])} | {requirement['priority']} | {requirement['verdict']} | {refs} |"
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
                f"- {obligation['id']} `{obligation['type']}` ({mandatory}): {obligation['state']} — {refs}. "
                f"{obligation['description']}"
            )
        lines.extend(["", "Evidence:", ""])
        matching_ids = {item for obligation in requirement["obligations"] for item in obligation["evidence"]}
        matching = [item for item in report["evidence"] if item.get("id") in matching_ids]
        if not matching:
            lines.append("- No valid evidence captured.")
        for item in matching:
            if item.get("command"):
                lines.append(
                    f"- **{item['id']}** {item['assessment']}: `{item['command']}`; "
                    f"exit_code={item['exit_code']}, status={item['status']}, "
                    f"integrity={item.get('integrity', {}).get('valid')}. {item['assessment_reason']}"
                )
                lines.append(f"  - Oracle result: `{item.get('oracle_result', {})}`")
            else:
                lines.append(
                    f"- **{item['id']}** {item['assessment']}: {item.get('description', item['assessment_reason'])} "
                    f"(source: `{item.get('source_path') or item['source']}`)."
                )
    lines.extend(["", "## Unverified Risks", ""])
    lines.extend(f"- {risk}" for risk in report["unverified_risks"]) if report["unverified_risks"] else lines.append("- None")
    lines.extend(["", "## Verification Integrity", ""])
    integrity = report["integrity"]
    lines.append(f"State: **{integrity['state']}**")
    if integrity.get("reason"):
        lines.append(f"- {integrity['reason']}")
    changes = integrity["non_verification_changes"]
    for kind in ("added", "modified", "deleted"):
        if changes.get(kind):
            lines.append(f"- {kind.title()}: {', '.join(f'`{path}`' for path in changes[kind])}")
    if report["invalid_evidence"]:
        lines.extend(["", "Invalid evidence:", ""])
        lines.extend(f"- {item['id']}: {item['reason']}" for item in report["invalid_evidence"])
    lines.extend(["", f"> {report['scope_notice']}", ""])
    return "\n".join(lines)


def generate_reports(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    report = build_report(root, plan)
    directory = verification_path(root)
    write_json(directory / "report.json", report)
    (directory / "report.md").write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return report
