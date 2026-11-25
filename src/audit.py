"""Single-line JSONL audit logger with secret and canary redaction."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SENSITIVE_KEY_NAMES = frozenset(
    {
        "x-host-token",
        "host_token",
        "authorization",
        "api_key",
        "secret",
        "token",
        "password",
    }
)
DEFAULT_CANARY_PATTERN = r"CANARY_[A-Za-z0-9_-]+"


def _redact_string(
    text: str,
    compiled_patterns: Sequence[re.Pattern[str]],
    secret_values: Sequence[str],
    placeholder: str,
) -> str:
    masked = text
    for secret in secret_values:
        if secret:
            masked = masked.replace(secret, placeholder)
    for pattern in compiled_patterns:
        masked = pattern.sub(placeholder, masked)
    return masked


def sanitize_value(
    value: Any,
    compiled_patterns: Sequence[re.Pattern[str]],
    secret_values: Sequence[str],
    placeholder: str = "[REDACTED]",
    *,
    key_name: str | None = None,
) -> Any:
    """Recursively mask sensitive header keys, literal secrets, and canary markers."""
    if key_name is not None and key_name.strip().lower() in SENSITIVE_KEY_NAMES:
        return placeholder

    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        for k, v in value.items():
            raw_key = str(k)
            clean_key = _redact_string(raw_key, compiled_patterns, secret_values, placeholder)
            sanitized_dict[clean_key] = sanitize_value(
                v,
                compiled_patterns,
                secret_values,
                placeholder,
                key_name=raw_key,
            )
        return sanitized_dict
    if isinstance(value, list):
        return [
            sanitize_value(item, compiled_patterns, secret_values, placeholder)
            for item in value
        ]
    if isinstance(value, tuple):
        return [
            sanitize_value(item, compiled_patterns, secret_values, placeholder)
            for item in value
        ]
    if isinstance(value, str):
        return _redact_string(value, compiled_patterns, secret_values, placeholder)
    return value


class AuditLogger:
    """Append-only single-line JSONL audit writer preventing log injection."""

    def __init__(
        self,
        log_path: Path,
        *,
        secret_values: Sequence[str] = (),
        redact_patterns: Sequence[str] = (DEFAULT_CANARY_PATTERN,),
        placeholder: str = "[REDACTED]",
    ) -> None:
        self.log_path = Path(log_path)
        self.secret_values = tuple(s for s in secret_values if s)
        self.compiled_patterns = tuple(re.compile(p) for p in redact_patterns)
        self.placeholder = placeholder

    def log_event(
        self,
        *,
        request_id: str,
        session_id: str,
        role: str,
        tool_name: str,
        policy_version: str,
        http_status: int,
        decision: str,
        reason: str,
        details: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Serialize a sanitized audit event as a strict single-line JSONL record."""
        raw_event: dict[str, Any] = {
            "timestamp": timestamp or datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "session_id": session_id,
            "role": role,
            "tool_name": tool_name,
            "policy_version": policy_version,
            "http_status": http_status,
            "decision": decision,
            "reason": reason,
        }
        if details is not None:
            raw_event["details"] = details

        sanitized = sanitize_value(
            raw_event,
            self.compiled_patterns,
            self.secret_values,
            self.placeholder,
        )
        # Compact single-line JSON + explicit U+2028/U+2029 escaping prevents splitlines() injection.
        line = (
            json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029")
        )
        if any(sep in line for sep in ("\n", "\r", "\u2028", "\u2029")):
            raise ValueError("serialized JSONL audit line must not contain raw line separators")

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

        return sanitized
