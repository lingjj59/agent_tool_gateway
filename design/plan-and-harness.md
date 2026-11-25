# Plan & Double-Layer Harness: `agent-tool-gateway`

- **仓库与目录**：`agent_tool_gateway`（GitHub：`lingjj59/agent_tool_gateway`）
- **所属阶段**：第 1 步 · Commit 3（开题与设计收官）
- **上游依据**：[TASK_CHARTER.md](../TASK_CHARTER.md)、[project-brief.md](../brief/project-brief.md)、[specification.md](./specification.md)、[acceptance-matrix.md](./acceptance-matrix.md)、[architecture.md](./architecture.md)
- **已锁定基线**：5 步前置流水线（①查限 `429` → ②扣预算 `budget_used += 1` → ③鉴权/路径 `403` → ④幂等 `200`/`409` → ⑤执行 `200`/挂起 `202`）、SQLite 5 表（`sessions`、`idempotency_records`、`tickets`、`approvals`、`mock_outbox`）+ 单行序列化 JSONL 审计日志。

---

## 1. 里程碑总表（Roadmap Milestones）

| 里程碑 | 范围与核心交付 | 准出检查点（Gate） | 当前状态 |
| :--- | :--- | :--- | :--- |
| **M1｜开题与双层 Harness（Commit 1–3）** | 骨架、`.gitignore`、`TASK_CHARTER.md`、`brief/`、`design/` 全套契约/矩阵/架构/计划与根目录 `AGENTS.md` | 8 个 `GW-*` 与 `T-01`—`T-06` 全仓库文档无断链、无错位，人工审阅后提交 Commit 3 | 进行中（本轮收官） |
| **M2｜纵向切片与 `v0.1` 冻结（`T-01`—`T-06`）** | 严格按卡纵向切片推进，每卡写代码前先交改动清单与断言设计获批，代码 + Pytest 跑绿后独立提交 | `T-01`—`T-06` 全部跑绿，全量回归通过后冻结 **`v0.1` 基线** | `Pending` |
| **M3｜E1 取舍实验（O4）** | `v0.1` 冻结基线上单变量对比“纯规则裁决” vs “规则 + 语义二审”，记录负结果与成本口径 | 输出实验卡、原始数据与 ADR | `Pending` |
| **M4｜轻量评价 Agent（O3/O7）** | 3–4 个受限只读工具 + 确定性预检 + 1 次 LLM 判读 + `score_suggestion: null` + 人工签署 | 通过 `K1`—`K6` 校准集与错误分析 | `Pending` |
| **M5｜E2 策略撤权与 E3 4 方向对抗（O5）** | E2 YAML 升版撤权（`POLICY_REVOKED_BEFORE_EXECUTION`）与 E3 4 方向对抗修复回归 | 产出 Diff、Finding、修复与回归证据 | `Pending` |
| **M6｜交接与发布（O6/O7）** | 干净环境启动、SQLite/JSONL 重置与恢复演练实证、已知限制与最终人工签署 | `release/` 演练实证通过 + 人类签署 | `Pending` |

---

## 2. 纵向切片任务卡（`T-01` — `T-06`）

> 严格对齐 [TASK_CHARTER.md](../TASK_CHARTER.md) 第 5 节与 [acceptance-matrix.md](./acceptance-matrix.md)。禁止横切开发（严禁先写完所有 `src/` 再补 `eval/`）。

