"""Smoke tests for the FastMCP server registration.

These don't stand up an actual stdio transport — they verify the 8 tools
register on a real FastMCP instance and that the server module imports
without errors. End-to-end MCP integration is exercised in M1.9's red-team
harness against the launch script.
"""
from __future__ import annotations

import pytest

from privacy_agent.agent import PrivacyAgent
from privacy_agent.config import Config
from privacy_agent.server import register_tools


@pytest.fixture
def agent(conn):
    return PrivacyAgent(conn, Config(), orchestrator="claude_code")


def test_register_tools_attaches_eight_tools(agent):
    pytest.importorskip("mcp")
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("privacy-agent-test")
    register_tools(mcp, agent)

    # Internal API of FastMCP — fall back to the tool manager listing.
    tool_names = {t.name for t in mcp._tool_manager.list_tools()}
    expected = {
        "privacy_search",
        "privacy_index_volume",
        "privacy_read_excerpt",
        "privacy_list_volumes",
        "privacy_get_consent",
        "privacy_audit_log",
        "privacy_classify",
        "privacy_file_summary",
    }
    assert expected <= tool_names


def test_server_main_importable():
    """Smoke import — catches missing-dep regressions in the entry point."""
    from privacy_agent import server  # noqa: F401
    assert callable(server.main)
