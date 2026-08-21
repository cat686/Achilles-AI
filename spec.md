# Achilles-AI Version 0 — Codex Implementation Spec

## 0. 任务定义

实现一个面向 AI Coding Agent 的最小可用 **Goal Verification / Independent Acceptance Testing** 原型。

该项目不负责生成代码、不负责规划开发任务，也不负责替代 Coding Agent。

它只解决一个问题：

> 当 Coding Agent 声称“任务已经完成”时，如何根据用户最初的自然语言目标，对当前代码仓库进行系统化验证，并输出可审计的 PASS / FAIL / PARTIAL / UNKNOWN 结论。

Version 0 的核心链路：

```text
Natural-language Goal
        ↓
Atomic Requirements
        ↓
Evidence Obligations
        ↓
Repository Discovery
        ↓
Verification Experiments
        ↓
Captured Evidence
        ↓
PASS / FAIL / PARTIAL / UNKNOWN
```

核心原则：

> Agent may reason. Evidence must be observable.

也就是说：

* Codex 可以负责理解目标；
* Codex 可以负责拆 requirements；
* Codex 可以负责发现项目如何 build/test/run；
* Codex 可以负责设计 acceptance test；
* Codex 可以负责决定应该运行什么实验；

但：

* command 是否真正执行；
* exit code；
* stdout；
* stderr；
* runtime；
* git state；
* benchmark result；

必须由确定性 evidence capture 工具记录。

最终 PASS 不能仅仅依据 Codex 的自然语言判断。

---

# 1. Version 0 产品定位

产品名称暂定：

```text
Achilles-AI
```

定位：

```text
Independent Acceptance Testing for Coding Agents
```

核心抽象：

```text
Goal
→ Verifiable Claims
→ Evidence Obligations
→ Experiments
→ Evidence
→ Verdict
```

Version 0 的主要使用方式：

```text
用户
 ↓
Codex
 ↓
Achilles-AI Skill
 ↓
Evidence Capture CLI
 ↓
.verification/
```

暂时不实现：

* 独立 LLM 服务；
* Web UI；
* IDE 插件；
* 云端 sandbox；
* Docker orchestration platform；
* GitHub App；
* CI SaaS；
* 自己的 coding agent；
* Python/C++/Rust language adapters；
* AST framework；
* 全自动 benchmark framework；
* distributed verifier；
* cryptographic attestation；
* production-grade security sandbox。

V0 的目标是验证：

> 一个高质量 Verification Skill + 极薄 evidence runtime，是否已经能够显著提高 Coding Agent 对“任务是否真正完成”的判断可靠性。

---

# 2. 最重要的设计原则

整个实现必须遵守以下原则。

## 2.1 Evidence First

优先级：

```text
Executable Evidence
>
Static Evidence
>
LLM Reasoning
```

如果 requirement 可以通过真实执行验证，则不能只因为阅读代码“看起来正确”就判 PASS。

例如：

```text
Requirement:
CLI --json 输出合法 JSON
```

错误方式：

```text
代码中存在 --json 分支
→ PASS
```

正确方式：

```text
代码中存在 --json 分支
+
真实执行 CLI
+
stdout 可以被 JSON parser 解析
→ PASS
```

---

## 2.2 PASS 必须有证据

禁止出现：

```text
PASS
Reason: implementation looks correct
```

PASS 至少必须引用一个 evidence ID。

例如：

```text
R3 PASS

Evidence:
E07
E08
```

---

## 2.3 UNKNOWN 是合法结果

当系统无法获得足够 evidence 时：

```text
UNKNOWN
```

而不是猜测 PASS。

宁可：

```text
UNKNOWN
```

也不能产生：

```text
False PASS
```

V0 的最高优先级指标：

```text
minimize False PASS
```

---

# 3. Verdict 定义

仅允许以下四种 requirement verdict：

```text
PASS
FAIL
PARTIAL
UNKNOWN
```

不得自行增加：

```text
SUCCESS
WARNING
BLOCKED
LIKELY_PASS
```

等其他最终状态。

---

## 3.1 PASS

满足：

