"""Render a certification's status as the markdown cell text used in the cert tables.

Shared by the profile renderer and the LinkedIn draft generation, so both derive it from the
profile's certifications instead of re-parsing rendered markdown.
"""

from __future__ import annotations

from jobomatic.profile.model import Certification, CertStatus


def cert_status_cell(c: Certification) -> str:
    if c.status == CertStatus.CERTIFIED:
        date_str = f"{c.date:%B} {c.date.day}, {c.date.year}" if c.date else ""
        cred = f" — [Credential]({c.credential_url})" if c.credential_url else ""
        return f"**Certified {date_str}**{cred}"
    if c.status == CertStatus.IN_PROGRESS:
        return f"**Active target** — {c.notes or ''}"
    return c.notes or "Not pursuing"


def cert_status_rows(cert_registry: list[Certification]) -> list[tuple[str, str]]:
    return [(c.code, cert_status_cell(c)) for c in cert_registry]
