"""MCP stdio server entry point."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from .agent import build_agent
from .tools import register_tools

logger = logging.getLogger(__name__)


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config_path_env = os.getenv("AGENT_CONFIG")
    config_path = Path(config_path_env).expanduser() if config_path_env else None
    db_path_env = os.getenv("AGENT_DB")
    db_path = Path(db_path_env).expanduser() if db_path_env else None

    agent = build_agent(db_path=db_path, config_path=config_path)

    valid, broken = agent.audit.verify_chain_integrity()
    if not valid:
        logger.error("audit chain broken at startup: %d entries", len(broken))

    mcp = FastMCP("${AGENT_NAME_KEBAB}")
    register_tools(mcp, agent)
    logger.info("${AGENT_NAME_HUMAN} starting: orchestrator=%s", agent.orchestrator)
    mcp.run()


if __name__ == "__main__":
    main()
