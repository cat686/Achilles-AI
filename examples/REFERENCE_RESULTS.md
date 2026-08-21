# Click / Cookiecutter reference verification

测试日期：2026-08-21。环境：Windows 11、CPython 3.12.11、uv 0.12.5。两个项目均为干净的固定上游 commit；依赖通过各自的 `uv.lock` 和 dependency group 准备，未修改生产源码或既有测试。

## Click

- Upstream: `pallets/click@2c8cd3ac958a7eb316d67f2d316c27086c4c0369`
- Sealed command: `uv run --locked --no-default-groups --group dev tox run -e py3.12`
- Oracle: exit code `0`
- Seal SHA-256: `8859119e66150c51e4b726b179bd24f98dae774a09f9bccf02023771f9f5abf1`
- Supporting evidence: `E0002`
- Runtime result: `1907 passed, 108 skipped, 31000 deselected, 1 xfailed`
- Evidence duration: `19.943846s`
- Filesystem observations: 3613 events, 741 new untracked build/test files, 0 protected events, no protected file changes
- Achilles report: `SEALED / PASS`

`E0001` 被保留为 `MONITOR_ERROR / INCONCLUSIVE`：第一次启动 Achilles 时，PATH 误选了不含 `watchdog` 的工具环境。修正启动解释器后，在不改变 sealed argv/oracle 的前提下产生 `E0002`。

### Integrity caveat

`E0002` 执行期间，Windows watchdog observer 后台线程出现 UTF-16 文件名解码异常。该异常打印在父进程控制台，但 `FilesystemMonitor.result()` 仍返回 `monitor_error=null`、`integrity.valid=true`，最终报告没有识别监控器中途失效。

因此 Click 的**功能结论**有上游 pytest 输出和退出码支持，但 Achilles 的**文件事件完整性结论存在已知缺口**。在修复 observer liveness/error propagation 前，不应把该次 PASS 当作无保留的完整性证明。

## Cookiecutter

- Upstream: `cookiecutter/cookiecutter@c88fbe921c97c58b65f1883ba90a0ab53cc91b34`
- Sealed command: `uv run --python=3.12 --isolated --group test -- pytest`
- Oracle: exit code `0`
- Seal SHA-256: `bae3b4bbaf9ded5f7d33a9cc7627b5c821fe6f9e7ef418ddbf184c8b9adf035e`
- Supporting evidence: `E0001`
- Runtime result: `377 passed, 6 skipped`; measured coverage `100%` over 1101 statements
- Evidence duration: `96.425643s`
- Filesystem observations: 659 events, 1 new untracked path, 0 protected events, no protected file changes
- Achilles report: `SEALED / PASS`

pytest 报告了一个无法创建 `.pytest_cache` 的 warning，但测试与 coverage 均成功，且 warning 没有改变验收 oracle。

## Scope

两个 PASS 只回答各自固定 commit 上的官方 Python 3.12 测试入口是否成功，不代表全部平台、全部 Python 版本或所有潜在行为均已证明。原始 evidence 和报告保存在各项目本地的 `.verification/` 中，该目录默认不提交。
