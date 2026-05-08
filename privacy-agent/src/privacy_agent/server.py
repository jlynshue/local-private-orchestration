"""MCP stdio server — registers the 8 privacy-agent tools with FastMCP.

Run via the launch script (see scripts/launch-privacy-agent.sh) which sets
``PRIVACY_AGENT_ORCHESTRATOR`` so per-orchestrator profiles (M2) apply
deterministically.

The 8 tools are thin wrappers around handlers on ``PrivacyAgent``. Each
handler returns a ``ToolResponse(payload, provenance_id)``; the server
unwraps to ``payload``. Errors raise as exceptions which the MCP framework
serializes back to the orchestrator.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from .agent import (
    ClassificationBlocked,
    ConsentRequired,
    PrivacyAgent,
    ToolDisabled,
    build_agent,
)

logger = logging.getLogger(__name__)


def _format_error(exc: Exception) -> dict[str, Any]:
    return {
        "error": exc.__class__.__name__,
        "message": str(exc),
    }


def register_tools(mcp, agent: PrivacyAgent) -> None:
    """Register the 8 tools on a FastMCP instance.

    Lifted out of ``main()`` so unit tests can pass a mock MCP and exercise
    the registration without standing up a transport.
    """

    @mcp.tool()
    def privacy_search(
        query: str,
        scope: Optional[str] = None,
        max_results: Optional[int] = None,
        classification_filter: Optional[list[str]] = None,
        file_types: Optional[list[str]] = None,
    ) -> dict:
        """Search the indexed corpus. Returns ranked results with metadata and
        redacted snippets. Never returns raw file content."""
        try:
            return agent.handle_search(
                query=query,
                scope=scope,
                max_results=max_results,
                classification_filter=classification_filter,
                file_types=file_types,
            ).payload
        except (ConsentRequired, ToolDisabled, ClassificationBlocked) as e:
            return _format_error(e)

    @mcp.tool()
    def privacy_index_volume(
        volume_path: str,
        volume_id: Optional[str] = None,
        include_patterns: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
        force_reindex: bool = False,
    ) -> dict:
        """Crawl and index a volume. Requires active 'index' consent for the path."""
        try:
            return agent.handle_index_volume(
                volume_path=volume_path,
                volume_id=volume_id,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                force_reindex=force_reindex,
            ).payload
        except (ConsentRequired, FileNotFoundError) as e:
            return _format_error(e)

    @mcp.tool()
    def privacy_read_excerpt(
        volume_id: str,
        relative_path: str,
        page: Optional[int] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        max_chars: Optional[int] = None,
    ) -> dict:
        """Read a specific portion of a file. Disabled by default in Phase 1."""
        try:
            return agent.handle_read_excerpt(
                volume_id=volume_id,
                relative_path=relative_path,
                page=page,
                start_line=start_line,
                end_line=end_line,
                max_chars=max_chars,
            ).payload
        except (ToolDisabled, ConsentRequired, ClassificationBlocked, FileNotFoundError) as e:
            return _format_error(e)

    @mcp.tool()
    def privacy_list_volumes() -> dict:
        """List indexed volumes with metadata."""
        return agent.handle_list_volumes().payload

    @mcp.tool()
    def privacy_get_consent(path: str, scope: str, request: bool = False) -> dict:
        """Check (or request) consent for a path/scope. Phase 1 doesn't prompt
        via stdio — see returned ``instructions`` for out-of-band grant."""
        return agent.handle_get_consent(path=path, scope=scope, request=request).payload

    @mcp.tool()
    def privacy_audit_log(
        since: Optional[str] = None,
        until: Optional[str] = None,
        action_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        """Query the audit trail."""
        return agent.handle_audit_log(
            since=since,
            until=until,
            action_filter=action_filter,
            severity_filter=severity_filter,
            limit=limit,
        ).payload

    @mcp.tool()
    def privacy_classify(
        path: str,
        set_level: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> dict:
        """Get or set the sensitivity classification for a path."""
        try:
            return agent.handle_classify(
                path=path, set_level=set_level, reason=reason
            ).payload
        except ValueError as e:
            return _format_error(e)

    @mcp.tool()
    def privacy_file_summary(volume_id: str, relative_path: str) -> dict:
        """Return a sanitized summary of an indexed file."""
        try:
            return agent.handle_file_summary(
                volume_id=volume_id, relative_path=relative_path
            ).payload
        except (FileNotFoundError, ClassificationBlocked) as e:
            return _format_error(e)


def main() -> None:  # pragma: no cover (entry point; covered by launch tests)
    """Entry point used by the launch script and the ``privacy-agent`` console script."""
    from mcp.server.fastmcp import FastMCP

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config_path_env = os.getenv("PRIVACY_AGENT_CONFIG")
    config_path = Path(config_path_env).expanduser() if config_path_env else None
    db_path_env = os.getenv("PRIVACY_AGENT_DB")
    db_path = Path(db_path_env).expanduser() if db_path_env else None
    key = os.getenv("PRIVACY_AGENT_DB_KEY")

    agent = build_agent(db_path=db_path, config_path=config_path, encryption_key=key)

    # Verify audit chain integrity at startup. Broken chain blocks tools.
    valid, broken = agent.audit.verify_chain_integrity()
    if not valid:
        logger.error(
            "audit chain integrity failed at startup; %d broken entries: %s",
            len(broken),
            broken[:5],
        )
        # Still start so the operator can use privacy_audit_log to investigate.

    mcp = FastMCP("privacy-agent")
    register_tools(mcp, agent)
    logger.info(
        "privacy-agent starting: orchestrator=%s, excerpt_enabled=%s",
        agent.orchestrator,
        agent._excerpt_enabled(),
    )
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
