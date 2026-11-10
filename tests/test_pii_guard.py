import pytest

from jobomatic.privacy.guard import (
    PIIViolation,
    assert_presence_safe,
    scan_structure,
    scan_text,
)


def test_scan_text_finds_email_and_phone():
    findings = scan_text("Contact me at foo@example.com or 410-555-0142")
    types = {f["type"] for f in findings}
    assert {"email", "phone"} <= types


def test_scan_structure_finds_sensitive_keys():
    data = {
        "email": "foo@example.com",
        "nested": {"phone": "410-555-0142"},
        "safe": "Python developer",
    }
    findings = scan_structure(data)
    paths = {f["source"] for f in findings}
    assert "email" in paths
    assert "nested.phone" in paths


def test_assert_presence_safe_raises_for_pii():
    with pytest.raises(PIIViolation):
        assert_presence_safe({"summary": "email me at foo@example.com"})


def test_assert_presence_safe_accepts_clean_data():
    assert_presence_safe(
        {
            "headline": "Senior Dev",
            "summary": "I build cloud apps",
            "technical_skills": {"backend": ["C#"]},
        }
    )


def test_scan_text_does_not_match_iso_date_segments():
    """Regression: phone regex must not flag digit runs inside ISO dates."""
    findings = scan_text("incident happened on 2026-04-18 at 13:45")
    assert findings == []


def test_scan_text_still_matches_real_phone():
    """The tightened regex must keep flagging genuine phone numbers."""
    findings = scan_text("Call me at 410-555-0142 anytime")
    types = {f["type"] for f in findings}
    assert "phone" in types


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Springfield R3C 0A5", "postal_code"),
        ("Springfield r3c0a5", "postal_code"),
        ("SIN 123-456-789", "sin"),
        ("Lives at 123 Main Street", "street_address"),
        ("45 Portage Ave.", "street_address"),
    ],
)
def test_scan_text_finds_postal_code_sin_and_street_address(text, expected):
    assert expected in {f["type"] for f in scan_text(text)}


def test_scan_text_ignores_non_pii_numbers():
    assert scan_text("Azure AZ-204, C# 14, 252 courses completed, 2026-04-18") == []


def test_email_pattern_does_not_accept_pipe_in_tld():
    assert scan_text("a@b.c|d") == []


def test_findings_and_exception_message_never_contain_raw_values():
    with pytest.raises(PIIViolation) as excinfo:
        assert_presence_safe({"summary": "Call 410-555-0142 or foo@example.com"})
    assert "410-555-0142" not in str(excinfo.value)
    assert "foo@example.com" not in str(excinfo.value)
    for finding in excinfo.value.findings:
        assert "410-555-0142" not in finding["value"]
        assert "foo@example.com" not in finding["value"]
        assert finding["value"][0] in "4f"  # first character kept so it can be located


def test_sensitive_keys_cover_postal_and_birth_fields():
    findings = scan_structure({"postal_code": "R3C0A5", "dob": "1990-01-01"})
    assert {f["source"] for f in findings} == {"postal_code", "dob"}
