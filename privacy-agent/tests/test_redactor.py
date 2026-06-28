"""Tests for the PII redactor."""
from __future__ import annotations

import pytest

from privacy_agent.redactor import default_redactor


def test_default_yaml_loads():
    r = default_redactor()
    res = r.scrub("nothing sensitive here")
    assert res.text == "nothing sensitive here"
    assert res.redactions_applied == 0


def test_redacts_ssn():
    r = default_redactor()
    res = r.scrub("his SSN is 123-45-6789, recorded.")
    assert "[REDACTED:SSN]" in res.text
    assert "123-45-6789" not in res.text
    assert res.redactions_applied >= 1
    assert "SSN" in res.hit_types


def test_redacts_credit_card_separated():
    r = default_redactor()
    res = r.scrub("card 4111-1111-1111-1111 expires soon")
    assert "[REDACTED:CC]" in res.text
    assert "4111" not in res.text


def test_redacts_email():
    r = default_redactor()
    res = r.scrub("contact jane.doe+work@example.com")
    assert "[REDACTED:EMAIL]" in res.text
    assert "jane.doe" not in res.text


def test_redacts_phone():
    r = default_redactor()
    res = r.scrub("call (555) 867-5309 anytime")
    assert "[REDACTED:PHONE]" in res.text


def test_redacts_amount():
    r = default_redactor()
    res = r.scrub("balance is $1,234.56 today")
    assert "[REDACTED:AMOUNT]" in res.text


def test_canary_pattern_tracked_separately():
    r = default_redactor()
    res = r.scrub("seeded marker CANARY-ABCD123 should fire")
    assert res.canary_hits == 1
    assert "CANARY" in res.hit_types
    assert "[REDACTED:CANARY]" in res.text


def test_has_canary_hit_fast_check():
    r = default_redactor()
    assert r.has_canary_hit("CANARY-XYZ9 in the wild") is True
    assert r.has_canary_hit("totally normal payload") is False


def test_empty_input_safe():
    r = default_redactor()
    assert r.scrub("").text == ""


def test_no_double_redaction():
    """Once redacted, the marker should not be re-matched by later patterns."""
    r = default_redactor()
    res = r.scrub("SSN 123-45-6789 only")
    # The redaction marker should appear exactly once.
    assert res.text.count("[REDACTED:SSN]") == 1


def test_multiple_pii_in_one_string():
    r = default_redactor()
    res = r.scrub(
        "John's email j@e.com, phone 555-867-5309, ssn 123-45-6789, "
        "card 4111-1111-1111-1111, balance $42.00"
    )
    assert res.redactions_applied >= 5
    for pii in ("j@e.com", "867-5309", "123-45-6789", "4111-1111", "$42.00"):
        assert pii not in res.text


# --------------------------------------------------------------- secret scanning
# All values below are FAKE/example credentials (AWS uses its own published
# documentation example values). They prove the redactor actually scrubs
# machine credentials crossing the MCP boundary, not just human PII.

# (label, sample_text_containing_a_fake_secret, the_raw_token_that_must_disappear,
#  expected_redaction_marker)
SECRET_CASES = [
    (
        "aws_access_key_id",
        "deploy uses AKIAIOSFODNN7EXAMPLE for the role",
        "AKIAIOSFODNN7EXAMPLE",
        "[REDACTED:AWS_ACCESS_KEY_ID]",
    ),
    (
        "aws_temp_access_key_id",
        "session token starts ASIAY34FZKBOKMUTVV7A here",
        "ASIAY34FZKBOKMUTVV7A",
        "[REDACTED:AWS_ACCESS_KEY_ID]",
    ),
    (
        "aws_secret_access_key",
        "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "[REDACTED:AWS_SECRET_ACCESS_KEY]",
    ),
    (
        "github_pat_classic",
        "export GH_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyz now",
        "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
        "[REDACTED:GITHUB_TOKEN]",
    ),
    (
        "github_oauth",
        "auth gho_16C7e42F292c6912E7710c838347Ae178B4a end",
        "gho_16C7e42F292c6912E7710c838347Ae178B4a",
        "[REDACTED:GITHUB_TOKEN]",
    ),
    (
        "github_fine_grained_pat",
        "token github_pat_11ABCDE0Y0abcdefghijklmnop_qrstuvwxyz1234567890ABCDEFGH set",
        "github_pat_11ABCDE0Y0abcdefghijklmnop_qrstuvwxyz1234567890ABCDEFGH",
        "[REDACTED:GITHUB_TOKEN]",
    ),
    (
        "openai_project_key",
        "OPENAI_API_KEY=sk-proj-abcdEFGH1234ijklMNOP5678qrstUVWXyz done",
        "sk-proj-abcdEFGH1234ijklMNOP5678qrstUVWXyz",
        "[REDACTED:OPENAI_KEY]",
    ),
    (
        "openai_classic_key",
        "use sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD then",
        "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD",
        "[REDACTED:OPENAI_KEY]",
    ),
    (
        "google_api_key",
        "GOOGLE_KEY=AIzaSyDaaaaaaaaaaaaaaaaBBBBBBBBBBBBBBBB done",
        "AIzaSyDaaaaaaaaaaaaaaaaBBBBBBBBBBBBBBBB",
        "[REDACTED:GOOGLE_API_KEY]",
    ),
    (
        "slack_bot_token",
        "slack xoxb-dummy-slack-token-not-real-123456 ok",
        "xoxb-dummy-slack-token-not-real-123456",
        "[REDACTED:SLACK_TOKEN]",
    ),
    (
        "bearer_token",
        "Authorization: Bearer abcdef0123456789ABCDEF0123456789 done",
        "abcdef0123456789ABCDEF0123456789",
        "[REDACTED:BEARER_TOKEN]",
    ),
]


