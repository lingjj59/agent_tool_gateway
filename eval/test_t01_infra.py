"""Pytest suite for T-01 infrastructure foundation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.audit import AuditLogger
from src.config import GatewayConfig
from src.db import SCHEMA_TABLES, get_connection, init_db, transaction
from src.policy import PolicyValidationError, load_policy

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_config_defaults_and_tmp_path_override(tmp_path: Path) -> None:
    default_cfg = GatewayConfig()
    assert default_cfg.policy_path == default_cfg.project_root / "policies" / "policy_v1.yaml"
    assert default_cfg.runtime_dir == default_cfg.project_root / "runtime"
    assert default_cfg.db_path == default_cfg.project_root / "runtime" / "gateway.db"
    assert default_cfg.audit_log_path == default_cfg.project_root / "runtime" / "audit.jsonl"
    assert default_cfg.sandbox_dir == default_cfg.project_root / "sandbox"

    custom_runtime = tmp_path / "runtime_custom"
    custom_policy = tmp_path / "policy.yaml"
    custom_sandbox = tmp_path / "sandbox_custom"
    override_cfg = GatewayConfig(
        project_root=tmp_path,
        policy_path=custom_policy,
        runtime_dir=custom_runtime,
        sandbox_dir=custom_sandbox,
        host_token="test-token-override",
    )
    assert override_cfg.policy_path == custom_policy
    assert override_cfg.runtime_dir == custom_runtime
    assert override_cfg.db_path == custom_runtime / "gateway.db"
    assert override_cfg.audit_log_path == custom_runtime / "audit.jsonl"
    assert override_cfg.sandbox_dir == custom_sandbox
    assert override_cfg.host_token == "test-token-override"


def test_policy_yaml_valid_load_and_schema() -> None:
    policy = load_policy(REPO_ROOT / "policies" / "policy_v1.yaml")
    assert policy.policy_version == "v1"

    assert policy.roles["reader_agent"].budget_limit == 8
    assert policy.roles["reader_agent"].allowed_tools == ["read_doc", "query_tickets"]
    assert policy.roles["reader_agent"].approval_required_tools == []

    assert policy.roles["ops_agent"].budget_limit == 8
    assert policy.roles["ops_agent"].allowed_tools == [
        "read_doc",
        "query_tickets",
        "create_ticket",
        "send_email",
    ]
    assert policy.roles["ops_agent"].approval_required_tools == ["send_email"]

    assert policy.roles["budget_test_agent"].budget_limit == 3
    assert policy.roles["budget_test_agent"].allowed_tools == ["read_doc", "query_tickets"]
    assert policy.roles["budget_test_agent"].approval_required_tools == []

    assert policy.read_doc.public_dir == "sandbox/public"
    assert policy.read_doc.secret_dir == "sandbox/secret"
    assert policy.read_doc.redacted_placeholder == "[REDACTED]"


@pytest.mark.parametrize(
    "bad_yaml",
    [
        # Missing policy_version
        """
roles:
  reader_agent:
    budget_limit: 8
    allowed_tools: [read_doc]
  ops_agent:
    budget_limit: 8
    allowed_tools: [read_doc]
  budget_test_agent:
    budget_limit: 3
    allowed_tools: [read_doc]
read_doc:
  public_dir: sandbox/public
  secret_dir: sandbox/secret
  redact_patterns: ["CANARY_[A-Za-z0-9_-]+"]
""",
        # Negative budget_limit
        """
policy_version: "v1"
roles:
  reader_agent:
    budget_limit: -1
    allowed_tools: [read_doc]
  ops_agent:
    budget_limit: 8
    allowed_tools: [read_doc]
  budget_test_agent:
    budget_limit: 3
    allowed_tools: [read_doc]
read_doc:
  public_dir: sandbox/public
  secret_dir: sandbox/secret
  redact_patterns: ["CANARY_[A-Za-z0-9_-]+"]
""",
        # Unknown tool name
        """
policy_version: "v1"
roles:
  reader_agent:
    budget_limit: 8
    allowed_tools: [delete_everything]
  ops_agent:
    budget_limit: 8
    allowed_tools: [read_doc]
  budget_test_agent:
    budget_limit: 3
    allowed_tools: [read_doc]
read_doc:
  public_dir: sandbox/public
  secret_dir: sandbox/secret
  redact_patterns: ["CANARY_[A-Za-z0-9_-]+"]