### `T-01`｜基础设施：配置、YAML 策略引擎基础版、SQLite 5 表与单行 JSONL 审计
- **目标**：搭建 Python 包骨架与配置加载，落地 YAML 策略加载与校验（含显式 `policy_version`）、SQLite 5 表（`sessions`, `idempotency_records`, `tickets`, `approvals`, `mock_outbox`）初始化，以及单行序列化 JSONL 审计写入器（转义 `\n`/`\r` 防换行注入、严禁存 `X-Host-Token`/假密钥原文）。
- **关联 Req ID**：`GW-INJ-01`（日志防换行部分）、`GW-AUDIT-01`（基础设施与零密钥脱敏部分）
- **改动范围**：`pyproject.toml`、`src/` 配置/策略/SQLite 5 表/JSONL 审计模块、默认策略 `YAML`、`eval/test_t01_infra.py`
- **前置依赖**：Commit 3 完成（`design/plan-and-harness.md` 与 `AGENTS.md` 审核提交）
- **DoR**：ADR-001/ADR-002 已定稿；改动清单与 `eval/test_t01_infra.py` 断言设计获用户确认。
- **DoD 与计划验证命令**：
  - 5 表建表幂等，无效 YAML 显式报错；含 `\n` 输入写入 JSONL 后物理行数仅 `+1` 且每行 `json.loads()` 成功；日志中绝不出现假密钥原文。
  - 计划命令：`pytest -q eval/test_t01_infra.py` *(Pending 待 T-01 落地)*
- **停止条件**：SQLite 5 表 Schema 与 ADR-002 出现字段歧义；`test_t01_infra.py` 连续失败 3 次即停。

### `T-02`｜角色授权与 `read_doc` 目录隔离脱敏切片
- **目标**：打通 FastAPI `POST /v1/tools/invoke` 角色权限校验（`reader_agent`、`ops_agent`、`budget_test_agent`）与 `read_doc` 工具处理器及底层执行计数器 `tool_exec_count["read_doc"]`；实现 `sandbox/public/` 与 `sandbox/secret/` 目录隔离，拦截字面 `../` 及 URL 编码路径穿越统一返回 `403`，合法文档中 `CANARY_*` 在响应与审计中打码为 `[REDACTED]`。
- **关联 Req ID**：`GW-AUTH-01`、`GW-VIS-01`
- **改动范围**：`src/` FastAPI 应用与路由骨架、授权校验模块、`read_doc` 工具与底层计数、`sandbox/public/` & `sandbox/secret/` 静态夹具、`eval/test_t02_auth_and_read_doc.py`
- **前置依赖**：`T-01` Pytest 跑绿并独立提交
- **DoR**：`sandbox/` 目录边界规则在 `specification.md` 无歧义；本卡改动清单与断言设计获用户确认。
- **DoD 与计划验证命令**：
  - 越权与路径穿越统一返 `403` 且 `tool_exec_count` 增量 `== 0`；合法文档中 `CANARY_*` 全量替换为 `[REDACTED]`。
  - 计划命令：`pytest -q eval/test_t02_auth_and_read_doc.py` *(Pending 待 T-02 落地)*
- **停止条件**：发现 URL 编码或软链接可绕过目录隔离；或同一测试连续失败 3 次即停。

### `T-03`｜固定 5 步前置流水线（步骤 ①② 预算）与 `query_tickets` / `create_ticket` 切片
- **目标**：严格固化 `POST /v1/tools/invoke` 步骤 ①（检查 `budget_used >= budget_limit` 返 `429`）→ ②（原子 `budget_used += 1`，确保 `403` 等被拒请求同样扣预算），上线会话查询接口 `GET /v1/sessions/{session_id}`，并实现 `query_tickets`（预置含间接提示词诱导文本的假工单）与 `create_ticket` 工具及底层计数。
- **关联 Req ID**：`GW-BUDGET-01`、`GW-INJ-01`（诱导工单隔离部分）
- **改动范围**：`src/` 预算控制与事务模块、`query_tickets` / `create_ticket` 工具处理器、预置诱导工单种子数据、`eval/test_t03_budget_and_tickets.py`
- **前置依赖**：`T-02` Pytest 跑绿并独立提交
- **DoR**：5 步前置流水线顺序（①→②→③）锁定无歧义；本卡改动清单与断言设计获用户确认。
- **DoD 与计划验证命令**：
  - `budget_test_agent` 混合 `200`/`403` 至 3 次后第 4 次返 `429` 且 `budget_used` 维持 `3`、底层计数增量 `== 0`；诱导工单仅作纯数据返回不触发额外工具或提权。
  - 计划命令：`pytest -q eval/test_t03_budget_and_tickets.py` *(Pending 待 T-03 落地)*