@pytest.mark.parametrize("label,text,raw,marker", SECRET_CASES, ids=[c[0] for c in SECRET_CASES])
def test_secret_credential_is_redacted(label, text, raw, marker):
    """Each shipped secret/credential pattern fires and the raw token is gone."""
    r = default_redactor()
    res = r.scrub(text)
    assert marker in res.text, f"{label}: expected {marker} in {res.text!r}"
    assert raw not in res.text, f"{label}: raw secret {raw!r} leaked through"
    assert res.redactions_applied >= 1


def test_private_key_pem_block_is_redacted():
    """A full PEM private-key block is scrubbed to a single marker — the key
    material (base64 body) must not survive."""
    r = default_redactor()
    pem = (
        "config below\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA1234567890abcdefghijHEADERLINEMUSTGO\n"
        "klmnopqrstuvwxyzABCDEFGHIJKLMNOPbodyMustDisappear+/=\n"
        "-----END RSA PRIVATE KEY-----\n"
        "config above"
    )
    res = r.scrub(pem)
    assert "[REDACTED:PRIVATE_KEY]" in res.text
    assert "MIIEpAIBAAKCAQEA" not in res.text
    assert "bodyMustDisappear" not in res.text
    assert "BEGIN RSA PRIVATE KEY" not in res.text
    # Surrounding non-secret text is preserved.
    assert "config below" in res.text
    assert "config above" in res.text


def test_openssh_private_key_header_redacted():
    r = default_redactor()
    res = r.scrub("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert "[REDACTED:PRIVATE_KEY]" in res.text
    assert "OPENSSH PRIVATE KEY" not in res.text


def test_secrets_do_not_over_redact_benign_text():
    """High-value: the secret patterns must NOT fire on ordinary content, or
    they would silently corrupt legitimate search/index output."""
    r = default_redactor()
    benign = [
        "The quick brown fox jumps over the lazy dog.",
        "Commit 1234567890abcdef1234567890abcdef12345678 landed cleanly.",
        "Please authorize the integration before the demo.",
        "Booking reference ABC123, total was forty dollars.",
        "He said the skylark sang at dawn near the bay.",
    ]
    for text in benign:
        res = r.scrub(text)
        assert "[REDACTED:" not in res.text, f"over-redacted benign text: {res.text!r}"


def test_secret_and_pii_redacted_together():
    r = default_redactor()
    res = r.scrub(
        "leak: AKIAIOSFODNN7EXAMPLE and ghp_1234567890abcdefghijklmnopqrstuvwxyz "
        "for jane@example.com, ssn 123-45-6789"
    )
    assert "[REDACTED:AWS_ACCESS_KEY_ID]" in res.text
    assert "[REDACTED:GITHUB_TOKEN]" in res.text
    assert "[REDACTED:EMAIL]" in res.text
    assert "[REDACTED:SSN]" in res.text
    for raw in ("AKIAIOSFODNN7EXAMPLE", "ghp_1234567890", "jane@example.com", "123-45-6789"):
        assert raw not in res.text
