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
3. 初始化验证工作区，完成包含精确 argv、artifact 和 typed oracle 的 verification plan；
4. 如需 generated acceptance test，先写入 `.verification/generated/`；
5. 运行 `verify seal` 冻结 plan、profile、baseline、测试脚本和受保护仓库状态；
6. 运行封存实验，生成并检查 JSON 与 Markdown 报告。

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
├── seal.json
├── seal-summary.md
├── ledger.json
├── evidence/
├── generated/
├── tmp/
├── report.json
└── report.md
```

未传入 requirements 文件时，`init` 会创建一个 requirements 为空的合法 plan。Agent 应补全 `.verification/plan.json`、`.verification/repo_profile.json` 和 generated tests，然后执行 `verify seal`。也可以直接提供结构化文件：

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
      "planned_experiment": "执行封存的 CLI 命令并解析 stdout",
      "experiment": {
        "argv": ["python", "-B", "app.py", "--json"],
        "cwd": ".",
        "source": "project_command",
        "artifacts": ["app.py"]
      },
      "oracle": {
        "kind": "stdout_json",
        "expected_exit_code": 0
      }
    }
  ]
}
```

支持的 obligation types：`STATIC`、`BUILD`、`TEST`、`RUNTIME`、`DIFFERENTIAL`、`PERFORMANCE`、`HUMAN`、`UNKNOWN`。优先级包括 `MUST`、`SHOULD`、`MAY`。

### 捕获可执行证据

```bash
verify seal
verify run \
  --requirement R1 \
  --obligation R1-O1
```

`run` 不接受临时命令、baseline 或 measurement；它只执行 seal 中的 argv，并由 runtime 计算 assessment。CLI 保存命令、工作目录、时间、exit code、原始 stdout/stderr、文件事件、摘要、快照和 Git 状态。无法启动或无法监控的命令会记录为 inconclusive evidence。

Artifact schema v1 支持四类 oracle：`exit_code`、`stdout_json`、`differential` 和 `performance`。差分 baseline 在 seal 时计算 SHA-256；性能数据必须由命令通过 stdout JSON 输出，runtime 按 JSON Pointer、operator、threshold 和 minimum runs 判断，不能在运行后手工声明结果。

### 捕获静态证据

```bash
verify record \
  --requirement R2 \
  --obligation R2-O1 \
  --description "README 记录了 --json 参数" \
  --assessment SUPPORTS
```

STATIC 的 source path 和 line range 必须在 plan 中预先声明并封存。静态证据记录文件 SHA-256；`HUMAN` 和 `UNKNOWN` evidence 不允许标记为 `SUPPORTS`。

### 生成和检查结论

```bash
verify report
verify status
```

只有 supporting evidence 才能满足 obligation。存在明确反证时 requirement 为 `FAIL`；部分义务得到支持但 mandatory obligations 仍有缺口时为 `PARTIAL`；证据不足时为 `UNKNOWN`；所有 mandatory obligations 均被支持且不存在反证时为 `PASS`。每个 PASS 和 FAIL 都必须引用 evidence IDs。

Overall verdict 依据 MUST requirements，而不是多数投票：优先级依次为 `FAIL`、`PARTIAL`、`UNKNOWN`、`PASS`。SHOULD/MAY 的结果会出现在报告中，但不会直接导致整体 FAIL。

### 完整性模型

每次实验前后都会计算快照，并在命令运行期间使用原生文件事件监控。Git 仓库保护所有 tracked 文件、封存 artifact 与 `.verification/**`；非 Git 仓库保护 seal 时已存在的文件。受保护文件即使修改后恢复也会使该 evidence 变为 `INCONCLUSIVE`。未跟踪构建产物允许生成，但会列入报告。

Plan、profile、baseline、generated test、stdout、stderr、事件日志和 evidence JSON 都绑定 SHA-256；`ledger.json` 维护 evidence 哈希链。任何漂移都会让 `status` 显示 `STALE`，并阻止旧 PASS。旧 artifact schema v0 只允许审计展示，整体 verdict 强制为 `UNKNOWN`。

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

测试套件使用 `unittest`，并通过 `watchdog` 验证跨平台文件事件：

