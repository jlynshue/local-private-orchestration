"""T-5: file-hash manifest for tamper detection on privacy-critical files.

Mitigation against malicious server replacement (THREAT_MODEL.md T-5). The
manifest covers source files that determine policy:

- Everything in ``src/privacy_agent/``
- Hook scripts in ``hooks/``
- The MCP launcher

Operator workflow:
1. ``privacy-cli manifest install`` writes a fresh manifest at install time
2. SessionStart hook calls ``verify()`` on every Claude Code session start
3. ``privacy-cli manifest verify`` is the on-demand check
4. Mismatch = critical audit event + fail-closed by default

Phase 3 hardening upgrade path: replace this with cosign / Sigstore signing.
The manifest format (sha256sum-compatible) keeps that migration straightforward.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional


# Files that get manifested. Glob patterns relative to the package root
# (the ``privacy-agent/`` directory). Order doesn't matter — sorted at write.
MANIFESTED_PATTERNS: tuple[str, ...] = (
    "src/privacy_agent/*.py",
    "src/privacy_agent/extractors/*.py",
    "hooks/*.py",
    "scripts/launch-privacy-agent.sh",
)


def package_root() -> Path:
    """Best-effort resolution of the privacy-agent project root."""
    # privacy_agent/manifest.py → src/privacy_agent/ → src/ → privacy-agent/
    return Path(__file__).resolve().parents[2]


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_files(root: Optional[Path] = None) -> list[Path]:
    """Return absolute paths of files matching MANIFESTED_PATTERNS, sorted."""
    root = root or package_root()
    out: list[Path] = []
    for pattern in MANIFESTED_PATTERNS:
        for p in sorted(root.glob(pattern)):
            if p.is_file():
                out.append(p)
    return out


def generate(root: Optional[Path] = None) -> dict[str, str]:
    """Compute SHA-256 for every manifested file. Returns rel_path → hash."""
    root = root or package_root()
    manifest: dict[str, str] = {}
    for path in collect_files(root):
        rel = path.relative_to(root)
        manifest[str(rel)] = compute_sha256(path)
    return manifest


def write(manifest: dict[str, str], output: Path) -> None:
    """Write in sha256sum-compatible format: ``<hash>  <relative-path>``."""
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{h}  {p}" for p, h in sorted(manifest.items())]
    output.write_text("\n".join(lines) + "\n")
    try:
        output.chmod(0o600)
    except OSError:
        pass


def parse(path: Path) -> dict[str, str]:
    """Read a sha256sum-format manifest. Returns rel_path → hash."""
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        h, p = parts
        out[p.strip()] = h
    return out


def verify(
    manifest_path: Path,
    root: Optional[Path] = None,
    allow_extras: bool = True,
) -> tuple[bool, list[str]]:
    """Verify that the on-disk files match the manifest.

    Returns ``(valid, mismatch_descriptions)``. Each mismatch is a one-line
    description suitable for surfacing in audit-log warnings or CLI output.

    Args:
        manifest_path: Path to the manifest file (typically
            ``~/.privacy-agent/manifest.sha256``).
        root: Override the package root used to find current files.
            Default: the privacy-agent package root.
        allow_extras: When True, files present on disk but not in the
            manifest are silently allowed (lets the operator add
            non-manifested helper scripts without re-signing). When False,
            extras are flagged as mismatches.
    """
    if not manifest_path.exists():
        return (False, [f"manifest not found at {manifest_path}"])

    expected = parse(manifest_path)
    if not expected:
        return (False, [f"manifest at {manifest_path} is empty or unreadable"])

    root = root or package_root()
    mismatches: list[str] = []

    for rel_path, expected_hash in sorted(expected.items()):
        full = root / rel_path
        if not full.exists():
            mismatches.append(f"missing: {rel_path}")
            continue
        actual = compute_sha256(full)
        if actual != expected_hash:
            mismatches.append(f"changed: {rel_path}")

    if not allow_extras:
        on_disk = {str(p.relative_to(root)) for p in collect_files(root)}
        for rel_path in sorted(on_disk - set(expected)):
            mismatches.append(f"unmanifested: {rel_path}")

    return (len(mismatches) == 0, mismatches)


def install(
    output_path: Optional[Path] = None,
    root: Optional[Path] = None,
) -> Path:
    """Generate a manifest and write it to ``output_path``.

    Default ``output_path`` is ``~/.privacy-agent/manifest.sha256``. Returns
    the path written.
    """
    output_path = output_path or Path("~/.privacy-agent/manifest.sha256").expanduser()
    manifest = generate(root)
    write(manifest, output_path)
    return output_path
