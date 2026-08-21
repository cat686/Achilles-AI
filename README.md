# Achilles-AI

> **Don't ask whether the coding agent is done. Ask for evidence.**

**Achilles-AI is a goal-driven verification layer for AI Coding Agents.**

It turns a natural-language goal into executable verification, captures real evidence, and produces a traceable:

```text
PASS / FAIL / PARTIAL / UNKNOWN
```

[中文](#中文) · [English](#english)

---

# 中文

## AI 会写代码，但它真的完成了吗？

Coding Agent 已经可以修改代码、运行测试、修复错误，然后告诉你：

> **“Done. All tests pass.”**

但：

```text
Tests Passed ≠ Goal Satisfied
```

已有测试可能没有覆盖新需求，Agent 可能只检查了 happy path，也可能没有真正验证兼容性、性能或运行时行为。

**Achilles-AI 解决的是 AI Coding 的最后一公里：如何验证 Agent 的“完成”声明。**

---

## Achilles-AI 是什么？

Achilles-AI 是一个面向 AI Coding Agent 的：

> **目标驱动验收层（Goal-Driven Acceptance Layer）**

输入一个自然语言目标：

```text
新增 --json 参数。

开启后输出必须是合法 JSON。

不开启时原有 CLI 行为不能变化。
```

Achilles-AI 将其转换为：

```text
Natural-language Goal
        ↓
Atomic Requirements
        ↓
Verification Experiments
        ↓
Real Execution
        ↓
Auditable Evidence
        ↓
PASS / FAIL / PARTIAL / UNKNOWN
```

核心不是：

> 再让一个 AI 看一遍代码，然后说“看起来没问题”。

而是：

> **明确需要证明什么，真正执行实验，并让最终结论能够追溯到证据。**

---

## 为什么需要 Achilles-AI？

### 1. 验证 Goal，而不只是 Tests

传统 CI 回答：

```text
预先写好的测试通过了吗？
```

Achilles-AI 回答：

```text
当前代码真的满足用户刚刚提出的目标吗？
```

例如：

```text
Goal:
新增 --json 参数，同时保持原有 CLI 行为兼容。
```

可能被拆成：

```text
R1  --json 参数存在
    → STATIC + RUNTIME

R2  --json 输出可以被 JSON parser 解析
    → RUNTIME

R3  默认行为与原版本保持兼容
    → DIFFERENTIAL + TEST
```

即使原有 tests 全部通过，如果没有证据支持 `R3`，也不应该直接宣布任务完成。

---

### 2. 从 Agent Claim 到 Executable Evidence

普通 Coding Agent：

```text
Write Code
    ↓
Run Some Tests
    ↓
"PASS"
```

Achilles-AI：

```text
Goal
 ↓
Requirements
 ↓
Verification Plan
 ↓
Real Commands
 ↓
stdout / stderr / exit code / timing / repo state
 ↓
Evidence
 ↓
Verdict
```

最终你得到的不是：

```text
"The agent says it works."
```

而是：

```text
R3 PASS
  ↳ R3-O1 supported by E0006
  ↳ R3-O2 supported by E0007
```

---

### 3. 拒绝 False PASS

Achilles-AI 使用四种结果：

| Verdict   | 含义             |
| --------- | -------------- |
| `PASS`    | 当前必要验证义务已有充分证据 |
| `FAIL`    | 存在明确失败或反例      |
| `PARTIAL` | 只有部分必要义务得到验证   |
| `UNKNOWN` | 当前证据不足，无法可靠判断  |

对于验证系统来说：

> **UNKNOWN 比 False PASS 更好。**

如果环境缺失、没有可靠 baseline、无法构造 verification oracle，Achilles-AI 会保留不确定性，而不是猜一个 `PASS`。

---

## 适合什么场景？

Achilles-AI 尤其适合具有明确 **observable behavior** 的 Coding Agent 任务。

### CLI / API

```text
新增 --json 参数，并保证输出合法。
```

```text
新增 /health endpoint，必须返回 HTTP 200。
```

### Compatibility

```text
修改实现后，原有 CLI output 不能发生变化。
```

### Numerical Computing

```text
GPU implementation 与 CPU reference 平均误差 < 1%。
```

### Performance

```text
P95 latency < 100 ms。
```

```text
新实现吞吐量不能低于 baseline。
```

### Build / Runtime / Filesystem

```text
项目必须能够成功编译。
```

```text
命令执行后必须生成指定目录结构。
```

---

## Quick Start

### 1. 安装

需要：

* Python 3.11+
* Git

作为 Codex Skill 安装：

```bash
git clone https://github.com/cat686/Achilles-AI.git ~/.codex/skills/achilles-ai
python -m pip install -e ~/.codex/skills/achilles-ai

verify --help
```

安装后重新开启一个 Codex 对话，使 `$achilles-ai` 生效。

---

### 2. 在你的项目中使用

进入需要验证的代码仓库：

```bash
cd your-project
```

然后在 Codex 中直接描述你的目标：

```text
使用 $achilles-ai 验证：

目标：
新增 --json 参数；
开启后输出必须是合法 JSON；
不开启时原有 CLI 行为必须保持不变。
```

Achilles-AI 会自动：

```text
Understand Goal
      ↓
Inspect Repository
      ↓
Generate Requirements
      ↓
Design Verification Experiments
      ↓
Execute Real Commands
      ↓
Capture Evidence
      ↓
Produce Verdict
```

---

### 3. 查看结果

```bash
verify status
```

完整报告：

```text
.verification/report.md
```

主要验证产物：

```text
.verification/
├── plan.json
├── seal-summary.md
├── evidence/
├── report.json
└── report.md
```

通常只需要查看：

```text
verify status
.verification/report.md
```

---

## 运行官方示例

仓库提供 Click 和 Cookiecutter 的真实项目验证案例。

安装 `uv`：

```bash
python -m pip install uv
```

准备参考项目：

```bash
python examples/setup_reference_projects.py
```

验证 Click：

```bash
cd examples/click
```

在 Codex 中输入：

```text
使用 $achilles-ai 验证：

目标：在 Python 3.12 环境下，使用 uv.lock 锁定的依赖运行
Click 的完整官方测试体系，并判断当前项目是否满足该目标。
```

然后查看：

```bash
verify status
```

---

## Achilles-AI 在哪里？

```text
User Goal
    ↓
Coding Agent
    ↓
Implementation
    ↓
Achilles-AI
    ↓
Evidence-backed Acceptance
```

Coding Agent 解决：

> **How do I implement this?**

Achilles-AI 解决：

> **How do I know it was actually implemented?**

你也可以把它理解成：

> **Intent-Driven CI for AI Coding Agents.**

---

## 当前边界

Achilles-AI 当前不是：

* Coding Agent
* 自动修复工具
* Security Sandbox
* Formal Verifier
* 完整 CI 平台

它只专注于一件事：

> **在 Agent 说“Done”和任务真正被接受之间，建立一个基于证据的验证层。**

`PASS` 也不意味着软件在所有输入和环境下都绝对正确。

它只表示：

> **当前声明的 requirements，在当前 verification plan 和环境下，已经获得足够证据支持。**

---

# English

## AI can write the code. But did it actually finish the job?

Modern coding agents can modify code, run tests, fix failures, and finally report:

> **"Done. All tests pass."**

But:

```text
Tests Passed ≠ Goal Satisfied
```

Existing tests may not cover the new requirement.

Backward compatibility may never be checked.

Performance claims may never be measured.

**Achilles-AI verifies the completion claims made by AI Coding Agents.**

---

## What is Achilles-AI?

Achilles-AI is a:

> **Goal-Driven Acceptance Layer for AI Coding Agents.**

Give it a natural-language goal:

```text
Add a --json option.

Its output must be valid JSON.

Existing default CLI behavior must remain unchanged.
```

Achilles-AI turns it into:

```text
Natural-language Goal
        ↓
Atomic Requirements
        ↓
Verification Experiments
        ↓
Real Execution
        ↓
Auditable Evidence
        ↓
PASS / FAIL / PARTIAL / UNKNOWN
```

The goal is not to ask another LLM to read the code and say:

> "Looks good to me."

The goal is to determine:

> **What needed to be proven, what was actually executed, and what evidence supports the final verdict.**

---

## Why Achilles-AI?

### Verify Goals, Not Just Tests

Traditional CI asks:

```text
Did the predefined tests pass?
```

Achilles-AI asks:

```text
Does the current repository actually satisfy
the goal the user requested?
```

A goal such as:

```text
Add --json while preserving existing CLI behavior.
```

may become:

```text
R1  --json exists
    → STATIC + RUNTIME

R2  --json produces parseable JSON
    → RUNTIME

R3  default behavior remains compatible
    → DIFFERENTIAL + TEST
```

Passing the existing test suite alone is not enough if there is no evidence for `R3`.

---

### From Claims to Evidence

Typical self-verification:

```text
Write Code
    ↓
Run Some Tests
    ↓
"PASS"
```

Achilles-AI:

```text
Goal
 ↓
Requirements
 ↓
Verification Plan
 ↓
Real Commands
 ↓
stdout / stderr / exit code / timing / repo state
 ↓
Evidence
 ↓
Verdict
```

Instead of:

```text
"The agent says it works."
```

you get traceable evidence:

```text
R3 PASS
  ↳ R3-O1 supported by E0006
  ↳ R3-O2 supported by E0007
```

---

### Avoid False PASS

Achilles-AI uses four verdicts:

| Verdict   | Meaning                                                     |
| --------- | ----------------------------------------------------------- |
| `PASS`    | Mandatory verification obligations have sufficient evidence |
| `FAIL`    | Explicit failing or contradictory evidence exists           |
| `PARTIAL` | Only part of the required evidence is available             |
| `UNKNOWN` | Available evidence is insufficient for a reliable decision  |

For a verification system:

> **UNKNOWN is better than False PASS.**

If the environment is unavailable, no trustworthy baseline exists, or no reliable oracle can be constructed, Achilles-AI preserves the uncertainty instead of manufacturing success.

---

## Where is it useful?

Achilles-AI works best for goals with observable behavior.

### CLI / API

```text
Add --json and ensure the output is valid JSON.
```

```text
Add a /health endpoint that returns HTTP 200.
```

### Compatibility

```text
The new implementation must not change existing CLI output.
```

### Numerical Computing

```text
GPU output must stay within 1% average error
of the CPU reference.
```

### Performance

```text
P95 latency must remain below 100 ms.
```

### Build / Runtime / Filesystem

```text
The project must compile successfully.
```

```text
Execution must produce the required directory structure.
```

---

## Quick Start

### 1. Install

Requirements:

* Python 3.11+
* Git

Install as a Codex Skill:

```bash
git clone https://github.com/cat686/Achilles-AI.git ~/.codex/skills/achilles-ai
python -m pip install -e ~/.codex/skills/achilles-ai

verify --help
```

Start a new Codex conversation after installation so `$achilles-ai` becomes available.

---

### 2. Verify a Project

Enter your repository:

```bash
cd your-project
```

Then ask Codex:

```text
Use $achilles-ai to verify:

Goal:
Add a --json option.
Its output must be valid JSON.
Existing default CLI behavior must remain unchanged.
```

Achilles-AI will:

```text
Understand Goal
      ↓
Inspect Repository
      ↓
Generate Requirements
      ↓
Design Verification Experiments
      ↓
Execute Real Commands
      ↓
Capture Evidence
      ↓
Produce Verdict
```

---

### 3. Inspect the Result

```bash
verify status
```

Full report:

```text
.verification/report.md
```

Main artifacts:

```text
.verification/
├── plan.json
├── seal-summary.md
├── evidence/
├── report.json
└── report.md
```

---

## Try the Real-World Examples

Achilles-AI includes reference verification cases for Click and Cookiecutter.

Install `uv`:

```bash
python -m pip install uv
```

Prepare the repositories:

```bash
python examples/setup_reference_projects.py
```

For Click:

```bash
cd examples/click
```

Then ask Codex:

```text
Use $achilles-ai to verify:

Goal: On Python 3.12, run Click's complete official test suite
using the dependencies locked by uv.lock and determine whether
the repository satisfies this goal.
```

Inspect the result:

```bash
verify status
```

---

## Where Achilles-AI Fits

```text
User Goal
    ↓
Coding Agent
    ↓
Implementation
    ↓
Achilles-AI
    ↓
Evidence-backed Acceptance
```

Coding agents answer:

> **How do I implement this?**

Achilles-AI answers:

> **How do I know it was actually implemented?**

A useful mental model is:

> **Intent-Driven CI for AI Coding Agents.**

---

## Scope

Achilles-AI is currently not:

* a Coding Agent;
* an automatic repair system;
* a security sandbox;
* a formal verifier;
* a complete CI platform.

It focuses on one thing:

> **Building an evidence-backed boundary between "the agent says it's done" and "the task is actually accepted."**

A `PASS` does not mean the software is universally correct.

It means:

> **The declared requirements are sufficiently supported under the current verification plan and environment.**