- **停止条件**：出现 `429` 仍继续扣减预算、`403` 漏扣预算，或诱导文本引发控制流异常；连败 3 次即停。

### `T-04`｜流水线步骤 ④ 幂等保护切片（同参 `200` / 异参 `409`）
- **目标**：实现 `POST /v1/tools/invoke` 步骤 ④ 幂等校验（读写 `idempotency_records` 表），同参去重统一返回 `200`（附 `idempotency_hit=true` 与首次等价结果，底层执行计数增量 `= 0`，不新增业务记录），异参冲突返回 `409`（严禁覆写首次记录，且步骤 ② 已计入预算）。
- **关联 Req ID**：`GW-IDEM-01`、`GW-IDEM-02`
- **改动范围**：`src/` 规范化参数哈希与幂等校验模块、路由接线、`eval/test_t04_idempotency.py`
- **前置依赖**：`T-03` Pytest 跑绿并独立提交
- **DoR**：规范化 `arguments` 哈希口径明确；本卡改动清单与断言设计获用户确认。
- **DoD 与计划验证命令**：
  - 同参去重返 `200` 且底层执行计数增量 `== 0`、`tickets` 无重复行；异参返 `409` 且原记录完好、预算照常扣减。
  - 计划命令：`pytest -q eval/test_t04_idempotency.py` *(Pending 待 T-04 落地)*
- **停止条件**：出现并发/重复下产生双份记录或异参静默覆盖；连败 3 次即停。

### `T-05`｜`send_email` 隔离审批、同步策略二次复核与 `mock_outbox` 切片
- **目标**：实现步骤 ⑤ 高风险 `send_email` 挂起（首次返回 `202` `PENDING_APPROVAL`，同参重放走步骤 ④ 返回 `200` 附 `idempotency_hit=true` 与同一 `approval_id`）、宿主审批接口 `POST /v1/approvals/{approval_id}/decision`（强制 `X-Host-Token` 隔离校验、缺失/错误返 `403` 且日志零原文）与只读查询 `GET /v1/approvals/{approval_id}`；批准时**同步按最新 YAML 策略二次复核**（通过则在单事务内写 `approvals.status='EXECUTED'` + `INSERT INTO mock_outbox` 返 `200`；撤权则返 `403`、`REJECTED`、`POLICY_REVOKED_BEFORE_EXECUTION` 且 `mock_outbox` 增量 `= 0`）；终态（`EXECUTED`/`REJECTED`）锁死再次审批返 `409`。
- **关联 Req ID**：`GW-APPR-01`
- **改动范围**：`src/` `send_email` 处理器、审批服务与路由、`eval/test_t05_approval_and_email.py`
- **前置依赖**：`T-04` Pytest 跑绿并独立提交
- **DoR**：`X-Host-Token` 注入方式（环境变量/配置且不入库不入日志）及同步复核原子事务明确；本卡改动清单与断言设计获用户确认。
- **DoD 与计划验证命令**：
  - 覆盖 `202` 挂起、同参 `200` 去重、无/错 Token `403`、正常审批写 `mock_outbox`、策略升版撤权返 `403` + `POLICY_REVOKED_BEFORE_EXECUTION`、终态锁死返 `409` 及全日志零密钥原文断言。
  - 计划命令：`pytest -q eval/test_t05_approval_and_email.py` *(Pending 待 T-05 落地)*
- **停止条件**：发现 `approvals` 与 `mock_outbox` 出现半提交、未读取最新 YAML，或日志中出现 `X-Host-Token` 原文；连败 3 次即停。

