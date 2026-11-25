# Acceptance Matrix: `agent-tool-gateway`

> **⚠️ 状态声明（遵守质量红线 8）**：当前处于 **第 1 步 · Commit 2（设计阶段）**，尚未编写任何业务代码（`src/`）或测试代码（`eval/`）。下表中全部 Pytest 测试函数与验证状态当前均为 **`Pending`（待对应纵向切片 `T-01`—`T-06` 落地实现并实跑验证）**，严禁在此提前标注为通过。

---

## 1. 全量需求追踪矩阵（Req ID → RFC 2119 → GWT → 可观察结果 → 计划 Pytest → Task）

| Req ID | RFC 2119 等级 | 关联不变量 | 关联 GWT 场景 | 外部可观察结果（HTTP / SQLite / 计数 / JSONL） | 计划 Pytest 测试函数名（预期文件：`eval/test_t0x_*.py`） | 负责 Task | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **GW-AUTH-01** | **MUST** | INV-01 | `GWT-01`, `GWT-02`, `GWT-05` | 合法角色放行返 `200`；越权统一返 `403` 且响应无敏感内容；越权时底层工具执行计数增量 `== 0`，SQLite 业务表无新增行；JSONL 含 `decision="DENY"`。 | `test_role_allowlist_authorized_calls` / `test_unauthorized_role_returns_403_with_zero_exec`（`eval/test_t02_auth_and_read_doc.py`） | **T-02** | `Pending (待 T-02 落地)` |
| **GW-VIS-01** | **MUST** | INV-01 | `GWT-01`, `GWT-09` | 仅 `sandbox/public/` 可读；`sandbox/secret/`、`../` 与 `%2e%2e%2f` 路径穿越统一返 `403` 且底层计数增量 `== 0`；合法文档中的 `CANARY_*` 在响应和审计中打码为 `[REDACTED]`。 | `test_read_doc_redacts_canary_in_public_dir` / `test_read_doc_blocks_secret_and_traversal_403`（`eval/test_t02_auth_and_read_doc.py`） | **T-02** | `Pending (待 T-02 落地)` |
| **GW-BUDGET-01** | **MUST** | INV-02 | `GWT-01`, `GWT-02`, `GWT-04`, `GWT-05`, `GWT-06`, `GWT-07`, `GWT-09` | `sessions.budget_used` 单调递增（含 `403` 与 `409` 被拒请求）；达到上限（8/8/3）后后续请求返 `429`，底层工具执行计数增量 `== 0`，JSONL 记 `429`。 | `test_rejected_requests_consume_session_budget` / `test_budget_limit_enforced_returns_429`（`eval/test_t03_budget_and_tickets.py`） | **T-03** | `Pending (待 T-03 落地)` |
| **GW-INJ-01** | **MUST** | INV-01 | `GWT-10` | `query_tickets` 预置诱导工单仅作纯数据返回，不触发额外工具或提权（`send_email` 计数与审批表增量为 `0`）；含 `\n` 的恶意载荷在 JSONL 中经单行序列化转义，物理行数严格只增 `1`。 | `test_indirect_prompt_injection_ticket_isolated` / `test_jsonl_prevents_newline_log_injection`（`eval/test_t01_infra.py`, `eval/test_t03_budget_and_tickets.py`） | **T-01**, **T-03** | `Pending (待 T-01 / T-03 落地)` |
| **GW-IDEM-01** | **MUST** | INV-02 | `GWT-04` | 同会话同幂等键同参数复用返 `200`（含 `send_email` 重复申请，附 `idempotency_hit=true` 与首次等价结果/同一 `approval_id`）；底层工具执行计数增量 `== 0`，SQLite `tickets`/`approvals`/`mock_outbox` 无重复新增行；JSONL 标记幂等命中。 | `test_idempotency_same_params_returns_200_without_reexec`（`eval/test_t04_idempotency.py`） | **T-04** | `Pending (待 T-04 落地)` |
| **GW-IDEM-02** | **MUST** | INV-02 | `GWT-07` | 同会话同幂等键但参数/工具不同时返 `409`；首次持久化记录不被覆写，底层执行计数增量 `== 0`；被拒请求计入会话预算。 | `test_idempotency_different_params_returns_409_no_overwrite`（`eval/test_t04_idempotency.py`） | **T-04** | `Pending (待 T-04 落地)` |
| **GW-APPR-01** | **MUST** | INV-03 | `GWT-03`, `GWT-08`, `GWT-11` | `send_email` 申请返 `202`（`PENDING_APPROVAL`，`mock_outbox` 增 `0`）；无/错 `X-Host-Token` 返 `403`；批准同步读最新 YAML 策略复核：通过则 `EXECUTED` + `mock_outbox` `+1` + `200`，撤权则 `403` + `REJECTED` + `POLICY_REVOKED_BEFORE_EXECUTION` + `mock_outbox` 增 `0`；终态锁死再次审批返 `409` 不可重放。 | `test_send_email_requires_host_token_and_sync_recheck` / `test_policy_revoked_before_execution_returns_403` / `test_terminal_approval_cannot_be_replayed`（`eval/test_t05_approval_and_email.py`） | **T-05** | `Pending (待 T-05 落地)` |
| **GW-AUDIT-01** | **SHOULD** | INV-01, INV-03 | `GWT-01`~`GWT-03`, `GWT-05`, `GWT-08`~`GWT-11` | 单行 JSONL 完整记录 `request_id`/`session_id`/`policy_version`/`http_status`/`decision`/`reason`，支持 CLI 回放且历史记录不被策略升版改写；**全日志与回显严禁包含 `X-Host-Token` 原文或未打码 `CANARY_*`**。 | `test_audit_jsonl_fields_and_no_secret_leak` / `test_cli_replay_and_reset_end_to_end`（`eval/test_t01_infra.py`, `eval/test_t06_cli_and_e2e.py`） | **T-01**, **T-06** | `Pending (待 T-01 / T-06 落地)` |

