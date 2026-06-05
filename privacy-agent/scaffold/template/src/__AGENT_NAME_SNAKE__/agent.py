"""Application core — wires infrastructure to domain tools."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .audit import AuditLogger
from .config import Config, ProfileOverride, load_config, validate
from .db import open_db

KNOWN_ORCHESTRATORS = __KNOWN_ORCHESTRATORS__


class Agent:
    def __init__(self, conn, cfg: Config, orchestrator: Optional[str] = None):
        self.conn = conn
        self.cfg = cfg
        self.audit = AuditLogger(conn)
        self.orchestrator = orchestrator or os.getenv(
            f"{os.getenv('AGENT_ENV_PREFIX', 'AGENT')}_ORCHESTRATOR", "unknown"
        )

    @property
    def profile(self) -> ProfileOverride:
        return getattr(self.cfg.profiles, self.orchestrator, None) or ProfileOverride()


def build_agent(
    db_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    orchestrator: Optional[str] = None,
) -> Agent:
    cfg = load_config(config_path)
    errors = validate(cfg)
    if errors:
        raise ValueError("config validation failed: " + "; ".join(errors))
    if db_path is None:
        db_path = Path(f"~/.{os.getenv('AGENT_NAME', 'agent')}/db.sqlite").expanduser()
    conn = open_db(db_path)
    return Agent(conn, cfg, orchestrator=orchestrator)
