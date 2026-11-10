"""Profile models, the public view, the checks and the YAML adapter."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from jobomatic.profile import model
from jobomatic.profile.adapters.yaml_vault import YamlVaultProfile
from jobomatic.profile.model import (
    Certification,
    Profile,
    Record,
    Role,
    Rules,
    Visibility,
)
from jobomatic.profile.service import (
    ProfileError,
    check,
    load_profile,
    presence_view,
    public_data,
)
from jobomatic.profile.visibility import public_view
from tests.profile_fixtures import sample_profile


def _all_models() -> list[type[BaseModel]]:
    return [
        obj
        for obj in vars(model).values()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj.__module__ == model.__name__
        and obj
        not in (Record, model.Part, model.PresenceView)  # PresenceView only holds public data
    ]


@pytest.mark.parametrize("cls", _all_models(), ids=lambda c: c.__name__)
def test_every_field_declares_its_visibility(cls: type[BaseModel]) -> None:
    """An unmarked field would silently be private; make adding one a deliberate act."""
    if issubclass(cls, model.Part):
        return
    for name, field in cls.model_fields.items():
        if name == "visibility":
            continue
        marker = (field.json_schema_extra or {}).get("visibility")  # type: ignore[union-attr]
        assert marker in {"public", "private"}, f"{cls.__name__}.{name} has no visibility marker"


def test_public_view_has_only_public_data() -> None:
    profile = sample_profile()
    view = public_data(profile)
    text = json.dumps(view)
    for secret in (
        "sarah.ashford.dev@example.com",
        "555-0142",
        "Sarah Ashford",
        "Northwind",
        "Lakeshore",
        "kubernetes",
        "Pipeline ownership",
        "Worked in a ten-person team",
        "OTHER-1",
    ):
        assert secret not in text, secret
    assert view["identity"]["headline"] == "Full-Stack .NET Developer"
    assert [c["code"] for c in view["certifications"]] == ["AZ-900", "AI-200"]
    assert [r["company"] for r in view["roles"]] == ["Acme Health"]
    assert view["certifications"][1]["domain_coverage"] == [{"domain": "RAG", "status": "Partial"}]
    assert view["certifications"][0]["date"] == "2026-04-18"


def test_presence_view_is_typed_and_holds_only_public_data() -> None:
    view = presence_view(sample_profile())
    assert view.headline == "Full-Stack .NET Developer"
    assert [c.code for c in view.certifications] == ["AZ-900", "AI-200"]
    assert [r.company for r in view.roles] == ["Acme Health"]
    assert view.technical_skills == {"Backend": ["C#", "SQL"]}
    assert [p.name for p in view.projects] == ["CookingTime"]
    text = view.model_dump_json()
    for secret in ("sarah.ashford.dev@example.com", "555-0142", "Northwind", "OTHER-1"):
        assert secret not in text


def test_profile_read_helpers() -> None:
    profile = sample_profile()
    assert [r.company for r in profile.resume_roles] == ["Acme Health"]
    assert [r.company for r in profile.legacy_roles] == ["Northwind Traders"]
    assert [g.skill for g in profile.genuine_gaps] == ["kubernetes"]
    assert profile.keyword_map == {"Cloud": ["Azure"]}
    assert profile.certification("AZ-900").code == "AZ-900"
    assert [d.domain for d in profile.domain_coverage] == ["RAG"]


def test_a_field_added_without_a_marker_stays_out_of_the_public_view() -> None:
    class Extended(model.Project):
        internal_note: str = "do not publish"

    shown = public_view(Extended(name="n", url="https://x", description="d"))
    assert "internal_note" not in shown
    assert shown["name"] == "n"


def test_a_record_can_override_its_default_visibility() -> None:
    hidden = Role(title="t", company="Secret Co", visibility=Visibility.PRIVATE)
    assert public_view(hidden) == {}
    assert model.Education(credential="Diploma").effective_visibility() is Visibility.PRIVATE


def test_legacy_roles_cannot_be_public() -> None:
    with pytest.raises(ValidationError, match="legacy role"):
        Role(title="t", company="c", tier="legacy")


def test_unknown_certifications_cannot_be_public() -> None:
    with pytest.raises(ValidationError, match="not allowed on public surfaces"):
        Certification(code="SECRET-9", status="certified", visibility=Visibility.PUBLIC)


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Role(title="t", company="c", salary="x")  # type: ignore[call-arg]


# -- service checks ---------------------------------------------------------------------------


def _messages(profile: Profile, level: str = "error") -> list[str]:
    return [str(i) for i in check(profile) if i.level == level]


def test_a_clean_profile_has_no_issues() -> None:
    assert check(sample_profile()) == []


def test_empty_name_and_bad_email_are_errors() -> None:
    profile = sample_profile()
    profile.identity.name = " "
    profile.identity.email = "nope"
    assert len(_messages(profile)) == 2


def test_headline_rules_are_enforced() -> None:
    profile = sample_profile(
        rules=Rules(headline_forbidden_words=["Senior"], headline_required_phrase="Full-Stack")
    )
    assert check(profile) == []
    profile.identity.headline = "Senior .NET Developer"
    messages = _messages(profile)
    assert any("'Senior'" in m for m in messages)
    assert any("'Full-Stack'" in m for m in messages)


def test_certified_without_date_and_insecure_url_are_errors() -> None:
    profile = sample_profile()
    profile.certifications[0].date = None
    profile.certifications[0].credential_url = "http://insecure.example.com"
    assert len(_messages(profile)) == 2


def test_a_skill_cannot_be_both_gap_and_resolved() -> None:
    profile = sample_profile()
    profile.skills.gaps.append(model.Gap(skill="Kubernetes", severity="resolved"))
    assert any("both a genuine and a resolved" in m for m in _messages(profile))


def test_duplicate_names_are_errors() -> None:
    profile = sample_profile()
    profile.projects.append(profile.projects[0])
    assert any("projects" in m and "more than once" in m for m in _messages(profile))


def test_role_before_the_resume_window_is_a_warning_not_an_error() -> None:
    profile = sample_profile(rules=Rules(resume_window_start=dt.date(2015, 11, 1)))
    profile.roles[0].dates = "June 2010 - Present"
    assert _messages(profile) == []
    assert any("resume window" in m for m in _messages(profile, "warning"))


def test_load_profile_refuses_errors_but_not_warnings() -> None:
    class Repo:
        def __init__(self, profile: Profile) -> None:
            self._profile = profile

        def load(self) -> Profile:
            return self._profile

        def save(self, profile: Profile) -> None:
            raise AssertionError

    assert load_profile(Repo(sample_profile())).identity.name == "Sarah Ashford"
    broken = sample_profile()
    broken.identity.name = ""
    with pytest.raises(ProfileError, match="identity.name"):
        load_profile(Repo(broken))


# -- YAML adapter -----------------------------------------------------------------------------


def test_yaml_round_trip(tmp_path: Path) -> None:
    repo = YamlVaultProfile(tmp_path)
    original = sample_profile()
    repo.save(original)
    assert repo.load() == original
    assert (tmp_path / "identity.yaml").read_text(encoding="utf-8").startswith("name:")


def test_yaml_files_are_readable_and_lean(tmp_path: Path) -> None:
    YamlVaultProfile(tmp_path).save(sample_profile())
    roles = (tmp_path / "roles.yaml").read_text(encoding="utf-8")
    assert "visibility: private" in roles  # only the legacy role carries an override
    assert roles.count("visibility:") == 1
    assert "tier: resume" not in roles  # defaults are not written
    assert "date: 2026-04-18" in (tmp_path / "certifications.yaml").read_text(encoding="utf-8")


def test_a_missing_file_is_an_error_not_an_empty_section(tmp_path: Path) -> None:
    repo = YamlVaultProfile(tmp_path)
    repo.save(sample_profile())
    (tmp_path / "roles.yaml").unlink()
    with pytest.raises(ProfileError, match="roles.yaml: missing"):
        repo.load()


def test_errors_name_the_file_and_the_field(tmp_path: Path) -> None:
    repo = YamlVaultProfile(tmp_path)
    repo.save(sample_profile())
    path = tmp_path / "certifications.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("status: certified", "status: maybe", 1)
    )
    with pytest.raises(ProfileError) as info:
        repo.load()
    assert "certifications.yaml: invalid" in str(info.value)
    assert "certifications[0].status" in str(info.value)


def test_unparseable_yaml_is_an_error(tmp_path: Path) -> None:
    repo = YamlVaultProfile(tmp_path)
    repo.save(sample_profile())
    (tmp_path / "skills.yaml").write_text("groups: [unclosed", encoding="utf-8")
    with pytest.raises(ProfileError, match="not valid YAML"):
        repo.load()


def test_a_duplicated_key_is_an_error_not_a_silent_override(tmp_path: Path) -> None:
    repo = YamlVaultProfile(tmp_path)
    repo.save(sample_profile())
    path = tmp_path / "identity.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "headline: Something else\n")
    with pytest.raises(ProfileError, match="duplicate key 'headline'"):
        repo.load()


def test_json_schema_carries_the_visibility_markers() -> None:
    schema = Profile.model_json_schema()
    identity = schema["$defs"]["Identity"]["properties"]
    assert identity["email"]["visibility"] == "private"
    assert identity["headline"]["visibility"] == "public"


# -- list items cut at a comma inside brackets ------------------------------------------------


def _with_skill_items(items: list[str]) -> Profile:
    profile = sample_profile()
    profile.skills.keywords[0].keywords = items
    return profile


def test_balanced_brackets_in_list_items_are_fine() -> None:
    profile = _with_skill_items(
        ["NgRx (store, effects, entity)", "C# (Generics (and more))", "Azure"]
    )
    assert check(profile) == []


@pytest.mark.parametrize(
    ("items", "flagged"),
    [
        (["NgRx (store", "effects", "entity)"], 2),  # a list cut at the commas inside the brackets
        (["Docker (3 multi-stage images"], 1),  # never closed
        (["effects)"], 1),  # closed without opening
        (["step 2) then (step 1"], 1),  # closes before it opens
    ],
)
def test_a_list_item_with_unbalanced_brackets_is_an_error(items: list[str], flagged: int) -> None:
    messages = _messages(_with_skill_items(items))
    assert len(messages) == flagged
    assert all("unbalanced brackets" in m and "keywords[0].keywords[" in m for m in messages)


def test_the_error_names_the_list_item_and_says_what_to_do() -> None:
    [message] = _messages(_with_skill_items(["Azure", "NgRx (store"]))
    assert (
        "[1]" in message and "'NgRx (store'" in message and "join it with its neighbour" in message
    )


def test_free_text_with_a_stray_bracket_is_not_checked() -> None:
    profile = sample_profile()
    profile.identity.summary = "Steps: 1) design 2) build"
    assert check(profile) == []


def test_load_profile_refuses_a_cut_list_item(tmp_path: Path) -> None:
    class _Repo:
        def load(self) -> Profile:
            return _with_skill_items(["NgRx (store", "effects", "entity)"])

    with pytest.raises(ProfileError, match="unbalanced brackets"):
        load_profile(_Repo())  # type: ignore[arg-type]