1. 所有 mandatory evidence obligations 均得到满足；
2. 没有有效 contradictory evidence；
3. evidence 实际支持该 requirement；
4. requirement 的关键行为已经被直接验证。

---

## 3.2 FAIL

存在明确反例。

例如：

```text
required build succeeds
but build exit code = 1
```

或者：

```text
expected HTTP status = 200
observed HTTP status = 500
```

或者：

```text
performance requirement <= 100 ms
measured median = 143 ms
```

FAIL 必须引用 contradiction evidence。

---

## 3.3 PARTIAL

Requirement 有多个可验证组成部分：

```text
R5:
支持 JSON 输出并保持旧接口兼容
```

如果：

```text
JSON 输出验证成功
compatibility 尚未验证
```

则：

```text
PARTIAL
```

---

## 3.4 UNKNOWN

以下情况使用 UNKNOWN：

* 无法执行；
* 缺少环境；
* requirement 本身不可客观验证；
* 缺少 baseline；
* 缺少 credentials；
* 无法确认正确输出；
* 需要人工视觉判断；
* 无法可靠构造 oracle；
* evidence 不足。

---

# 4. Evidence Obligation 类型

V0 支持以下 verification types：

```text
STATIC
BUILD
TEST
RUNTIME
DIFFERENTIAL
PERFORMANCE
HUMAN
UNKNOWN
```

这些不是 Requirement Type。

一个 requirement 可以包含多个 evidence obligations。

例如：

```json
{
  "id": "R3",
  "text": "新增 --json 参数并保持原有 CLI 行为不变",
  "obligations": [
    {
      "type": "STATIC",
      "mandatory": false
    },
    {
      "type": "RUNTIME",
      "mandatory": true
    },
    {
      "type": "DIFFERENTIAL",
      "mandatory": true
    }
  ]
}
```

---

# 5. 各 Verification Type 定义

## STATIC

不执行目标程序，仅检查 repository 内容。

适用于：

* 文件存在；
* configuration 存在；
* API symbol 存在；
* dependency 声明；
* feature flag；
* source implementation；
* route registration；
* manifest 配置。

STATIC 默认属于较弱 evidence。

如果行为可以运行验证：

```text
STATIC 不应单独导致 PASS。
```

---

## BUILD

真实执行项目 build / compile / package 流程。

例如：

```text
npm run build
cargo build
cmake --build ...
make
python -m build
```

必须通过 evidence capture CLI 执行。

---

## TEST

执行 repository 已存在的 test。

优先使用项目官方测试方式。

例如：

```text
pytest
ctest
cargo test
npm test
go test ./...
```

不要根据语言硬编码逻辑。

Codex 应通过 repository discovery 判断正确命令。

---

## RUNTIME

真实运行目标功能。

例如：

```text
CLI invocation
HTTP request
program execution
library API call
generated black-box acceptance test
```

RUNTIME 是 V0 最重要的 verification type。

---

## DIFFERENTIAL

将当前实现与 baseline/reference 进行比较。

例如：

```text
old vs new
CPU vs GPU
reference implementation vs optimized implementation
golden output vs current output
```

只有存在合理 baseline 时使用。

不得虚构 baseline。

---

## PERFORMANCE

测量：

```text
latency
throughput
memory
execution time
benchmark metric
```

V0 不需要完整 benchmark framework。

允许使用 repository 已有 benchmark。

若 Codex 自己设计 benchmark：

* 明确 warmup；
* 明确 repetitions；
* 记录原始结果；
* 记录统计指标；
* 不得只选择最好的一次。

---

## HUMAN

机器不能可靠判断。

例如：

```text
UI 是否美观
文章文风是否合适
动画视觉质量
```

这些 requirement 不得由系统强行 PASS。

---

## UNKNOWN

当前无法设计可靠 verification oracle。

---

# 6. Requirement 拆解规则

输入 goal 后，Codex 首先拆分 atomic requirements。

Requirement 必须：

* 尽量单一；
* 可判断；
* 可验证；
* 避免把多个独立目标塞在一起。

错误：

```text
R1:
实现登录功能、提高性能并完善文档
```

正确：

