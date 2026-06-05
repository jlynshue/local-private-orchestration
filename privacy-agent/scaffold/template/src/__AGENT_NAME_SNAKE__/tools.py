"""Domain tools — FILL THIS IN with your agent's specific capabilities.

This file is where you define the MCP tools your agent exposes. The scaffold
provides the infrastructure (audit, consent, profiles, config); you provide
the domain logic here.

Example (a secrets-scanner agent):
    @mcp.tool()
    def scan_file(path: str) -> dict:
        ...

Example (a code-review agent):
    @mcp.tool()
    def review_diff(base: str, head: str) -> dict:
        ...

Each tool should:
1. Check consent if accessing sensitive resources
2. Log to the audit chain
3. Return only schema-declared fields (frozen dataclass → dict)
4. Never return raw sensitive content unless explicitly opted in
"""
from __future__ import annotations


def register_tools(mcp, agent) -> None:
    """Register your domain tools on the MCP server instance.

    ``agent`` is the application core (see agent.py) with access to
    audit, consent, config, and profiles.
    """

    @mcp.tool()
    def hello() -> dict:
        """Scaffold smoke-test tool. Replace with your domain tools."""
        agent.audit.log("hello", agent.orchestrator)
        return {"message": f"${AGENT_NAME_HUMAN} is running", "orchestrator": agent.orchestrator}

    # TODO: Add your domain tools here. See privacy-agent's agent.py for
    # patterns: consent-gated access, classification filtering, redaction,
    # schema-bounded responses.
