"""Scaffold tests — verify the infrastructure works before domain code is added."""
from __future__ import annotations

from pathlib import Path

from __AGENT_NAME_SNAKE__.agent import build_agent
from __AGENT_NAME_SNAKE__.audit import AuditLogger
from __AGENT_NAME_SNAKE__ import db


def test_db_opens_with_schema(tmp_db_path: Path):
    conn = db.open_db(tmp_db_path)
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "audit" in tables
    assert "consent" in tables
    conn.close()


def test_audit_chain_works(conn):
    logger = AuditLogger(conn)
    logger.log("test", "manual")
    logger.log("test", "manual")
    valid, broken = logger.verify_chain_integrity()
    assert valid is True
    assert broken == []


def test_audit_tamper_detected(conn):
    logger = AuditLogger(conn)
    logger.log("test", "manual")
    logger.log("test", "manual")
    conn.execute("UPDATE audit SET action='TAMPERED' WHERE sequence_num=1")
    conn.commit()
    valid, broken = logger.verify_chain_integrity()
    assert valid is False
    assert len(broken) >= 1


def test_build_agent(tmp_db_path: Path):
    agent = build_agent(db_path=tmp_db_path)
    assert agent.conn is not None
    assert agent.orchestrator == "unknown"  # no env var set
    agent.conn.close()


def test_server_imports():
    from __AGENT_NAME_SNAKE__ import server
    assert callable(server.main)


def test_tools_register():
    import pytest
    pytest.importorskip("mcp")
    from mcp.server.fastmcp import FastMCP
    from __AGENT_NAME_SNAKE__.agent import build_agent
    from __AGENT_NAME_SNAKE__.tools import register_tools

    agent = build_agent(db_path=Path("/tmp/test_scaffold_tools.db"))
    try:
        mcp_server = FastMCP("test")
        register_tools(mcp_server, agent)
        tools = {t.name for t in mcp_server._tool_manager.list_tools()}
        assert "hello" in tools
    finally:
        agent.conn.close()
        Path("/tmp/test_scaffold_tools.db").unlink(missing_ok=True)