---

## 2. 7 条 MUST 断链检查与纵向切片验收计划

- **断链核查结论**：`GW-AUTH-01`、`GW-VIS-01`、`GW-BUDGET-01`、`GW-INJ-01`、`GW-IDEM-01`、`GW-IDEM-02`、`GW-APPR-01` 共 **7 条 MUST 全部 100% 映射到具体 GWT 场景、可观察副作用、计划 Pytest 函数及 `T-01`—`T-06` 切片卡，无任何断链**。
- **纵向切片同步门禁（对齐 `TASK_CHARTER.md` 第 5 节）**：

| 切片卡 | 本卡关联 Req ID | 计划落盘测试文件 | 计划验收范围 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- |
| **T-01** | `GW-INJ-01`（日志部分）, `GW-AUDIT-01` | `eval/test_t01_infra.py` | 配置加载、YAML 策略解析、SQLite 5 表初始化（含 `mock_outbox`）、单行 JSONL 序列化与防换行/零密钥脱敏 | `Pending` |
| **T-02** | `GW-AUTH-01`, `GW-VIS-01` | `eval/test_t02_auth_and_read_doc.py` | 3 角色权限校验（`403`）、`read_doc` 目录隔离、`../` 与 URL 编码穿越拦截、`CANARY_*` → `[REDACTED]` | `Pending` |
| **T-03** | `GW-BUDGET-01`, `GW-INJ-01` | `eval/test_t03_budget_and_tickets.py` | 会话预算（8/8/3）、被拒计费、`429` 阻断、`create_ticket` 与 `query_tickets`（含诱导样本隔离） | `Pending` |
| **T-04** | `GW-IDEM-01`, `GW-IDEM-02` | `eval/test_t04_idempotency.py` | 幂等键同参去重（`200`、执行计数增量 `0`）与异参冲突（`409`、不覆写首次记录） | `Pending` |
| **T-05** | `GW-APPR-01` | `eval/test_t05_approval_and_email.py` | `send_email` 待批（`202`）、`X-Host-Token` 隔离、批准同步策略二次复核（含 `POLICY_REVOKED_BEFORE_EXECUTION`）、假发件箱与终态锁死 | `Pending` |
| **T-06** | `GW-AUDIT-01` + 全量 `GW-*` | `eval/test_t06_cli_and_e2e.py` | CLI 回放/重置命令、全量端到端回归，跑绿后冻结 **`v0.1` 基线** | `Pending` |