""",
        # Broken YAML syntax
        "policy_version: [unclosed",
    ],
)
def test_policy_yaml_invalid_raises_explicit_error(tmp_path: Path, bad_yaml: str) -> None:
    bad_file = tmp_path / "bad_policy.yaml"
    bad_file.write_text(bad_yaml, encoding="utf-8")
    with pytest.raises(PolicyValidationError):
        load_policy(bad_file)


def test_sqlite_5_tables_idempotent_init_and_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime" / "gateway.db"

    # Idempotent repeated initialization
    init_db(db_path)
    init_db(db_path)

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        ).fetchall()
        table_names = {row["name"] for row in rows}
        assert table_names == set(SCHEMA_TABLES)

        # Foreign key enforcement: orphan approval must fail
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO approvals (
                    approval_id, session_id, idempotency_key, status,
                    policy_version, email_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("apr-orphan", "missing-sess", "k1", "PENDING_APPROVAL", "v1", "{}", "2026-11-25T00:00:00Z"),
            )

        # Seed valid session
        conn.execute(
            """
            INSERT INTO sessions (session_id, role, budget_limit, budget_used, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("sess-1", "ops_agent", 8, 0, "2026-11-25T00:00:00Z", "2026-11-25T00:00:00Z"),
        )

        # UNIQUE(session_id, idempotency_key) on idempotency_records
        conn.execute(
            """
            INSERT INTO idempotency_records (
                session_id, idempotency_key, tool_name, params_hash,
                http_status, response_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("sess-1", "idem-1", "create_ticket", "hash-a", 200, "{}", "2026-11-25T00:00:00Z"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO idempotency_records (
                    session_id, idempotency_key, tool_name, params_hash,
                    http_status, response_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("sess-1", "idem-1", "create_ticket", "hash-b", 200, "{}", "2026-11-25T00:00:01Z"),
            )

        # UNIQUE(session_id, idempotency_key) on approvals + UNIQUE(approval_id) on mock_outbox
        conn.execute(
            """
            INSERT INTO approvals (
                approval_id, session_id, idempotency_key, status,
                policy_version, email_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("apr-1", "sess-1", "idem-email-1", "EXECUTED", "v1", "{}", "2026-11-25T00:00:00Z"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO approvals (
                    approval_id, session_id, idempotency_key, status,
                    policy_version, email_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("apr-2", "sess-1", "idem-email-1", "PENDING_APPROVAL", "v1", "{}", "2026-11-25T00:00:01Z"),
            )

        conn.execute(
            """
            INSERT INTO mock_outbox (
                approval_id, session_id, recipient, subject, body, policy_version, sent_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("apr-1", "sess-1", "a@example.com", "hi", "body", "v1", "2026-11-25T00:00:02Z"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO mock_outbox (
                    approval_id, session_id, recipient, subject, body, policy_version, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("apr-1", "sess-1", "a@example.com", "hi", "dup", "v1", "2026-11-25T00:00:03Z"),
            )
    finally:
        conn.close()


def test_sqlite_transaction_rollback_on_exception(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime" / "gateway.db"
    init_db(db_path)

    with pytest.raises(RuntimeError, match="boom"):
        with transaction(db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, role, budget_limit, budget_used, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("sess-rollback", "ops_agent", 8, 0, "2026-11-25T00:00:00Z", "2026-11-25T00:00:00Z"),
            )
            raise RuntimeError("boom")

    conn = get_connection(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM sessions;").fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_jsonl_prevents_newline_log_injection(tmp_path: Path) -> None:
    log_path = tmp_path / "runtime" / "audit.jsonl"
    logger = AuditLogger(log_path)

    malicious_title = 'bug\n{"decision":"ALLOW","role":"admin"}\r\n\u2028{"fake":1}\u2029'
    logger.log_event(
        request_id="req-1",
        session_id="sess-inj",
        role="ops_agent",
        tool_name="create_ticket",
        policy_version="v1",
        http_status=403,
        decision="DENY",
        reason="FORBIDDEN\nINJECTION\u2028LINE",
        details={"title": malicious_title},
    )
    logger.log_event(
        request_id="req-2",
        session_id="sess-inj",
        role="ops_agent",
        tool_name="read_doc",
        policy_version="v1",
        http_status=200,
        decision="ALLOW",
        reason="OK",
    )

    raw_text = log_path.read_text(encoding="utf-8")
    assert "\u2028" not in raw_text
    assert "\u2029" not in raw_text
    lines = raw_text.splitlines()
    assert len(lines) == 2

    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["request_id"] == "req-1"
    assert parsed[0]["decision"] == "DENY"
    assert parsed[0]["role"] == "ops_agent"
    assert parsed[0]["http_status"] == 403
    assert parsed[0]["details"]["title"] == malicious_title
    assert parsed[1]["request_id"] == "req-2"


def test_audit_jsonl_fields_and_no_secret_leak(tmp_path: Path) -> None:
    dummy_host_token = "host-secret-xyz-999"
    log_path = tmp_path / "runtime" / "audit.jsonl"
    logger = AuditLogger(log_path, secret_values=[dummy_host_token])

    record = logger.log_event(
        request_id="req-sec-1",
        session_id="sess-sec",
        role="ops_agent",
        tool_name="read_doc",
        policy_version="v1",
        http_status=200,
        decision="ALLOW",
        reason=f"checked with {dummy_host_token}",
        details={
            "headers": {"X-Host-Token": dummy_host_token},
            "snippet": "Token prefix is CANARY_SECRET_001 inside doc",
            "host_token": dummy_host_token,
            f"meta_{dummy_host_token}": "val-1",
            "CANARY_KEY_999": "val-2",
        },
    )

    raw_file_text = log_path.read_text(encoding="utf-8")
    assert dummy_host_token not in raw_file_text
    assert "CANARY_SECRET_001" not in raw_file_text
    assert "CANARY_KEY_999" not in raw_file_text
    assert "[REDACTED]" in raw_file_text

    required_fields = {
        "timestamp",
        "request_id",
        "session_id",
        "role",
        "tool_name",
        "policy_version",
        "http_status",
        "decision",
        "reason",
    }
    assert required_fields.issubset(record.keys())
    assert record["details"]["headers"]["X-Host-Token"] == "[REDACTED]"
    assert record["details"]["host_token"] == "[REDACTED]"
    assert record["details"]["snippet"] == "Token prefix is [REDACTED] inside doc"
    assert record["details"]["meta_[REDACTED]"] == "val-1"
    assert record["details"]["[REDACTED]"] == "val-2"
