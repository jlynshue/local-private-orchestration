"""Tests for the PII redactor."""
from __future__ import annotations

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
