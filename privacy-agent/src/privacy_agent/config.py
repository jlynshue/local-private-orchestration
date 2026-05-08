"""TOML configuration loader for privacy-agent.

The merged plan defaults `enable_excerpt_tool` to False (Sequencing Principle 3:
the excerpt tool stays off until Phase 2 lands H1+M1+H3). Operator must explicitly
flip it via ``/privacy-manage configure`` once the compensating controls exist.

NFR-PORT-1: stdio is the only allowed bind. Validation rejects anything else.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


@dataclass
class AgentConfig:
    snippet_max_chars: int = 200
    max_results_per_query: int = 20
    bind: str = "stdio"
    log_level: str = "info"
    enable_excerpt_tool: bool = False
    excerpt_max_chars: int = 500


@dataclass
class VolumesConfig:
    allowed: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)


@dataclass
class ConsentConfig:
    default_expiry_hours: int = 168  # 7 days
    excerpt_lease_minutes: int = 30  # M5: stricter window for raw reads
    require_per_file_consent: bool = False
    require_per_volume_consent: bool = True


@dataclass
class ClassificationRuleConfig:
    pattern: str
    level: str


@dataclass
class ClassificationConfig:
    default_level: str = "internal"
    rules: list[ClassificationRuleConfig] = field(default_factory=list)


@dataclass
class SearchConfig:
    fts_enabled: bool = True
    semantic_enabled: bool = False  # Phase 2
    embedding_model: str = "all-MiniLM-L6-v2"
    chromadb_path: str = "./data/chroma"


@dataclass
class EncryptionConfig:
    enabled: bool = True  # H5: day-1 encryption
    key_source: str = "keychain"  # keychain | env | file
    keychain_account: str = "privacy-agent-db"
    env_var: str = "PRIVACY_AGENT_DB_KEY"


@dataclass
class AuditConfig:
    enabled: bool = True
    retention_days: int = 365
    export_format: str = "jsonl"


@dataclass
class ExtractorsConfig:
    pdf_enabled: bool = True
    docx_enabled: bool = True
    csv_enabled: bool = True
    json_enabled: bool = True
    image_ocr_enabled: bool = False  # Phase 3
    max_file_size_mb: int = 100


@dataclass
class CanaryConfig:
    """H7: honeytokens. Detection-only tripwire."""
    enabled: bool = True
    seed_dir: str = "~/.privacy-agent/canaries"
    pattern_prefix: str = "CANARY-"


@dataclass
class ProfileOverride:
    """Per-orchestrator policy override (M2).

    Any field set here overrides the corresponding agent config field for that
    orchestrator. Goose ships stricter than Claude Code by default.
    """
    enable_excerpt_tool: Optional[bool] = None
    classification_cap: Optional[str] = None  # "public"|"internal"|"confidential"|"restricted"
    max_results_per_query: Optional[int] = None


@dataclass
class ProfilesConfig:
    claude_code: ProfileOverride = field(default_factory=ProfileOverride)
    codex: ProfileOverride = field(
        default_factory=lambda: ProfileOverride(
            enable_excerpt_tool=False, classification_cap="confidential"
        )
    )
    goose: ProfileOverride = field(
        default_factory=lambda: ProfileOverride(
            enable_excerpt_tool=False, classification_cap="internal"
        )
    )


@dataclass
class Config:
    agent: AgentConfig = field(default_factory=AgentConfig)
    volumes: VolumesConfig = field(default_factory=VolumesConfig)
    consent: ConsentConfig = field(default_factory=ConsentConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    encryption: EncryptionConfig = field(default_factory=EncryptionConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    extractors: ExtractorsConfig = field(default_factory=ExtractorsConfig)
    canary: CanaryConfig = field(default_factory=CanaryConfig)
    profiles: ProfilesConfig = field(default_factory=ProfilesConfig)


def _coerce(cls, raw: dict[str, Any]):
    """Build a dataclass instance from a dict, dropping unknown keys."""
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in raw.items() if k in known})


def _coerce_classification(raw: dict[str, Any]) -> ClassificationConfig:
    cfg = ClassificationConfig()
    if "default_level" in raw:
        cfg.default_level = raw["default_level"]
    rules_raw = raw.get("rules", [])
    cfg.rules = [
        ClassificationRuleConfig(pattern=r["pattern"], level=r["level"])
        for r in rules_raw
        if "pattern" in r and "level" in r
    ]
    return cfg


def _coerce_profiles(raw: dict[str, Any]) -> ProfilesConfig:
    cfg = ProfilesConfig()
    for key in ("claude_code", "codex", "goose"):
        if key in raw:
            setattr(cfg, key, _coerce(ProfileOverride, raw[key]))
    return cfg


def load_config(path: Optional[Path]) -> Config:
    """Load TOML config; missing file → defaults. Validation is the caller's job."""
    if path is None or not path.exists():
        return Config()
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return from_dict(raw)


