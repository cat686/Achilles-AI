---
name: achilles-ai
description: Independently verify whether a code repository satisfies a stated natural-language goal by creating evidence obligations, executing real experiments through the Achilles-AI CLI, and reporting traceable PASS, FAIL, PARTIAL, or UNKNOWN verdicts. Use when asked to verify that an implementation or coding-agent task is actually complete; do not use as a code-generation or automatic-repair workflow.
---

# Achilles-AI

Verify only the declared goal. Reason about intent and evidence sufficiency, but make every factual execution claim traceable to artifacts captured by `verify` under `.verification/`.

## Workflow

Follow this order without announcing completion before the report exists.

1. **Understand the goal.** Preserve the user's exact scope, explicit constraints, and acceptance language. Do not add product requirements.
2. **Decompose requirements.** Create atomic, decidable requirements with unique `R...` IDs, `text`, exact `source_text`, `priority` (`MUST`, `SHOULD`, or `MAY`), `notes`, and obligations. Explicit user requirements default to `MUST`.
3. **Discover repository verification interfaces.** Inspect repository-wide entry documents and manifests first, then goal-relevant paths. Find build, test, run, and benchmark commands from README/CONTRIBUTING, package or build manifests, CI, Makefiles, scripts, tests, examples, and container files. Record the exact source of every discovered command in `.verification/repo_profile.json`; never label a guessed command as discovered.
4. **Create evidence obligations.** Give each obligation a unique `R...-O...` ID, one supported type, `mandatory`, a factual description, and a planned experiment. Prefer executable behavior over static inspection. Use `DIFFERENTIAL` only with an identified trustworthy baseline. Use `PERFORMANCE` only with a defensible method and threshold. Use `HUMAN` or `UNKNOWN` when no reliable machine oracle exists.
5. **Write the plan.** Run `verify init --goal "..."` to capture initial state and create the workspace, then write the complete requirements to `.verification/plan.json` and discovery data to `.verification/repo_profile.json`. Finish and validate the plan before experiments; `verify run` and `verify record` enforce its requirement/obligation/type links.
6. **Execute existing build/test infrastructure.** Use the repository's official commands before generating acceptance tests. Do not run a favorable subset while hiding relevant failures. Capture each command with `verify run`.
7. **Design missing acceptance experiments.** Derive black-box assertions from requirement text, not implementation logic. Create generated tests only under `.verification/generated/`. If verification requires changing production files, existing tests, fixtures, expected output, thresholds, baseline data, or CI, stop that experiment and leave the obligation insufficient.
8. **Execute every experiment through the evidence CLI.** Use argument-vector execution after `--`; do not substitute an uncaptured shell run for factual evidence. Supply `--expect-exit-code` only when command success/failure is a valid oracle for the obligation. Without an explicit oracle, let the evidence remain `INCONCLUSIVE`. A failed or unstartable command must remain visible in evidence.
9. **Assess sufficiency.** Read the saved stdout/stderr and metadata. Evidence existence is not evidence sufficiency. Static evidence alone cannot prove behavior that can be executed. Comments, README claims, test existence, and exit code without a suitable oracle are not runtime proof.
10. **Generate verdicts.** Run `verify report`. Accept only `PASS`, `FAIL`, `PARTIAL`, and `UNKNOWN`. PASS requires all mandatory obligations supported, direct verification of key behavior, no valid contradiction, and evidence IDs. FAIL requires a concrete contradictory evidence ID. Use PARTIAL for some support with mandatory gaps, and UNKNOWN when evidence or a reliable oracle is absent.
11. **Review both reports and integrity.** Inspect `.verification/report.json` and `.verification/report.md`. Confirm stdout/stderr files exist for every command. Treat any reported non-`.verification/` change as an integrity failure; do not hide, revert, or explain it away to manufacture PASS. Report unrelated test failures separately.
12. **Return a concise result.** State the overall verdict, each requirement verdict and evidence IDs, the principal unknowns or integrity warnings, and the report path. Claim only the requirements evaluated under this plan, never repository-wide correctness.

## Non-negotiable rules

- Never trust implementation comments as proof.
- Never trust README claims as runtime proof.
- Never treat test existence as test success.
- Never treat exit code alone as requirement proof unless the requirement-derived oracle is exactly command success.
- Prefer behavior verification over implementation inspection and existing project tests over generated tests.
- Never modify production source or existing tests during verification.
- Never modify expected values, skip failures, lower thresholds, alter baselines, or hide failing commands.
- Every PASS must cite supporting evidence IDs; every FAIL must cite contradictory evidence IDs.
- When reliable verification is impossible, return UNKNOWN.
- Keep generated acceptance tests within `.verification/generated/` and all other verification writes within `.verification/`.

## CLI patterns

Run from the repository root after installing Achilles-AI. Put a global `--root` before the subcommand when verifying another directory.

```bash
verify init --goal "<exact user goal>"

verify run \
  --requirement R1 \
  --obligation R1-O1 \
  --type TEST \
  --source existing_test \
  --expect-exit-code 0 \
  -- <command> <arg> ...

verify record \
  --requirement R2 \
  --obligation R2-O1 \
  --type STATIC \
  --source README.md \
  --line 10-20 \
  --description "Observed repository fact" \
  --assessment SUPPORTS

verify report
verify status
```

For `DIFFERENTIAL`, record the legitimate baseline with `--baseline`. For `PERFORMANCE`, pass `--measurement` pointing to a JSON object containing `threshold`, `observed_value`, `measurement_method`, and `number_of_runs`. Do not invent a missing baseline or benchmark.
