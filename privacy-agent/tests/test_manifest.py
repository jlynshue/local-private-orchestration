"""Tests for the T-5 file-hash manifest."""
from __future__ import annotations

import stat
from pathlib import Path


from privacy_agent import manifest


def _make_fake_repo(root: Path) -> Path:
    """Build a tiny fake project that matches MANIFESTED_PATTERNS structure."""
    (root / "src" / "privacy_agent").mkdir(parents=True)
    (root / "src" / "privacy_agent" / "extractors").mkdir()
    (root / "hooks").mkdir()
    (root / "scripts").mkdir()

    (root / "src" / "privacy_agent" / "agent.py").write_text("# agent\n")
    (root / "src" / "privacy_agent" / "consent.py").write_text("# consent\n")
    (root / "src" / "privacy_agent" / "extractors" / "text.py").write_text("# text\n")
    (root / "hooks" / "pre_tool_use.py").write_text("#!/usr/bin/env python3\n")
    (root / "scripts" / "launch-privacy-agent.sh").write_text("#!/usr/bin/env bash\n")
    return root


def test_collect_files_picks_up_patterns(tmp_path: Path):
    root = _make_fake_repo(tmp_path)
    files = manifest.collect_files(root)
    rels = sorted(str(p.relative_to(root)) for p in files)
    assert rels == [
        "hooks/pre_tool_use.py",
        "scripts/launch-privacy-agent.sh",
        "src/privacy_agent/agent.py",
        "src/privacy_agent/consent.py",
        "src/privacy_agent/extractors/text.py",
    ]


def test_generate_returns_hashes_for_each_file(tmp_path: Path):
    root = _make_fake_repo(tmp_path)
    m = manifest.generate(root)
    assert len(m) == 5
    for hash_value in m.values():
        assert len(hash_value) == 64  # SHA-256 hex


def test_write_and_parse_round_trip(tmp_path: Path):
    root = _make_fake_repo(tmp_path)
    m = manifest.generate(root)
    out = tmp_path / "manifest.sha256"
    manifest.write(m, out)
    parsed = manifest.parse(out)
    assert parsed == m


def test_write_uses_0600(tmp_path: Path):
    root = _make_fake_repo(tmp_path)
    out = tmp_path / "manifest.sha256"
    manifest.write(manifest.generate(root), out)
    mode = out.stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


def test_verify_clean(tmp_path: Path):
    root = _make_fake_repo(tmp_path)
    out = tmp_path / "manifest.sha256"
    manifest.write(manifest.generate(root), out)
    ok, mismatches = manifest.verify(out, root=root)
    assert ok is True
    assert mismatches == []


def test_verify_detects_modified_file(tmp_path: Path):
    root = _make_fake_repo(tmp_path)
    out = tmp_path / "manifest.sha256"
    manifest.write(manifest.generate(root), out)

    # Tamper with one of the manifested files.
    (root / "src" / "privacy_agent" / "agent.py").write_text("# tampered\n")

    ok, mismatches = manifest.verify(out, root=root)
    assert ok is False
    assert any("agent.py" in m and m.startswith("changed:") for m in mismatches)


def test_verify_detects_missing_file(tmp_path: Path):
    root = _make_fake_repo(tmp_path)
    out = tmp_path / "manifest.sha256"
    manifest.write(manifest.generate(root), out)

    (root / "hooks" / "pre_tool_use.py").unlink()

    ok, mismatches = manifest.verify(out, root=root)
    assert ok is False
    assert any("pre_tool_use.py" in m and m.startswith("missing:") for m in mismatches)


def test_verify_returns_false_when_manifest_absent(tmp_path: Path):
    ok, mismatches = manifest.verify(tmp_path / "nonexistent.sha256", root=tmp_path)
    assert ok is False
    assert any("manifest not found" in m for m in mismatches)


def test_verify_allow_extras_default(tmp_path: Path):
    root = _make_fake_repo(tmp_path)
    out = tmp_path / "manifest.sha256"
    manifest.write(manifest.generate(root), out)

    # New file added after manifest install — default allows it.
    (root / "src" / "privacy_agent" / "newmod.py").write_text("# new\n")

    ok, mismatches = manifest.verify(out, root=root, allow_extras=True)
    assert ok is True
    assert mismatches == []


def test_verify_strict_flags_extras(tmp_path: Path):
    root = _make_fake_repo(tmp_path)
    out = tmp_path / "manifest.sha256"
    manifest.write(manifest.generate(root), out)
    (root / "src" / "privacy_agent" / "newmod.py").write_text("# new\n")

    ok, mismatches = manifest.verify(out, root=root, allow_extras=False)
    assert ok is False
    assert any("unmanifested" in m for m in mismatches)


def test_install_writes_to_default_location(tmp_path: Path, monkeypatch):
    """install() respects the explicit output path and the file count."""
    root = _make_fake_repo(tmp_path)
    out_path = tmp_path / "out" / "manifest.sha256"
    written = manifest.install(output_path=out_path, root=root)
    assert written == out_path
    assert out_path.exists()
    parsed = manifest.parse(out_path)
    assert len(parsed) == 5


def test_real_package_root_is_resolvable():
    """package_root() should locate the privacy-agent project from inside the package."""
    root = manifest.package_root()
    # The directory should contain pyproject.toml and src/privacy_agent/.
    assert (root / "pyproject.toml").exists()
    assert (root / "src" / "privacy_agent").is_dir()


def test_verify_real_package_after_install(tmp_path: Path):
    """End-to-end: install manifest from real package, verify, get clean."""
    out = tmp_path / "manifest.sha256"
    manifest.install(output_path=out)
    ok, mismatches = manifest.verify(out)
    assert ok is True, f"unexpected mismatches: {mismatches}"
