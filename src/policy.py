"""Declarative YAML policy loader and strict schema validator."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

ToolName = Literal["read_doc", "query_tickets", "create_ticket", "send_email"]
RoleName = Literal["reader_agent", "ops_agent", "budget_test_agent"]
REQUIRED_ROLES: tuple[str, ...] = ("reader_agent", "ops_agent", "budget_test_agent")


class PolicyValidationError(ValueError):
    """Raised when a policy YAML file is missing, malformed, or violates schema rules."""


class RolePolicy(BaseModel):
    """Authorization and session budget limits for a single agent role."""

    model_config = ConfigDict(extra="forbid")

    budget_limit: int = Field(gt=0)
    allowed_tools: list[ToolName]
    approval_required_tools: list[ToolName] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_approval_subset(self) -> RolePolicy:
        allowed = set(self.allowed_tools)
        extra_approval = [t for t in self.approval_required_tools if t not in allowed]
        if extra_approval:
            raise ValueError(
                f"approval_required_tools must be a subset of allowed_tools: {extra_approval}"
            )
        return self


class ReadDocPolicy(BaseModel):
    """Path isolation and redaction configuration for read_doc."""

    model_config = ConfigDict(extra="forbid")

    public_dir: str = Field(min_length=1)
    secret_dir: str = Field(min_length=1)
    redact_patterns: list[str] = Field(min_length=1)
    redacted_placeholder: str = Field(default="[REDACTED]", min_length=1)

    @field_validator("redact_patterns")
    @classmethod
    def validate_regex_patterns(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            if not pattern:
                raise ValueError("redact_patterns cannot contain empty strings")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid regex pattern {pattern!r}: {exc}") from exc
        return patterns


class GatewayPolicy(BaseModel):
    """Top-level declarative YAML gateway policy."""

    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(min_length=1)
    roles: dict[RoleName, RolePolicy]
    read_doc: ReadDocPolicy

    @field_validator("policy_version")
    @classmethod
    def validate_version_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("policy_version cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_required_roles_present(self) -> GatewayPolicy:
        missing = [role for role in REQUIRED_ROLES if role not in self.roles]
        if missing:
            raise ValueError(f"missing required roles in policy: {missing}")
        return self


def load_policy(policy_path: Path) -> GatewayPolicy:
    """Load and validate a YAML policy file from disk synchronously."""
    path = Path(policy_path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyValidationError(f"failed to read policy file {path}: {exc}") from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise PolicyValidationError(f"invalid YAML syntax in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise PolicyValidationError(f"policy file {path} must decode to a YAML mapping")

    try:
        return GatewayPolicy.model_validate(data)
    except ValidationError as exc:
        raise PolicyValidationError(f"policy schema validation failed in {path}: {exc}") from exc