```text
R1:
用户可以成功登录

R2:
错误密码不能登录

R3:
登录 API P95 < 200 ms

R4:
README 包含登录 API 使用说明
```

---

每个 requirement 至少包含：

```json
{
  "id": "R1",
  "text": "...",
  "source_text": "...",
  "priority": "MUST",
  "obligations": [],
  "notes": ""
}
```

priority V0 支持：

```text
MUST
SHOULD
MAY
```

用户明确要求的功能默认：

```text
MUST
```

---

# 7. Repository Discovery

Codex 不应首先阅读所有 source code。

执行：

```text
repository-wide discovery
+
requirement-scoped inspection
```

首先寻找：

```text
README
CONTRIBUTING
package/build manifests
Makefile
CI config
test directories
benchmark directories
scripts
examples
entrypoints
existing docs
container config
```

目标是回答：

```text
How does this project build?
How does this project test?
How does this project run?
How does this project benchmark?
What are the relevant components for this goal?
```

---

Codex 在 `.verification/repo_profile.json` 写入：

```json
{
  "build_commands": [],
  "test_commands": [],
  "run_commands": [],
  "benchmark_commands": [],
  "relevant_paths": [],
  "discovered_from": [],
  "notes": []
}
```

不得把猜测的 command 当成 discovered command。

如果命令来自 README：

记录：

```text
source = README.md
```

如果来自 CI：

记录具体文件。

---

# 8. Verification Plan

生成：

```text
.verification/plan.json
```

格式：

```json
{
  "version": "0",
  "goal": "...",
  "created_at": "...",
  "repository": {
    "root": "...",
    "git_commit": "...",
    "worktree_dirty": true
  },
  "requirements": [
    {
      "id": "R1",
      "text": "...",
      "source_text": "...",
      "priority": "MUST",
      "obligations": [
        {
          "id": "R1-O1",
          "type": "RUNTIME",
          "mandatory": true,
          "description": "...",
          "planned_experiment": "..."
        }
      ]
    }
  ]
}
```

在实际执行 verification 前，必须生成 plan。

---

# 9. Evidence Capture Runtime

实现一个确定性 CLI。

建议名称：

```text
verify
```

V0 可以使用 Python 3.11+ 实现。

优先：

```text
Python standard library
```

不要引入大型 framework。

---

## 9.1 Command

至少实现：

```bash
verify run
```

示例：

```bash
verify run \
  --requirement R2 \
  --obligation R2-O1 \
  --type TEST \
  -- pytest tests/test_cli.py
```

CLI 必须实际启动 subprocess。

---

## 9.2 每次执行必须记录

```text
evidence_id
requirement_id
obligation_id
verification_type
command
cwd
started_at
finished_at
duration_seconds
exit_code
stdout
stderr
git_commit
git_dirty
environment summary
```

stdout/stderr 不能只保存在 LLM context。

必须写入文件。

---

# 10. Evidence Storage

目录：

```text
.verification/
├── plan.json
├── repo_profile.json
├── evidence/
│   ├── E0001.json
│   ├── E0001.stdout.txt
│   ├── E0001.stderr.txt
│   ├── E0002.json
│   ├── E0002.stdout.txt
│   └── E0002.stderr.txt
├── generated/
├── tmp/
├── report.json
└── report.md
```

---

单个 evidence JSON：

```json
{
  "id": "E0001",
  "requirement_id": "R1",
  "obligation_id": "R1-O1",
  "type": "TEST",
  "source": "existing_test",
  "command": "pytest tests/test_cli.py",
  "cwd": "...",
  "started_at": "...",
  "finished_at": "...",
  "duration_seconds": 2.14,
  "exit_code": 0,
  "stdout_path": "evidence/E0001.stdout.txt",
  "stderr_path": "evidence/E0001.stderr.txt",
  "git_commit": "...",
  "git_dirty": true,
  "status": "EXECUTED"
}
```

注意：

```text
exit_code == 0
```

并不自动意味着 requirement PASS。

它只代表：

```text
command execution succeeded
```

Codex 必须判断这个 experiment 是否真正支持 requirement。

---