### `T-06`｜CLI 回放/重置工具切片与全量回归（冻结 `v0.1` 基线）
- **目标**：实现 CLI 命令行工具（按 `session_id` 回放 JSONL 审计轨迹、查看 SQLite `sessions`/`approvals`/`mock_outbox` 状态、干净环境一键重置 SQLite 与 JSONL 并重新植入种子数据），编写全量端到端集成测试，跑通全部 `T-01`—`T-06` 后冻结 **`v0.1` 基线**。
- **关联 Req ID**：`GW-AUDIT-01` + 全量 `GW-*` 端到端回归
- **改动范围**：`src/` CLI 模块、`eval/test_t06_cli_and_e2e.py`、`evidence/` 首次 `v0.1` 基线原始输出归档
- **前置依赖**：`T-05` Pytest 跑绿并独立提交
- **DoR**：CLI 子命令接口（`replay` / `inspect` / `reset`）与种子重置口径明确；本卡改动清单与断言设计获用户确认。
- **DoD 与计划验证命令**：
  - 全量 `eval/` 跑绿且历史 JSONL 在策略升版后仍保留原 `policy_version`；CLI 回放输出不含 `X-Host-Token` 原文；重置后可干净复跑。
  - 计划命令：`pytest -q eval/` + CLI 回放/重置命令 *(Pending 待 T-06 落地)*
- **停止条件**：任意一条 `GW-*` 回归失败或干净环境重置后测试不通过；连败 3 次即停。

---

## 3. 双层 Harness Manifest

### 3.1 Runtime Harness（由外部 AI 编程宿主环境提供）
以下能力由外部 AI 编程宿主（Agent Runtime / IDE 沙箱）提供与强制执行，不由本项目业务代码重新发明：
- **进程与文件系统沙箱**：限制命令执行范围与外部写入边界（非沙箱操作需用户显式授权）；
- **网络隔离控制**：默认阻断未授权外网请求，天然兜底本项目“零外网”硬边界；
- **工具审批与会话中断**：支持操作前确认、流式任务取消与人工接管；
- **只读检查通道**：允许无副作用读取仓库文件、Git 状态与结构化输出，供人类与评价器复核。

### 3.2 Project Harness（本项目仓内约束与接口）

#### A. 验证命令表（严守红线 8：区分当前可跑 vs `Pending`）
| 类别 | 命令 | 适用阶段 | 当前可运行状态 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| **文档一致性只读检查** | `python3 -c 'import pathlib, re; docs = ["TASK_CHARTER.md", "brief/project-brief.md", "design/specification.md", "design/acceptance-matrix.md", "design/architecture.md", "design/plan-and-harness.md", "AGENTS.md"]; texts = {d: pathlib.Path(d).read_text("utf-8") for d in docs}; gws = {"GW-AUTH-01","GW-VIS-01","GW-BUDGET-01","GW-INJ-01","GW-IDEM-01","GW-IDEM-02","GW-APPR-01","GW-AUDIT-01"}; ts = {"T-01","T-02","T-03","T-04","T-05","T-06"}; assert gws == set(re.findall(r"\bGW-[A-Z]+-\d+\b", "\n".join(texts.values()))); assert ts == set(re.findall(r"\bT-0\d+\b", "\n".join(texts.values()))); print("DOCS_OK")'` 与 `git status -u` | Commit 3 及全程 | **当前可跑（Commit 3 即用）** | 仅只读扫描文档编号集合与 Git 状态，零副作用 |
| **基础设施单测** | `pytest -q eval/test_t01_infra.py` | `T-01` 起 | **`Pending (待 T-01 落地)`** | 尚未创建 `src/` 与 `eval/` 文件 |
| **授权与 `read_doc` 单测** | `pytest -q eval/test_t02_auth_and_read_doc.py` | `T-02` 起 | **`Pending (待 T-02 落地)`** | 依赖 `T-01` 与 `T-02` 代码及夹具 |
| **预算与工单单测** | `pytest -q eval/test_t03_budget_and_tickets.py` | `T-03` 起 | **`Pending (待 T-03 落地)`** | 依赖 `T-03` 流水线与种子数据 |
| **幂等保护单测** | `pytest -q eval/test_t04_idempotency.py` | `T-04` 起 | **`Pending (待 T-04 落地)`** | 依赖 `T-04` 幂等逻辑 |
| **审批隔离与复核单测** | `pytest -q eval/test_t05_approval_and_email.py` | `T-05` 起 | **`Pending (待 T-05 落地)`** | 依赖 `T-05` 审批与 `mock_outbox` |
| **全量回归与服务启动** | `pytest -q eval/` \| `uvicorn ...` | `T-06` 起 | **`Pending (待 T-06 落地)`** | 全量切片完成后冻结 `v0.1` |
| **CLI 回放与重置** | `python -m src.cli replay ...` / `reset` | `T-06` 起 | **`Pending (待 T-06 落地)`** | 依赖 `T-06` CLI 模块落地 |

