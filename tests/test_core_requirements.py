"""Which required skills are core (ADR 0021, step C2), and the rating they drive."""

from __future__ import annotations

from jobomatic.bootstrap import load_profile
from jobomatic.fit.engine import rate_parsed_jd
from jobomatic.fit.parser import parse_jd
from jobomatic.fit.soft_skills import is_soft_skill


def _jd(title: str, *required: str, extra: str = "") -> str:
    lines = "".join(f"- {line}\n" for line in required)
    return f"# {title}\n\n## Requirements\n{lines}\n{extra}"


def test_a_skill_named_in_the_title_is_core() -> None:
    lines = [f"Experience with Tool{i}" for i in range(6)] + ["Kubernetes"]
    parsed = parse_jd(_jd("Kubernetes Platform Engineer", *lines))
    assert "kubernetes" in parsed.core_skills


def test_the_first_five_required_lines_are_core_and_the_sixth_is_not() -> None:
    parsed = parse_jd(_jd("Dev", "C#", "SQL", "Angular", "Docker", "Git", "Terraform"))
    assert {"c#", "sql", "angular", "docker", "git"} <= parsed.core_skills
    assert "terraform" not in parsed.core_skills


def test_every_skill_on_a_first_five_line_is_core_whatever_the_count() -> None:
    parsed = parse_jd(_jd("Dev", "Proficient in C#, SQL, Angular and Docker", "Git"))
    assert {"c#", "sql", "angular", "docker", "git"} <= parsed.core_skills


def test_a_years_or_degree_line_still_uses_up_one_of_the_first_five() -> None:
    parsed = parse_jd(
        _jd("Dev", "5+ years of experience", "Bachelor's degree", "C#", "SQL", "Angular", "Docker")
    )
    assert "angular" in parsed.core_skills
    assert "docker" not in parsed.core_skills


def test_a_line_with_a_years_figure_makes_its_skill_core_even_late_in_the_list() -> None:
    parsed = parse_jd(
        _jd("Dev", "C#", "SQL", "Angular", "Docker", "Git", "Jenkins", "3+ years of Terraform")
    )
    assert "terraform" in parsed.core_skills
    assert "jenkins" not in parsed.core_skills


def test_a_skill_mentioned_on_two_lines_anywhere_in_the_posting_is_core() -> None:
    extra = "## Responsibilities\n- Operate our Kubernetes clusters\n"
    parsed = parse_jd(
        _jd("Dev", "C#", "SQL", "Angular", "Docker", "Git", "Kubernetes", extra=extra)
    )
    assert "kubernetes" in parsed.core_skills


def test_soft_skill_lines_are_never_core_even_in_the_first_five() -> None:
    parsed = parse_jd(_jd("Dev", "Excellent communication", "C#", "Interpersonal skills"))
    assert parsed.core_skills == {"c#"}


def test_soft_skill_phrases_come_from_the_json_list() -> None:
    assert is_soft_skill("Ability to work independently and collaboratively")
    assert not is_soft_skill("Strong SQL Server skills")


def test_soft_skill_lines_are_listed_and_do_not_affect_the_rating() -> None:
    """The posting that rated Pass on three soft-skill rows alone (ADR 0021, then ADR 0023)."""
    technical = ["C#", "SQL", "Angular"]
    soft = [
        "Excellent communication",
        "Interpersonal skills",
        "Ability to work independently and collaboratively in a fast-paced environment",
    ]
    with_soft = parse_jd(_jd("Dev", *technical, *soft))
    without = parse_jd(_jd("Dev", *technical))
    assert with_soft.required_for_rating == technical
    assert [s.kind for s in with_soft.soft_requirements] == ["soft skill"] * 3
    profile = load_profile()
    assert rate_parsed_jd(with_soft, profile).rating == rate_parsed_jd(without, profile).rating


def test_a_missing_core_skill_makes_the_posting_a_stretch_and_a_late_one_does_not() -> None:
    covered = ["C#", "SQL", "Angular", "Docker", "Git"]
    early = parse_jd(_jd("Dev", "Rust", *covered, "Python", "Jira"))
    late = parse_jd(_jd("Dev", *covered, "Python", "Jira", "Rust"))
    profile = load_profile()
    assert rate_parsed_jd(early, profile).rating == "Stretch"  # Rust is on line 1: core
    assert rate_parsed_jd(late, profile).rating == "Worth a try"  # Rust is on line 8: tail


def test_two_missing_core_skills_make_the_posting_a_pass() -> None:
    parsed = parse_jd(_jd("Dev", "Rust", "Kotlin", "C#", "SQL", "Angular", "Docker", "Git"))
    assert rate_parsed_jd(parsed, load_profile()).rating == "Pass"
