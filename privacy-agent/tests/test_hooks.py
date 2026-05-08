"""Tests for the Claude Code hook scripts (M1.7)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path



HOOKS_DIR = Path(__file__).parent.parent / "hooks"


def _run_hook(hook_name: str, event: dict) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook_name)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode, proc.stdout, proc.stderr


# -- PreToolUse --

def test_pre_tool_use_blocks_bash_cat_against_volumes():
    code, out, _ = _run_hook(
        "pre_tool_use.py",
        {"tool_name": "Bash", "tool_input": {"command": "cat /Volumes/Backup/Tax/2024.pdf"}},
    )
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "privacy-agent" in decision["reason"]
    assert code == 1


def test_pre_tool_use_blocks_compound_bash():
    """Even chained / piped bypasses must trip the regex."""
    code, out, _ = _run_hook(
        "pre_tool_use.py",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "echo start && strings /Volumes/Backup/Tax/2024.pdf | head -50"
            },
        },
    )
    assert json.loads(out)["decision"] == "block"
    assert code == 1


def test_pre_tool_use_allows_bash_ls_on_sensitive_path():
    """Listing is fine — only content-reading verbs are gated."""
    code, out, _ = _run_hook(
        "pre_tool_use.py",
        {"tool_name": "Bash", "tool_input": {"command": "ls /Volumes/Backup/Tax"}},
    )
    assert json.loads(out)["decision"] == "allow"
    assert code == 0


def test_pre_tool_use_allows_cat_on_innocuous_path():
    code, out, _ = _run_hook(
        "pre_tool_use.py",
        {"tool_name": "Bash", "tool_input": {"command": "cat /tmp/scratch/note.txt"}},
    )
    assert json.loads(out)["decision"] == "allow"


def test_pre_tool_use_blocks_read_against_sensitive_dir():
    code, out, _ = _run_hook(
        "pre_tool_use.py",
        {
            "tool_name": "Read",
            "tool_input": {"file_path": "/Volumes/Backup/Medical/labs.pdf"},
        },
    )
    assert json.loads(out)["decision"] == "block"
    assert code == 1


def test_pre_tool_use_allows_other_tools():
    code, out, _ = _run_hook(
        "pre_tool_use.py",
        {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/foo.py"}},
    )
    assert json.loads(out)["decision"] == "allow"


def test_pre_tool_use_empty_stdin_allows():
    """Defensive: empty input fails open (don't break the whole session)."""
    code, out, _ = _run_hook("pre_tool_use.py", {})  # encoded as "{}"; not strictly empty
    decision = json.loads(out)
    assert decision["decision"] == "allow"


# -- PostToolUse --

def test_post_tool_use_silent_on_clean_payload():
    code, out, err = _run_hook(
        "post_tool_use.py",
        {"tool_name": "privacy_search", "tool_result": {"results": []}},
    )
    assert code == 0
    # Clean payload — no warnings.
    assert "CRITICAL" not in err
    assert "WARNING" not in err


def test_post_tool_use_warns_on_canary_in_response(tmp_path: Path):
    code, out, err = _run_hook(
        "post_tool_use.py",
        {
            "tool_name": "Read",
            "tool_result": {"content": "leaked CANARY-ABCD1234 from somewhere"},
        },
    )
    # Hook never blocks (returns 0) but stderr warns.
    assert code == 0
    assert "CRITICAL" in err
    assert "canary" in err.lower()


# -- SessionStart --

def test_session_start_runs_and_exits_zero():
    code, out, err = _run_hook("session_start.py", {})
    assert code == 0
    # Stderr summary is present.
    assert "privacy-agent" in err