#### B. Allow / Ask / Deny 权限边界
- **Allow（当前阶段及已授权切片内可自动执行）**：
  - 只读查看仓库文档、目录树、`git status`、`git log`、`git diff`；
  - 执行只读文档一致性检查脚本；
  - 在用户已批准当前任务卡改动清单后，编写该卡范围内的 `src/` 与 `eval/` 文件并运行对应 `pytest`。
- **Ask（必须先停下来向用户请示）**：
  - 进入任意新任务卡（`T-01`—`T-06`）写代码前，**必须先提交本卡改动清单与测试断言设计，待用户确认后再动手**；
  - 需要修改任何核心设定（3 角色/预算、4 工具、5 步流水线、5 表结构、5 个状态码）、新增第三方依赖、或进入 E1/E2/E3 实验条件变更。
- **Deny（绝对禁止）**：
  - **严禁擅自执行 `git commit`、`git push` 或 `git push --force`**；
  - 严禁提前跨轮偷跑后续任务卡代码或实验脚本；
  - 严禁删除外层 `.pptx` 文件或 `.git/` 目录；
  - 严禁访问外网、写入真实账号/密钥、将 `X-Host-Token` 原文写入日志、或修改断言掩盖失败。

#### C. 协作与叫停规则（Stop / Ask）
1. **先报后写**：每张 `T-0x` 卡动手写代码前，先输出「改动文件清单 + 对应 Pytest 断言设计」，用户批准后方可落盘代码。
2. **三败即停**：同一测试或故障修复**连续失败 3 次立即停止**，汇报完整报错、已排查假设与回滚建议，禁止盲目扩大改动面。
3. **歧义即停**：发现规格条文、状态码或权限边界存在未决歧义时立即停止，先向用户澄清并同步更新 `design/` 文档后再继续。
4. **人工提交**：每张卡跑绿并汇报实测输出后停止，由用户审查后亲自 `git commit`。

#### D. 回滚方式（Rollback）
- **文档与代码层**：未提交修改使用 `git restore <path>` 精确撤销；已提交切片使用 `git revert <commit>`（严禁对已推送历史强推）。
- **版本基线层**：`v0.1` 冻结后若后续实验/对抗引入回归，可检出或对比 `v0.1` 标签恢复。
- **策略与数据层**：YAML 策略按 `policy_version` 切回上一可用版本；SQLite 5 表与 JSONL 通过 `T-06` 重置命令或预先备份快照还原，绝不改写既有历史审计行。

---

## 4. 跨会话交接模板（7 字段 Continuity Pack）

> 每次阶段结束或开启新会话接管时，按以下固定 7 字段输出当前接力包：

```markdown
### Continuity Pack
1. Current Stage & Commit: <当前处于哪一步 / 最近一次已提交的 Git Commit SHA 与 Tag>
2. Verified Facts: <已通过实际命令/文件读取验证的事实，附具体路径或测试通过数>
3. Pending & Blockers: <当前尚未落地的任务卡、Open Questions 及是否存在阻塞>
4. Modified Files: <工作区已修改或新增的文件清单（与 git status 一致）>
5. Last Validation Commands & Results: <最近一次实跑命令及原样输出摘要（不得写 Pending 为 PASS）>
6. Next Exact Action: <下一位接手者/下一会话唯一要做的第一步具体动作>
7. Stop & Ask Conditions: <触发停机/请示人类的明确边界条件>
```
