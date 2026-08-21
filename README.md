# Achilles-AI

[中文](#中文) | [English](#english)

## 中文

Achilles-AI 是一个面向 AI Coding Agent 的最小独立验收层。它将自然语言目标拆解为原子需求和证据义务，从真实命令与仓库文件中捕获可观察事实，并生成可追踪的 `PASS`、`FAIL`、`PARTIAL` 或 `UNKNOWN` 结论。

项目由两个部分组成：

- [SKILL.md](SKILL.md) 是智能层，负责理解目标、发现仓库的验证入口、拆解需求和设计实验；
- Python CLI 是精简、确定性的证据运行时，负责执行命令、保存 stdout/stderr 和运行事实、约束证据关联、评估义务覆盖情况并生成报告。


### Achilles-AI 不是什么

Achilles-AI 不是 Coding Agent、通用代码审查器、形式化验证系统，也不保证软件没有任何缺陷。Version 0 不包含 Web UI、数据库、云端执行、语言 adapter、LLM API、自动修复循环或插件框架。

`PASS` 仅表示：在当前 verification plan 声明的需求范围内，已经收集到充分证据。它不表示软件在所有场景下都绝对正确。

### 环境与安装

- Python 3.11 或更高版本；
- Git 可选。在 Git worktree 中会捕获 commit、dirty state 和 porcelain status；在非 Git 目录中，这些字段会明确记录为 unavailable，而不会猜测。

本地安装：

```bash
python -m pip install -e .
verify --help
```

开发时也可以不安装：设置 `PYTHONPATH=src`，并以 `python -m goal_verifier` 代替 `verify`。

### 核心流程

1. 使用 `SKILL.md` 将目标拆成原子需求和 evidence obligations；
2. 从 README、manifest、CI 和脚本中发现 build/test/run/benchmark 命令，并记录准确来源；
3. 初始化验证工作区，在运行实验前完成 verification plan；
4. 优先执行项目已有测试，必要时再设计 requirement-derived acceptance experiments；
5. Generated tests 只能写入 `.verification/generated/`；
6. 生成并检查 JSON 与 Markdown 报告。

全局 `--root` 参数必须放在子命令之前。在待验证仓库中运行：

```bash
verify init --goal "CLI --json 输出合法 JSON"
```

生成的目录结构为：

```text
.verification/
├── plan.json
├── repo_profile.json
├── session.json
├── evidence/
├── generated/
├── tmp/
├── report.json
└── report.md
```

未传入 requirements 文件时，`init` 会创建一个 requirements 为空的合法 plan。Agent 应在执行任何实验前补全 `.verification/plan.json` 和 `.verification/repo_profile.json`。也可以直接提供结构化文件：

```bash
verify init \
  --goal "CLI --json 输出合法 JSON" \
  --requirements requirements.json \
  --profile repo_profile.json
```

Requirement 示例：

```json
{
  "id": "R1",
  "text": "使用 --json 时输出合法 JSON",
  "source_text": "新增 --json 输出",
  "priority": "MUST",
  "notes": "",
  "obligations": [
    {
      "id": "R1-O1",
      "type": "RUNTIME",
      "mandatory": true,
      "description": "执行 CLI 并将 stdout 解析为 JSON",
      "planned_experiment": "运行黑盒 acceptance script"
    }
  ]
}
```

支持的 obligation types：`STATIC`、`BUILD`、`TEST`、`RUNTIME`、`DIFFERENTIAL`、`PERFORMANCE`、`HUMAN`、`UNKNOWN`。优先级包括 `MUST`、`SHOULD`、`MAY`。

### 捕获可执行证据

```bash
verify run \
  --requirement R1 \
  --obligation R1-O1 \
  --type TEST \
  --source existing_test \
  --expect-exit-code 0 \
  -- python -B -m unittest discover -s tests -v
```

命令以 argument vector 直接启动，不经过 shell。无论命令成功还是失败，CLI 都会保存参数、工作目录、开始/结束时间、duration、exit code、stdout、stderr、环境摘要和 Git 状态。无法启动的命令会记录为 inconclusive evidence，而不会丢失。

退出码为零本身不是需求成立的证据。未提供 `--expect-exit-code` 时，证据会保持 `INCONCLUSIVE`。只有当命令本身是有效的 requirement-derived oracle 时，才应声明预期退出码。

`DIFFERENTIAL` evidence 还必须通过 `--baseline` 标明可信基线；`PERFORMANCE` evidence 必须通过 `--measurement` 提供 JSON，其中包含 `threshold`、`observed_value`、`measurement_method` 和 `number_of_runs`。

### 捕获静态证据

```bash
verify record \
  --requirement R2 \
  --obligation R2-O1 \
  --type STATIC \
  --source README.md \
  --line 20-28 \
  --description "README 记录了 --json 参数" \
  --assessment SUPPORTS
```

静态证据会记录文件 SHA-256。`HUMAN` 和 `UNKNOWN` evidence 不允许标记为 `SUPPORTS`，从而避免在缺少可靠机器 oracle 时制造自动 PASS。

### 生成和检查结论

```bash
verify report
verify status
```

只有 supporting evidence 才能满足 obligation。存在明确反证时 requirement 为 `FAIL`；部分义务得到支持但 mandatory obligations 仍有缺口时为 `PARTIAL`；证据不足时为 `UNKNOWN`；所有 mandatory obligations 均被支持且不存在反证时为 `PASS`。每个 PASS 和 FAIL 都必须引用 evidence IDs。

Overall verdict 依据 MUST requirements，而不是多数投票：优先级依次为 `FAIL`、`PARTIAL`、`UNKNOWN`、`PASS`。SHOULD/MAY 的结果会出现在报告中，但不会直接导致整体 FAIL。

### 完整性模型

Verification 阶段对项目文件默认只读。CLI 自身只写入 `.verification/**`。`init` 会记录初始 Git 状态，并为所有非 `.git`、非 `.verification` 文件计算哈希；`report` 会重复检查。任何新增、修改或删除的非 `.verification/` 路径都会在报告中显著标记。

如果需求证据原本足以 PASS，但初始化快照缺失或项目路径发生变化，overall verdict 会降为 `UNKNOWN`，而不是输出不安全的 PASS。验证过程中不得修改 production code、existing tests、expected output、threshold、baseline 或 CI；如果必须修改项目才能构造 oracle，应输出 UNKNOWN 并说明原因。

### Demo

`examples/` 包含三种结果：

- `pass_cli`：输出合法 JSON，产生 PASS；
- `fail_cli`：包含故意设置的单引号 JSON bug，真实测试失败并产生 FAIL；
- `unknown_cli`：视觉质量属于 HUMAN obligation，缺少可靠机器 oracle，因此产生 UNKNOWN。

安装后运行；开发模式下可先设置 `PYTHONPATH=src`：

```bash
python -B examples/run_demos.py
```

Runner 会将 fixture 复制到临时目录，完整执行 goal → plan → evidence → report 流程，校验预期 verdict，并输出报告路径。

### 测试

测试套件仅使用 Python 标准库：

```bash
python -B -m unittest discover -s tests -v
```

测试覆盖 schema 拒绝逻辑、command capture、命令启动失败、stdout/stderr 持久化、exit code、duration、Git state、静态文件哈希、obligation 关联、四种 verdict 规则、CLI 流程和仓库完整性检测。

---

## English

Achilles-AI is a minimal independent acceptance-testing layer for AI coding agents. It turns natural-language goals into atomic requirements and evidence obligations, captures observable facts from real commands and repository files, and produces traceable `PASS`, `FAIL`, `PARTIAL`, or `UNKNOWN` verdicts.

The project has two parts:

- [SKILL.md](SKILL.md) is the intelligence layer responsible for understanding goals, discovering repository verification interfaces, decomposing requirements, and designing experiments.
- The Python CLI is a thin deterministic evidence runtime responsible for executing commands, persisting stdout/stderr and runtime facts, enforcing evidence links, assessing obligation coverage, and rendering reports.


### What Achilles-AI is not

Achilles-AI is not a coding agent, a general code reviewer, a formal-verification system, or a guarantee of bug-free software. Version 0 has no web UI, database, cloud runner, language adapters, LLM API, automatic repair loop, or plugin framework.

`PASS` means sufficient evidence was collected for the declared requirements under the current verification plan. It does **not** mean the software is universally correct.

### Requirements and installation

- Python 3.11 or newer.
- Git is optional. In a Git worktree, commit, dirty state, and porcelain status are captured. Outside Git, those fields are explicitly recorded as unavailable rather than guessed.

Install locally:

```bash
python -m pip install -e .
verify --help
```

For development without installation, set `PYTHONPATH=src` and use `python -m goal_verifier` in place of `verify`.

### Core workflow

1. Use `SKILL.md` to turn the goal into atomic requirements and evidence obligations.
2. Discover build/test/run/benchmark commands from repository documentation, manifests, CI, and scripts; record their exact sources.
3. Initialize the verification workspace and complete the verification plan before executing experiments.
4. Run existing project tests first, then design requirement-derived acceptance experiments if needed.
5. Write generated tests only under `.verification/generated/`.
6. Generate and inspect the JSON and Markdown reports.

The global `--root` option must appear before the subcommand. From the repository being verified:

```bash
verify init --goal "CLI --json emits valid JSON"
```

This creates:

```text
.verification/
├── plan.json
├── repo_profile.json
├── session.json
├── evidence/
├── generated/
├── tmp/
├── report.json
└── report.md
```

Without a requirements file, `init` creates a valid plan with an empty requirements array. The agent must complete `.verification/plan.json` and `.verification/repo_profile.json` before running experiments. Structured files can also be supplied directly:

```bash
verify init \
  --goal "CLI --json emits valid JSON" \
  --requirements requirements.json \
  --profile repo_profile.json
```

A requirement has this shape:

```json
{
  "id": "R1",
  "text": "Using --json emits valid JSON",
  "source_text": "Add --json output",
  "priority": "MUST",
  "notes": "",
  "obligations": [
    {
      "id": "R1-O1",
      "type": "RUNTIME",
      "mandatory": true,
      "description": "Execute the CLI and parse stdout as JSON",
      "planned_experiment": "Run a black-box acceptance script"
    }
  ]
}
```

Supported obligation types are `STATIC`, `BUILD`, `TEST`, `RUNTIME`, `DIFFERENTIAL`, `PERFORMANCE`, `HUMAN`, and `UNKNOWN`. Priorities are `MUST`, `SHOULD`, and `MAY`.

### Capture executable evidence

```bash
verify run \
  --requirement R1 \
  --obligation R1-O1 \
  --type TEST \
  --source existing_test \
  --expect-exit-code 0 \
  -- python -B -m unittest discover -s tests -v
```

The command is launched as an argument vector without a shell. Its arguments, working directory, timestamps, duration, exit code, stdout, stderr, environment summary, and Git state are persisted whether it succeeds or fails. A command that cannot start is recorded as inconclusive evidence rather than lost.

Exit code zero alone is not proof. Without `--expect-exit-code`, evidence remains `INCONCLUSIVE`. Supply an expected exit code only when the command itself is a valid requirement-derived oracle.

`DIFFERENTIAL` evidence also requires `--baseline` to identify a trustworthy baseline. `PERFORMANCE` evidence requires `--measurement` pointing to JSON with `threshold`, `observed_value`, `measurement_method`, and `number_of_runs`.

### Capture static evidence

```bash
verify record \
  --requirement R2 \
  --obligation R2-O1 \
  --type STATIC \
  --source README.md \
  --line 20-28 \
  --description "README documents --json" \
  --assessment SUPPORTS
```

Static records include a SHA-256 file hash. `HUMAN` and `UNKNOWN` evidence cannot be marked `SUPPORTS`, preventing an automatic PASS where no reliable machine oracle exists.

### Generate and inspect verdicts

```bash
verify report
verify status
```

Only supporting evidence satisfies an obligation. Concrete contradictory evidence makes a requirement `FAIL`; partial support with mandatory gaps produces `PARTIAL`; insufficient evidence produces `UNKNOWN`; and support for all mandatory obligations with no contradiction produces `PASS`. Every PASS and FAIL cites evidence IDs.

Overall verdicts follow MUST requirements, not majority vote: `FAIL` takes precedence, then `PARTIAL`, then `UNKNOWN`, otherwise `PASS`. SHOULD/MAY results remain visible but do not directly fail the overall verdict.

### Integrity model

Verification is read-only for project files by default. The CLI itself writes only `.verification/**`. `init` records the initial Git state and hashes every non-`.git`, non-`.verification` file; `report` repeats both checks. Added, modified, or deleted paths outside `.verification/` are shown prominently.

If requirement evidence would otherwise pass but the initialization snapshot is missing or project paths changed, the overall result becomes `UNKNOWN` rather than an unsafe PASS. Do not alter production code, existing tests, expected output, thresholds, baselines, or CI during verification. If an acceptance oracle requires changing the project, report UNKNOWN and explain why.

### Demos

The fixtures under `examples/` cover three outcomes:

- `pass_cli`: valid JSON behavior, producing PASS.
- `fail_cli`: an intentional single-quote JSON bug, producing FAIL from a real test failure.
- `unknown_cli`: a visual-quality HUMAN obligation with no reliable machine oracle, producing UNKNOWN.

After installation, or with `PYTHONPATH=src` in development:

```bash
python -B examples/run_demos.py
```

The runner copies each fixture to a temporary directory, performs the complete goal → plan → evidence → report flow, checks the expected verdict, and prints each report path.

### Tests

The test suite uses only the Python standard library:

```bash
python -B -m unittest discover -s tests -v
```

It covers schema rejection, command capture, command-launch failure, stdout/stderr persistence, exit codes, durations, Git state, static hashing, obligation association, all verdict rules, CLI flows, and repository-integrity detection.