# 11. Generated Acceptance Tests

允许 Codex 自动生成 acceptance tests。

但必须满足：

Generated tests 只能创建在：

```text
.verification/generated/
```

不得：

* 修改已有 tests；
* 删除已有 tests；
* 修改 expected outputs；
* skip failing tests；
* 改 CI config；
* 修改 production source。

如果必须修改项目才能验证：

停止并输出：

```text
UNKNOWN
```

以及原因。

---

Generated acceptance test 应尽可能：

```text
black-box
behavior-oriented
requirement-derived
```

而不是：

```text
implementation-derived
```

例如：

Requirement：

```text
--json 输出合法 JSON
```

优先：

```text
运行 executable
解析 stdout
```

而不是：

```text
检查 source 中是否调用 json.dumps()
```

---

# 12. Anti-Self-Cheating Rules

Verification 阶段默认：

```text
READ-ONLY PROJECT MODE
```

允许写入：

```text
.verification/**
```

默认不允许修改其他路径。

开始前记录：

```bash
git status --porcelain
git rev-parse HEAD
```

结束后再次记录。

如果 verification 过程中出现非 `.verification/` 文件变化：

必须在 report 中显著标记。

不得通过以下行为制造 PASS：

```text
修改已有 tests
修改 expected values
删除 failing tests
skip tests
降低 threshold
修改 baseline
修改 benchmark input
只运行 test 子集而隐瞒其他 failures
```

---

# 13. Static Evidence

不是所有 evidence 都需要 command。

允许 CLI 提供：

```bash
verify record
```

例如：

```bash
verify record \
  --requirement R4 \
  --obligation R4-O1 \
  --type STATIC \
  --source README.md \
  --description "README documents --json option"
```

对应 evidence 应记录：

```text
file path
line/range if known
description
```

如果实现方便，可加入 file hash。

---

# 14. Evidence Sufficiency

Codex 必须区分：

```text
Evidence exists
```

和：

```text
Evidence is sufficient
```

例如：

Requirement：

```text
program does not crash on malformed JSON
```

Evidence：

```text
source code contains try/except
```

只能证明：

```text
STATIC evidence exists
```

不能证明 requirement。

因此：

```text
RUNTIME mandatory obligation remains unsatisfied
```

最终：

```text
PARTIAL
```

或者：

```text
UNKNOWN
```

而不能 PASS。

---

# 15. Final Report

Verification 完成后必须生成：

```text
.verification/report.json
.verification/report.md
```

Markdown 首屏应该直接告诉用户：

```text
Overall Verdict

PASS / FAIL / PARTIAL / UNKNOWN
```

然后：

```text
Requirements:
X PASS
X FAIL
X PARTIAL
X UNKNOWN
```

---

推荐格式：

```markdown
# Verification Report

## Goal

...

## Overall Verdict

PARTIAL

## Summary

| Requirement | Verdict | Evidence |
|-------------|---------|----------|
| R1 | PASS | E001, E002 |
| R2 | FAIL | E003 |
| R3 | UNKNOWN | — |

## R1

Requirement:

...

Verification obligations:

- STATIC
- RUNTIME

Evidence:

- E001 ...
- E002 ...

Verdict:

PASS

Reason:

...

## R2

...

## Unverified Risks

...

## Environment / Reproduction

...

## Repository State

Commit:
...

Dirty:
...
```

---

# 16. Overall Verdict 规则

Overall Verdict 不通过简单 majority vote 产生。

规则：

如果任何：

```text
MUST requirement == FAIL
```

则：

```text
Overall = FAIL
```

否则，如果任何：

```text
MUST requirement == PARTIAL
```

则：

```text
Overall = PARTIAL
```

否则，如果任何：

```text
MUST requirement == UNKNOWN
```

则：

```text
Overall = UNKNOWN
```

否则：

```text
Overall = PASS
```

SHOULD / MAY requirement 不直接导致整体 FAIL。

但必须在报告中列出。

---

# 17. Verification Skill

实现：

```text
SKILL.md
```

Skill 是 V0 的核心 intelligence layer。

Skill 必须告诉 Codex：

