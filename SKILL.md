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
5. **Write the v1 plan.** Run `verify init --goal "..."`, then complete `.verification/plan.json` and `.verification/repo_profile.json`. Every executable obligation must declare exact `experiment.argv`, relative `cwd`, source, artifact paths, and one typed oracle. STATIC obligations must declare their source path and optional line range.
6. **Design missing acceptance experiments before sealing.** Prefer official existing tests. Derive any missing black-box assertions from requirement text and create generated tests only under `.verification/generated/`. Declare every generated test as an experiment artifact. Never modify production files, existing tests, expected output, thresholds, baselines, or CI to build an oracle.
7. **Review and seal.** Inspect the exact argv, oracle, baseline, and artifact list, then run `verify seal`. Review `.verification/seal-summary.md`. Do not edit the plan, profile, baseline, or generated tests after sealing; start a new verification if the approved plan must change.
8. **Execute every sealed experiment through the evidence CLI.** Run `verify run --requirement ... --obligation ...` without supplying an ad-hoc command or result. The runtime executes only sealed argv, evaluates the typed oracle, records raw stdout/stderr, observes filesystem events, and binds the evidence to the seal. A failed, unstartable, unmonitorable, or integrity-invalid experiment must remain visible.
9. **Assess sufficiency.** Read the saved stdout/stderr and metadata. Evidence existence is not evidence sufficiency. Static evidence alone cannot prove behavior that can be executed. Comments, README claims, test existence, and exit code without a suitable oracle are not runtime proof.
10. **Generate verdicts.** Run `verify report`. Accept only `PASS`, `FAIL`, `PARTIAL`, and `UNKNOWN`. PASS requires all mandatory obligations supported, direct verification of key behavior, no valid contradiction, and evidence IDs. FAIL requires a concrete contradictory evidence ID. Use PARTIAL for some support with mandatory gaps, and UNKNOWN when evidence or a reliable oracle is absent.
11. **Review both reports and integrity.** Inspect `.verification/report.json` and `.verification/report.md`. Confirm `status` is `SEALED`, payload digests and the evidence ledger validate, and every command has stdout/stderr and filesystem-event artifacts. Protected-file events are integrity failures even if content was restored. New untracked build outputs may be reported without invalidating evidence.
12. **Return a concise result.** State the overall verdict, each requirement verdict and evidence IDs, the principal unknowns or integrity warnings, and the report path. Claim only the requirements evaluated under this plan, never repository-wide correctness.

## Non-negotiable rules

- Never trust implementation comments as proof.
- Never trust README claims as runtime proof.
- Never treat test existence as test success.
- Never treat exit code alone as requirement proof unless the requirement-derived oracle is exactly command success.
- Never supply or substitute a command, baseline, threshold, or measurement after sealing.
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

# Complete plan/profile and any .verification/generated tests first.
verify seal

verify run \
  --requirement R1 \
  --obligation R1-O1

verify record \
  --requirement R2 \
  --obligation R2-O1 \
  --description "Observed repository fact" \
  --assessment SUPPORTS

verify report
verify status
```

Use only the four v1 oracle kinds: `exit_code`, `stdout_json`, `differential`, and `performance`. Differential baselines and performance thresholds belong in the plan before sealing. Performance observations and run counts must come from the sealed command's stdout JSON; never invent a missing baseline or benchmark result.