def from_dict(raw: dict[str, Any]) -> Config:
    cfg = Config()
    if "agent" in raw:
        cfg.agent = _coerce(AgentConfig, raw["agent"])
    if "volumes" in raw:
        cfg.volumes = _coerce(VolumesConfig, raw["volumes"])
    if "consent" in raw:
        cfg.consent = _coerce(ConsentConfig, raw["consent"])
    if "classification" in raw:
        cfg.classification = _coerce_classification(raw["classification"])
    if "search" in raw:
        cfg.search = _coerce(SearchConfig, raw["search"])
    if "encryption" in raw:
        cfg.encryption = _coerce(EncryptionConfig, raw["encryption"])
    if "audit" in raw:
        cfg.audit = _coerce(AuditConfig, raw["audit"])
    if "extractors" in raw:
        cfg.extractors = _coerce(ExtractorsConfig, raw["extractors"])
    if "canary" in raw:
        cfg.canary = _coerce(CanaryConfig, raw["canary"])
    if "profiles" in raw:
        cfg.profiles = _coerce_profiles(raw["profiles"])
    return cfg


VALID_LEVELS = {"public", "internal", "confidential", "restricted"}


def validate(cfg: Config) -> list[str]:
    """Return list of validation errors. Empty list = config is valid."""
    errors: list[str] = []

    if cfg.agent.bind != "stdio":
        errors.append(f"agent.bind must be 'stdio' (NFR-PORT-1), got {cfg.agent.bind!r}")
    if cfg.agent.snippet_max_chars > 500 or cfg.agent.snippet_max_chars < 1:
        errors.append(
            f"agent.snippet_max_chars must be in [1, 500] (NFR-PERF-2), "
            f"got {cfg.agent.snippet_max_chars}"
        )
    if cfg.agent.excerpt_max_chars > 2000 or cfg.agent.excerpt_max_chars < 1:
        errors.append(
            f"agent.excerpt_max_chars must be in [1, 2000], got {cfg.agent.excerpt_max_chars}"
        )
    if cfg.agent.max_results_per_query > 50 or cfg.agent.max_results_per_query < 1:
        errors.append(
            f"agent.max_results_per_query must be in [1, 50], "
            f"got {cfg.agent.max_results_per_query}"
        )

    if cfg.classification.default_level not in VALID_LEVELS:
        errors.append(
            f"classification.default_level must be one of {sorted(VALID_LEVELS)}, "
            f"got {cfg.classification.default_level!r}"
        )
    for r in cfg.classification.rules:
        if r.level not in VALID_LEVELS:
            errors.append(
                f"classification.rules: invalid level {r.level!r} for pattern {r.pattern!r}"
            )

    if cfg.encryption.key_source not in {"keychain", "env", "file"}:
        errors.append(
            f"encryption.key_source must be one of keychain|env|file, "
            f"got {cfg.encryption.key_source!r}"
        )

    for prof_name in ("claude_code", "codex", "goose"):
        prof: ProfileOverride = getattr(cfg.profiles, prof_name)
        if prof.classification_cap is not None and prof.classification_cap not in VALID_LEVELS:
            errors.append(
                f"profiles.{prof_name}.classification_cap must be one of "
                f"{sorted(VALID_LEVELS)}, got {prof.classification_cap!r}"
            )

    return errors
