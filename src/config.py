"""Configuration management for agent-tool-gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HOST_TOKEN = "local-dev-host-token"


@dataclass(frozen=True)
class GatewayConfig:
    """Resolved gateway paths and isolated host token configuration."""

    project_root: Path = field(default_factory=lambda: DEFAULT_PROJECT_ROOT)
    policy_path: Path | None = None
    runtime_dir: Path | None = None
    db_path: Path | None = None
    audit_log_path: Path | None = None
    sandbox_dir: Path | None = None
    host_token: str = field(
        default_factory=lambda: os.environ.get("GATEWAY_HOST_TOKEN", DEFAULT_HOST_TOKEN)
    )

    def __post_init__(self) -> None:
        root = Path(self.project_root)
        runtime = Path(self.runtime_dir) if self.runtime_dir is not None else root / "runtime"
        policy = (
            Path(self.policy_path)
            if self.policy_path is not None
            else root / "policies" / "policy_v1.yaml"
        )
        db = Path(self.db_path) if self.db_path is not None else runtime / "gateway.db"
        audit = (
            Path(self.audit_log_path)
            if self.audit_log_path is not None
            else runtime / "audit.jsonl"
        )
        sandbox = Path(self.sandbox_dir) if self.sandbox_dir is not None else root / "sandbox"

        object.__setattr__(self, "project_root", root)
        object.__setattr__(self, "runtime_dir", runtime)
        object.__setattr__(self, "policy_path", policy)
        object.__setattr__(self, "db_path", db)
        object.__setattr__(self, "audit_log_path", audit)
        object.__setattr__(self, "sandbox_dir", sandbox)