当用户要求：

```text
verify this project
verify whether the task is actually complete
check whether this repository satisfies this goal
```

时按照固定流程执行。

---

## Verification Skill Workflow

严格顺序：

```text
STEP 1
Understand Goal

STEP 2
Decompose Requirements

STEP 3
Discover Repository Verification Interfaces

STEP 4
Create Evidence Obligations

STEP 5
Write plan.json

STEP 6
Execute Existing Build/Test Infrastructure

STEP 7
Design Missing Acceptance Experiments

STEP 8
Execute Experiments Through Evidence CLI

STEP 9
Assess Evidence Sufficiency

STEP 10
Generate Verdicts

STEP 11
Generate report.json + report.md

STEP 12
Return concise result to user
```

Codex 不得跳过 plan 直接宣布：

```text
everything looks good
```

---

# 18. Agent Behavior Rules

Skill 中加入以下强制规则。

### Rule 1

Never trust implementation comments as proof.

### Rule 2

Never trust README claims as runtime proof.

### Rule 3

Never treat test existence as test success.

### Rule 4

Never treat command exit code alone as proof of a requirement unless the requirement is exactly command success.

### Rule 5

Prefer behavior verification over implementation inspection.

### Rule 6

Prefer existing project tests before generating new tests.

### Rule 7

Generated tests must come from requirements, not from copying implementation logic.

### Rule 8

Do not modify production source during verification.

### Rule 9

Do not modify existing tests during verification.

### Rule 10

If reliable verification is impossible, return UNKNOWN.

### Rule 11

Every PASS must reference evidence IDs.

### Rule 12

Every FAIL must reference contradictory evidence.

### Rule 13

Do not hide failing commands.

### Rule 14

A test failure unrelated to the requested goal should still be reported separately.

### Rule 15

Do not claim repository-wide correctness.

Only claim:

```text
requirements evaluated under this verification plan
```

---

# 19. CLI Implementation

建议结构：

```text
achilles-ai/
├── README.md
├── SKILL.md
├── pyproject.toml
├── src/
│   └── goal_verifier/
│       ├── __init__.py
│       ├── cli.py
│       ├── capture.py
│       ├── evidence.py
│       ├── git_state.py
│       ├── schema.py
│       └── report.py
└── tests/
    ├── test_capture.py
    ├── test_schema.py
    ├── test_git_state.py
    └── test_report.py
```

保持实现简单。

不要提前实现：

```text
plugin architecture
adapter registry
database
server
RPC
LLM provider abstraction
workflow engine
distributed queue
```

---

# 20. CLI 最小命令

必须至少支持：

```bash
verify init
verify run
verify record
verify status
```

---

## verify init

创建：

```text
.verification/
```

记录：

```text
timestamp
git commit
git dirty status
```

---

## verify run

执行 command 并 capture evidence。

---

## verify record

记录 static/manual evidence。

---

## verify status

展示：

```text
current goal
requirements
evidence count
current verdict state
```

无需漂亮 UI。

---

# 21. Shell Command Capture

subprocess 执行必须：

* capture stdout；
* capture stderr；
* preserve exit code；
* measure elapsed time；
* 不经过 shell，除非必要；
* 正确处理 command arguments；
* 尽量支持 Ctrl-C；
* 不因为 command failure 导致整个 verifier 崩溃。

例如：

```bash
verify run --type TEST -- pytest -q
```

pytest 返回 1：

应：

```text
Evidence E0004 recorded
exit_code = 1
```

而不是 verifier 自己异常退出导致 evidence 丢失。

---

# 22. Performance Evidence

V0 只支持简单模式。

例如：

```bash
verify run \
  --requirement R5 \
  --obligation R5-O1 \
  --type PERFORMANCE \
  -- ./benchmark
```

Codex 自己负责解释 stdout。

如果 performance requirement 是：

```text
latency < 100 ms
```

报告必须包含：

```text
threshold
observed value
measurement method
number of runs if known
```

如果没有可靠 benchmark：

```text
UNKNOWN
```

---

# 23. Differential Verification

只有以下 baseline 可以使用：