```bash
python -B -m unittest discover -s tests -v
```

测试覆盖 seal 漂移、四类 oracle、command capture、瞬时文件修改、构建产物、payload/ledger 篡改、legacy 降级、CLI 流程和 verdict 规则。

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
3. Initialize the workspace and complete a plan containing exact argv, artifacts, and typed oracles.
4. Create any generated acceptance tests under `.verification/generated/` before approval.
5. Run `verify seal` to freeze the plan, profile, baselines, tests, and protected repository state.
6. Execute sealed experiments, then inspect the JSON and Markdown reports.

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
├── seal.json
├── seal-summary.md
├── ledger.json
├── evidence/
├── generated/
├── tmp/
├── report.json
└── report.md
```

Without a requirements file, `init` creates a valid plan with an empty requirements array. Complete the plan, profile, and generated tests, then run `verify seal`. Structured files can also be supplied directly:

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
      "planned_experiment": "Execute the sealed CLI and parse stdout",
      "experiment": {
        "argv": ["python", "-B", "app.py", "--json"],
        "cwd": ".",
        "source": "project_command",
        "artifacts": ["app.py"]
      },
      "oracle": {
        "kind": "stdout_json",
        "expected_exit_code": 0
      }
    }
  ]
}
```

Supported obligation types are `STATIC`, `BUILD`, `TEST`, `RUNTIME`, `DIFFERENTIAL`, `PERFORMANCE`, `HUMAN`, and `UNKNOWN`. Priorities are `MUST`, `SHOULD`, and `MAY`.

### Capture executable evidence

```bash
verify seal
verify run \
  --requirement R1 \
  --obligation R1-O1
```

`run` accepts no ad-hoc command, baseline, or measurement. It executes only the sealed argv, and the runtime computes the assessment. Command metadata, raw stdout/stderr, filesystem events, digests, snapshots, and Git state are persisted. An unstartable or unmonitorable command remains inconclusive.

Artifact schema v1 supports `exit_code`, `stdout_json`, `differential`, and `performance` oracles. Differential baselines are hashed at seal time. Performance measurements must come from stdout JSON and are evaluated by the runtime using JSON pointers, an operator, threshold, and minimum run count.

### Capture static evidence

```bash
verify record \
  --requirement R2 \
  --obligation R2-O1 \
  --description "README documents --json" \
  --assessment SUPPORTS
```

STATIC source paths and line ranges are declared in the plan before sealing. Static records include a SHA-256 file hash. `HUMAN` and `UNKNOWN` evidence cannot be marked `SUPPORTS`.

### Generate and inspect verdicts

```bash
verify report
verify status
```

Only supporting evidence satisfies an obligation. Concrete contradictory evidence makes a requirement `FAIL`; partial support with mandatory gaps produces `PARTIAL`; insufficient evidence produces `UNKNOWN`; and support for all mandatory obligations with no contradiction produces `PASS`. Every PASS and FAIL cites evidence IDs.

Overall verdicts follow MUST requirements, not majority vote: `FAIL` takes precedence, then `PARTIAL`, then `UNKNOWN`, otherwise `PASS`. SHOULD/MAY results remain visible but do not directly fail the overall verdict.

### Integrity model

Every experiment takes before/after snapshots and uses native filesystem events while the child process runs. Git repositories protect tracked files, sealed artifacts, and `.verification/**`; non-Git repositories protect every file that existed at seal time. A protected file modified and then restored still makes the evidence inconclusive. New untracked build outputs are allowed but reported.

Plan, profile, baseline, generated test, stdout, stderr, event-log, and evidence digests are bound through `seal.json` and the evidence hash chain in `ledger.json`. Drift makes `status` report `STALE` and prevents an old PASS. Artifact schema v0 remains readable for audit, but its overall verdict is forced to `UNKNOWN`.

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

The test suite uses `unittest` and `watchdog` for cross-platform filesystem events:

```bash
python -B -m unittest discover -s tests -v
```

It covers seal drift, all four oracle kinds, command capture, transient source changes, generated build output, payload/ledger tampering, legacy downgrade, CLI flows, and verdict aggregation.
