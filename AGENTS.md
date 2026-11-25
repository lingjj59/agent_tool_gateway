# AGENTS.md — `agent_tool_gateway` 协作与执行总规

## 1. 一句话定位与必读顺序
面向 AI Agent 的受控工具执行网关与审计回放系统（纯后端、零外网、全本地假数据：`Python 3.11+ / FastAPI / SQLite / YAML / Pytest / CLI`）。
**新会话必读顺序**：`TASK_CHARTER.md` → `brief/project-brief.md` → `design/specification.md` → `design/acceptance-matrix.md` → `design/architecture.md` → `design/plan-and-harness.md`。

## 2. 目录地图与权威边界（8 个目录）
| 目录 | 职责与权威边界 |
| :--- | :--- |
| `brief/` | 开题 Brief（范围、`INV-01`—`INV-03`、硬软门、人机责任、Assumptions、Open Questions） |
| `design/` | 唯一设计权威：`specification.md`、`acceptance-matrix.md`、`architecture.md`、`plan-and-harness.md` |
| `src/` | FastAPI 网关、YAML 策略引擎、SQLite 5 表、单行 JSONL 审计、4 个本地模拟工具与 CLI |
| `eval/` | `T-01`—`T-06` 纵向 Pytest、E1–E3 剧本、`K1`—`K6` 校准夹具与 `sandbox/public/` & `secret/` |
| `evidence/` | **只存绑定版本与 Run ID 的原始运行事实**（Trace/`mock_outbox`/成本记录），严禁写美化总结 |
| `review/` | **存工程解释与复核文件**（E1 实验卡与 ADR、E2 Diff、E3 Finding/修复、人工签署卡） |
| `release/` | 干净环境启动、SQLite/JSONL 重置、恢复演练实证与已知限制 |
| `evaluator/` | 轻量评价 Agent（3–4 只读工具 + 确定性预检 + 1 次 LLM 判读 + K1–K6 + `score_suggestion: null`） |

## 3. 五条硬工程约定
1. **固定 5 步前置流水线 & 5 表分工**：`POST /v1/tools/invoke` 严格按 ①查预算上限(`429`) → ②扣预算(`budget_used += 1`) → ③角色与路径授权(`403`) → ④幂等检查(同参`200`附`idempotency_hit=true` / 异参`409`) → ⑤执行(`200`)或`send_email`挂起(`202`)。SQLite 持久化 `sessions`、`idempotency_records`、`tickets`、`approvals`、独立 `mock_outbox` 共 5 张表；JSONL 单行序列化专责审计与防 `\n` 注入。
2. **同步复核与零泄密红线**：`send_email` 审批仅限 `X-Host-Token`，批准时同步按最新 YAML 复核（无中间态），撤权返 `403`、置 `REJECTED` 并记 `POLICY_REVOKED_BEFORE_EXECUTION`，终态重放返 `409`。`read_doc` 拦 `sandbox/secret/` 与路径穿越，`CANARY_*` 打码 `[REDACTED]`；全日志严禁存 `X-Host-Token` 原文；严禁外网与真实数据。
3. **纵向切片开发纪律**：严格按 `T-01`—`T-06` 纵向推进（代码 + Pytest 同步跑绿并独立提交至 `v0.1`），严禁先写完所有 `src/` 再补测试。**每张卡动手写代码前必须先提交改动清单与断言设计，待用户确认后再实施**。
4. **Stop / Ask 铁律**：同一测试连续失败 **3 次**即停；发现规格或状态机歧义即停；**严禁擅自执行 `git commit`、`git push --force`**，严禁删改外层 `.pptx` 或 `.git/`。
5. **证据与评价红线**：不改测试断言掩盖失败，不以自述替代运行事实；评价器不自动运行被评仓库脚本，不替代人类打分或签署。

## 4. 命令速查表（区分当前可跑 vs `Pending`）
| 状态 | 命令 | 用途 |
| :--- | :--- | :--- |
| **当前可跑** | `git status -u` | 查看工作区变更与未提交文件 |
| **当前可跑** | `python3 -c 'import pathlib, re; t="\n".join(pathlib.Path(p).read_text("utf-8") for p in ["TASK_CHARTER.md","brief/project-brief.md","design/specification.md","design/acceptance-matrix.md","design/architecture.md","design/plan-and-harness.md","AGENTS.md"]); assert len(set(re.findall(r"\bGW-[A-Z]+-\d+\b",t)))==8 and len(set(re.findall(r"\bT-0\d+\b",t)))==6; print("DOCS_OK")'` | 只读校验 8 个 `GW-*` 与 `T-01`—`T-06` 文档无断链 |
| **`Pending (待 T-0x 落地)`** | `pytest -q eval/test_t01_infra.py` … `pytest -q eval/test_t06_cli_and_e2e.py` | 对应 `T-01`—`T-06` 纵向切片验收 |
| **`Pending (待 T-06 落地)`** | `pytest -q eval/` / `uvicorn ...` / `python -m src.cli replay\|reset` | 全量回归、本地启动与 CLI 回放/重置 |