* repository 中已有 reference implementation；
* user explicitly supplied baseline；
* existing golden files；
* stable previous version clearly identifiable；
* CPU/reference implementation；
* officially documented expected output。

不能因为存在：

```text
git HEAD~1
```

就自动认为它是正确 baseline。

---

# 24. V0 示例

用户输入：

```text
Goal:
给 CLI 新增 --json 参数。
使用 --json 时输出合法 JSON。
默认输出行为必须保持不变。
```

拆解：

```text
R1 CLI exposes --json
R2 --json returns valid JSON
R3 default CLI output remains compatible
```

Plan：

```text
R1
STATIC + RUNTIME

R2
RUNTIME

R3
DIFFERENTIAL
```

Experiments：

```text
E001
inspect --help

E002
run CLI --json

E003
parse stdout as JSON

E004
run default CLI

E005
compare with known baseline
```

最终：

```text
R1 PASS
R2 PASS
R3 UNKNOWN
```

如果不存在可信 baseline。

Overall：

```text
UNKNOWN
```

这比凭猜测：

```text
PASS
```

更正确。

---

# 25. Codex 输出给用户的最终信息

不要把大量内部推理 dump 给用户。

最终回复保持类似：

```text
Verification: PARTIAL

3 requirements evaluated:
- R1 PASS — CLI option exists and executes successfully.
- R2 PASS — generated output was parsed as valid JSON.
- R3 UNKNOWN — no reliable baseline was available to prove backward compatibility.

Evidence and full report:
.verification/report.md
```

详细信息存在 report。

---

# 26. README

README 需要解释：

## What Achilles-AI Is

```text
Achilles-AI checks whether a repository satisfies a natural-language goal by turning requirements into executable evidence.
```

## What Achilles-AI Is Not

```text
It is not:
- a coding agent
- a code reviewer
- a formal verification system
- a guarantee of bug-free software
```

强调：

```text
PASS means:
sufficient evidence was collected for the declared requirements under the current verification plan.

PASS does NOT mean:
the software is universally correct.
```

---

# 27. Testing Achilles-AI 自身

至少实现 unit tests：

### capture

验证：

```text
stdout correctly stored
stderr correctly stored
exit code correctly stored
duration recorded
failed command still creates evidence
```

### git state

验证：

```text
commit captured
dirty state captured
```

### schema

验证：

```text
valid evidence accepted
invalid verification type rejected
invalid verdict rejected
```

### report

验证：

```text
MUST FAIL → overall FAIL
MUST PARTIAL → overall PARTIAL
MUST UNKNOWN → overall UNKNOWN
all MUST PASS → overall PASS
```

---

# 28. Demo Fixtures

创建：

```text
examples/
```

至少包含一个极小 demo repository 或 fixture。

例如：

```text
examples/simple_cli/
```

提供一个 intentional bug。

然后展示：

```text
Goal
↓
Verification
↓
FAIL
```

目的是证明系统能够找到真实失败，而不是只展示 PASS。

最好同时具有：

```text
PASS case
FAIL case
UNKNOWN case
```

---

# 29. Version 0 非目标

Codex 如果发现这些方向，不要扩展。

明确禁止 scope creep：

```text
Do not build a web frontend.

Do not build authentication.

Do not build a database.

Do not implement cloud execution.

Do not implement Docker management.

Do not implement GitHub integration.

Do not implement language-specific adapters.

Do not implement generic AST analysis.

Do not implement an LLM API client.

Do not implement automatic code repair.

Do not implement autonomous development loops.

Do not build a planner.

Do not build a code generator.

Do not implement plugin marketplaces.

Do not optimize prematurely.
```

---

# 30. Definition of Done

Version 0 只有满足以下条件才算完成。

## Functional

