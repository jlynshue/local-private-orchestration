"""TOML configuration loader — reused from privacy-agent scaffold."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class AgentConfig:
    bind: str = "stdio"
    log_level: str = "info"
    snippet_max_chars: int = 200
    max_results_per_query: int = 20
    enable_excerpt_tool: bool = False


@dataclass
class ConsentConfig:
    default_expiry_hours: int = 168
    require_per_scope_consent: bool = True


@dataclass
class AuditConfig:
    enabled: bool = True
    retention_days: int = 365


@dataclass
class ProfileOverride:
    enable_excerpt_tool: Optional[bool] = None
    classification_cap: Optional[str] = None
    max_results_per_query: Optional[int] = None


@dataclass
class ProfilesConfig:
    claude_code: ProfileOverride = field(default_factory=ProfileOverride)
    codex: ProfileOverride = field(default_factory=lambda: ProfileOverride(enable_excerpt_tool=False, classification_cap="confidential"))
    goose: ProfileOverride = field(default_factory=lambda: ProfileOverride(enable_excerpt_tool=False, classification_cap="internal"))
    cline: ProfileOverride = field(default_factory=lambda: ProfileOverride(enable_excerpt_tool=False, classification_cap="confidential"))
    continue_dev: ProfileOverride = field(default_factory=lambda: ProfileOverride(enable_excerpt_tool=False, classification_cap="confidential"))
    zed: ProfileOverride = field(default_factory=lambda: ProfileOverride(enable_excerpt_tool=False, classification_cap="confidential"))
    cursor: ProfileOverride = field(default_factory=lambda: ProfileOverride(enable_excerpt_tool=False, classification_cap="confidential"))
    aider: ProfileOverride = field(default_factory=lambda: ProfileOverride(enable_excerpt_tool=False, classification_cap="internal"))


@dataclass
class Config:
    agent: AgentConfig = field(default_factory=AgentConfig)
    consent: ConsentConfig = field(default_factory=ConsentConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    profiles: ProfilesConfig = field(default_factory=ProfilesConfig)


def _coerce(cls, raw: dict[str, Any]):
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in raw.items() if k in known})


def load_config(path: Optional[Path]) -> Config:
    if path is None or not path.exists():
        return Config()
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    cfg = Config()
    if "agent" in raw:
        cfg.agent = _coerce(AgentConfig, raw["agent"])
    if "consent" in raw:
        cfg.consent = _coerce(ConsentConfig, raw["consent"])
    if "audit" in raw:
        cfg.audit = _coerce(AuditConfig, raw["audit"])
    return cfg


def validate(cfg: Config) -> list[str]:
    errors: list[str] = []
    if cfg.agent.bind != "stdio":
        errors.append(f"agent.bind must be 'stdio', got {cfg.agent.bind!r}")
    if cfg.agent.snippet_max_chars > 500 or cfg.agent.snippet_max_chars < 1:
        errors.append(f"agent.snippet_max_chars must be in [1, 500]")
    return errors
