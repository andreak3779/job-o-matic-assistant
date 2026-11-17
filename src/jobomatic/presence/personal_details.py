"""Fill a skill template's stand-in employers and home city with the candidate's own.

The skills are committed to a public repo, so their templates carry stand-in names
("Acme Software", "the home city"). The candidate's real ones live in the vault
(``profile/employer-names.json`` and ``profile/location-preferences.json``). Shared by the
presence generators whose copy names an employer or the home city (LinkedIn, Indeed/ZipRecruiter).
"""

from __future__ import annotations

import json
import re

from jobomatic import paths

# Employer names used in the skills' templates; ``employer-names.json`` maps each to a real one:
# ``{"Acme Software": "Real Employer Inc.", ...}``.
DEMO_EMPLOYERS = ("Acme Software", "Globex Industrial", "Example Pharmacy")
EMPLOYER_NAMES_FILENAME = "employer-names.json"


def _employer_names() -> dict[str, str]:
    """Stand-in -> real employer names from the vault, or ``{}`` when the file is absent."""
    path = paths.profile_dir() / EMPLOYER_NAMES_FILENAME
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def _home_location() -> str:
    """``"City, ST"`` from the vault's location preferences, or ``""`` when not set."""
    path = paths.profile_dir() / "location-preferences.json"
    if not path.is_file():
        return ""
    home = json.loads(path.read_text(encoding="utf-8")).get("home", {})
    city = str(home.get("label", "")).strip()
    abbreviations = home.get("province_abbreviations") or []
    province = (
        str(abbreviations[0]).upper() if abbreviations else str(home.get("province_label", ""))
    )
    return ", ".join(part for part in (city, province) if part)


def fill_personal_details(text: str, warnings: list[str], where: str) -> str:
    """Replace the template's stand-in employers and home city with the candidate's own.

    A stand-in or ``<...>`` placeholder that survives is reported, so a draft never goes out with
    "Acme Software" or "the home city" in it without a warning saying so.
    """
    for stand_in, real in _employer_names().items():
        text = text.replace(stand_in, real)
    location = _home_location()
    if location:
        text = text.replace("<home city, province>", location).replace("the home city", location)
    leftovers = [name for name in DEMO_EMPLOYERS if name in text]
    leftovers += re.findall(r"<[a-z][^<>\n]*>", text)
    if "the home city" in text:
        leftovers.append("the home city")
    if leftovers:
        warnings.append(
            f"{where} still has template stand-ins ({', '.join(sorted(set(leftovers)))}); add the "
            f"employers to profile/{EMPLOYER_NAMES_FILENAME} and the home city to "
            "profile/location-preferences.json"
        )
    return text