* [ ] 存在完整 `SKILL.md`
* [ ] 可以将 goal 拆成 structured requirements
* [ ] 可以生成 `plan.json`
* [ ] 可以创建 `.verification/`
* [ ] 可以通过 CLI 执行真实 command
* [ ] stdout 被保存
* [ ] stderr 被保存
* [ ] exit code 被保存
* [ ] duration 被保存
* [ ] git commit 被保存
* [ ] evidence 可以关联 requirement
* [ ] 支持 STATIC evidence
* [ ] 支持 executable evidence
* [ ] 能生成 report.json
* [ ] 能生成 report.md
* [ ] Verdict 仅包含 PASS/FAIL/PARTIAL/UNKNOWN
* [ ] 每个 PASS 引用 evidence
* [ ] 每个 FAIL 引用 evidence
* [ ] 能正确产生 UNKNOWN

## Safety / Integrity

* [ ] Verification 默认不修改 source
* [ ] Verification 默认不修改 existing tests
* [ ] Generated tests 仅进入 `.verification/generated/`
* [ ] Command failure 不会丢失 evidence
* [ ] Verification 前后记录 git state
* [ ] 非 `.verification` 修改被检测并报告

## Engineering

* [ ] CLI 有 unit tests
* [ ] core schema 有 unit tests
* [ ] report verdict logic 有 unit tests
* [ ] README 可以让新用户理解项目
* [ ] 至少一个 PASS demo
* [ ] 至少一个 FAIL demo
* [ ] 至少一个 UNKNOWN demo

---

# 31. Codex 实现策略

按以下阶段实现，不要同时铺开。

## Phase A — Skeleton

创建：

```text
package
CLI
schema
.verification layout
tests
```

---

## Phase B — Evidence Capture

优先确保：

```text
command
→ subprocess
→ stdout/stderr
→ evidence JSON
```

可靠工作。

这是 V0 最重要的确定性组件。

---

## Phase C — Report

实现：

```text
requirements
+
obligations
+
evidence
→ verdict
```

先保持规则简单。

---

## Phase D — Skill

最后编写高质量：

```text
SKILL.md
```

让 Codex 自己承担：

```text
goal understanding
repo discovery
requirement decomposition
experiment design
evidence interpretation
```

不要把这些能力重复实现成 Python heuristic。

---

## Phase E — Demo

建立三个最小案例：

```text
PASS
FAIL
UNKNOWN
```

并实际完整运行一次：

```text
Goal
→ plan
→ evidence
→ report
```

---

# 32. 最核心的架构边界

Version 0 必须保持：

```text
┌──────────────────────────┐
│        Codex Agent       │
│                          │
│ Goal understanding       │
│ Requirement generation   │
│ Repo discovery           │
│ Experiment design        │
│ Evidence interpretation  │
└─────────────┬────────────┘
              │
              │ commands
              ▼
┌──────────────────────────┐
│ Evidence Capture Runtime │
│                          │
│ subprocess execution     │
│ stdout / stderr          │
│ exit code                │
│ runtime                  │
│ git state                │
│ evidence persistence     │
└─────────────┬────────────┘
              │
              ▼
       .verification/
              │
              ▼
┌──────────────────────────┐
│     Verdict / Report     │
│                          │
│ PASS                     │
│ FAIL                     │
│ PARTIAL                  │
│ UNKNOWN                  │
└──────────────────────────┘
```

原则：

```text
Reasoning belongs to the Agent.

Facts belong to the runtime.

Verdicts must trace back to facts.
```

---

# 33. Version 0 核心研究问题

实现过程中始终记住：

Version 0 不是为了证明：

```text
we can build another testing tool
```

而是为了回答：

> 当 Coding Agent 完成真实软件开发任务后，一个通用 Verification Skill 加上最薄的确定性 evidence runtime，是否足以显著降低 False PASS，并减少程序员重新人工检查整个项目的需求？

因此任何与这个问题无关的复杂系统设计，都不应该进入 Version 0。

---

# 34. 最终产品哲学

Achilles-AI 不应该回答：

```text
Do I think the code is correct?
```

它应该回答：

```text
What exactly did we need to prove?

What experiments were performed?

What did those experiments observe?

Which requirements are supported by sufficient evidence?

Which requirements failed?

Which requirements remain unknown?
```

最终价值不来自：

```text
another AI opinion
```

而来自：

```text
auditable evidence
+
explicit uncertainty
+
traceable verdicts
```

这就是 Version 0 的全部目标。
