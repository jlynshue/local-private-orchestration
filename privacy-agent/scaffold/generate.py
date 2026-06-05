#!/usr/bin/env python3
"""Generate a new domain-specific MCP agent from the privacy-agent template.

Produces a self-contained project directory with the reusable infrastructure
(audit chain, consent, config, manifest, profiles, red-team scaffold, CI) and
domain-specific stubs the developer fills in.

Usage:
    python scaffold/generate.py \\
        --name "secrets-scanner" \\
        --description "Detects leaked API keys and credentials in codebases" \\
        --output ~/code-projects/projects/active/secrets-scanner \\
        --orchestrators claude_code,codex,goose,cline

The generated project compiles, installs, and passes a minimal test suite
immediately (no domain logic wired yet — just the plumbing).

Compatible orchestrators (MCP stdio):
    claude_code, codex, goose, cline, continue_dev, zed, cursor, aider
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from string import Template
from textwrap import dedent

SCAFFOLD_ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = SCAFFOLD_ROOT / "template"


ORCHESTRATOR_PROFILES = {
    "claude_code": ("uncapped", None),
    "codex": ("confidential", False),
    "goose": ("internal", False),
    "cline": ("confidential", False),
    "continue_dev": ("confidential", False),
    "zed": ("confidential", False),
    "cursor": ("confidential", False),
    "aider": ("internal", False),
}


def to_snake(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_")
    return re.sub(r"([A-Z])", lambda m: "_" + m.group(0).lower(), s).strip("_").lower()


def to_kebab(name: str) -> str:
    return to_snake(name).replace("_", "-")


def generate(
    name: str,
    description: str,
    output: Path,
    orchestrators: list[str],
) -> Path:
    snake = to_snake(name)
    kebab = to_kebab(name)

    if output.exists():
        print(f"error: output directory already exists: {output}", file=sys.stderr)
        sys.exit(1)

    # Copy the template tree
    shutil.copytree(TEMPLATE_DIR, output)

    # Replacement map
    replacements = {
        "AGENT_NAME_KEBAB": kebab,
        "AGENT_NAME_SNAKE": snake,
        "AGENT_NAME_HUMAN": name,
        "AGENT_DESCRIPTION": description,
        "PROFILE_ENTRIES": _generate_profiles(orchestrators),
        "ORCHESTRATOR_LIST": ", ".join(f'"{o}"' for o in orchestrators),
        "KNOWN_ORCHESTRATORS": str(tuple(orchestrators + ["manual"])),
    }

    # Walk and replace in all files
    for path in output.rglob("*"):
        if path.is_file() and path.suffix in (".py", ".toml", ".yaml", ".yml", ".md", ".sh", ".json"):
            try:
                content = path.read_text()
            except UnicodeDecodeError:
                continue
            for key, val in replacements.items():
                content = content.replace(f"{{{{${key}}}}}", val)
                content = content.replace(f"${{{key}}}", val)
                content = content.replace(f"__{key}__", val)
            path.write_text(content)

        # Rename files that contain the placeholder
        if "__AGENT_NAME_SNAKE__" in path.name:
            new_name = path.name.replace("__AGENT_NAME_SNAKE__", snake)
            path.rename(path.parent / new_name)

    # Rename the package directory
    src_pkg = output / "src" / "__AGENT_NAME_SNAKE__"
    if src_pkg.exists():
        src_pkg.rename(output / "src" / snake)

    print(f"generated: {output}")
    print(f"  package: {snake}")
    print(f"  orchestrators: {', '.join(orchestrators)}")
    print()
    print("next steps:")
    print(f"  cd {output}")
    print("  python -m venv .venv && source .venv/bin/activate")
    print('  pip install -e ".[dev]"')
    print("  pytest tests/  # should pass immediately (scaffold tests)")
    print()
    print("then:")
    print(f"  1. Edit src/{snake}/tools.py — define your domain's MCP tools")
    print(f"  2. Edit config/default_patterns.yaml — define your detection patterns")
    print(f"  3. Edit tests/redteam/conftest.py — seed your attack corpus")
    print(f"  4. Run `bash scripts/ci.sh full` to verify everything holds")
    return output


def _generate_profiles(orchestrators: list[str]) -> str:
    lines = []
    for orch in orchestrators:
        cap, excerpt = ORCHESTRATOR_PROFILES.get(orch, ("confidential", False))
        if cap == "uncapped":
            lines.append(f"[profiles.{orch}]")
            lines.append(f"# inherits all defaults")
        else:
            lines.append(f"[profiles.{orch}]")
            if excerpt is not None:
                lines.append(f"enable_excerpt_tool = {str(excerpt).lower()}")
            lines.append(f'classification_cap = "{cap}"')
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate a new MCP agent project")
    parser.add_argument("--name", required=True, help="Human-readable agent name (e.g., 'secrets-scanner')")
    parser.add_argument("--description", required=True, help="One-line description")
    parser.add_argument("--output", required=True, type=Path, help="Target directory (must not exist)")
    parser.add_argument(
        "--orchestrators",
        default="claude_code,codex,goose",
        help="Comma-separated list of orchestrators to generate profiles for",
    )
    args = parser.parse_args()
    orchestrators = [o.strip() for o in args.orchestrators.split(",")]
    generate(args.name, args.description, args.output.expanduser(), orchestrators)


if __name__ == "__main__":
    main()
