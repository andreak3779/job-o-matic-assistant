"""Education and years lines: read as soft requirements, never scored (ADR 0021, step C1)."""

from __future__ import annotations

import pytest

from jobomatic.fit.parser import parse_jd
from jobomatic.fit.soft_requirements import (
    classify,
    classify_optional,
    is_education,
    minimum_years,
    soft_skill,
    title_level,
)


@pytest.mark.parametrize(
    "line,expected",
    [
        ("5+ years of C# development", 5),
        ("Minimum 3 years' experience", 3),
        ("7-10 years in software development", 7),
        ("6–8 years of professional experience in software development.", 6),  # en dash
        ("3+ years or equivalent", 3),
        ("at least 2 years of Azure", 2),
        ("Senior-level experience", 5),
        ("Proficient in C# with 4 yrs of experience", 4),
        ("Strong C# skills", None),
    ],
)
def test_the_years_figure_is_the_minimum(line, expected):
    assert minimum_years(line) == expected


def test_a_senior_level_line_with_a_figure_uses_the_figure():
    assert minimum_years("Senior-level developer with 8+ years") == 8


@pytest.mark.parametrize(
    "line",
    [
        "Bachelor's degree in computer science",
        "Master's degree or higher",
        "College diploma or university degree",
        "Computer science degree or equivalent practical experience",
        "Azure certification",
        "Post-secondary education",
    ],
)
def test_education_lines_are_recognised(line):
    assert is_education(line)


@pytest.mark.parametrize("line", ["Strong C# skills", "Experience with Docker", "Mastering SQL"])
def test_skill_lines_are_not_education(line):
    assert not is_education(line)


@pytest.mark.parametrize(
    "line",
    [
        "Bachelor's degree or equivalent",
        "Degree in computer science or related field",
        "Diploma or equivalent experience",
    ],
)
def test_the_three_alternative_wordings_mark_equivalent_accepted(line):
    (soft,) = classify(line)
    assert (soft.kind, soft.note) == ("education", "equivalent accepted")


def test_a_degree_with_no_alternative_says_to_check_it_yourself():
    (soft,) = classify("Bachelor's degree in computer science")
    assert soft.note == "stated as required — check this yourself"


def test_one_line_can_hold_a_years_entry_and_an_education_entry():
    kinds = [s.kind for s in classify("Bachelor's degree and 5+ years of experience")]
    assert kinds == ["years", "education"]


def test_a_senior_level_line_is_read_as_five_years_and_says_so():
    (soft,) = classify("Senior-level experience")
    assert (soft.minimum_years, soft.note) == (5, "senior-level, read as 5+ years")


# ── in a parsed posting ──────────────────────────────────────────────────────


def _jd(*lines: str) -> str:
    return "# Dev\n\n## Requirements\n" + "".join(f"- {line}\n" for line in lines)


def test_a_years_line_with_no_skill_is_listed_and_not_scored():
    parsed = parse_jd(_jd("6–8 years of professional experience in software development.", "C#"))
    assert parsed.required == ["C#"]
    assert parsed.unscored_required == ()
    assert [(s.kind, s.minimum_years) for s in parsed.soft_requirements] == [("years", 6)]


def test_a_years_line_that_names_a_skill_is_scored_for_the_skill_and_listed():
    parsed = parse_jd(_jd("5+ years of C#"))
    assert parsed.required == ["C#"]
    assert [(s.kind, s.minimum_years) for s in parsed.soft_requirements] == [("years", 5)]


def test_a_range_before_a_skill_does_not_leave_a_dash_in_the_skill():
    parsed = parse_jd(_jd("6–8 years C#"))
    assert parsed.required == ["C#"]


def test_digits_that_belong_to_the_line_are_not_stripped_with_the_bullet():
    parsed = parse_jd(_jd("3D modeling"))
    assert "3D modeling" in parsed.required


def test_a_numbered_list_marker_is_still_removed():
    parsed = parse_jd("# Dev\n\n## Requirements\n1. Docker\n2) Python\n")
    assert parsed.required == ["Docker", "Python"]


def test_an_education_line_in_the_nice_section_is_listed_as_optional_and_never_scored():
    parsed = parse_jd("# Dev\n\n## Requirements\n- C#\n\n## Nice to have\n- Master's degree\n")
    assert [(s.kind, s.note.startswith("optional")) for s in parsed.soft_requirements] == [
        ("education", True)
    ]
    assert parsed.nice_to_have == []


@pytest.mark.parametrize(
    "line",
    [
        "Degree in Computer Science, or a related program",
        "Diploma in IT or related discipline",
        "Bachelor's degree in engineering or a related area",
    ],
)
def test_or_a_related_program_discipline_or_area_marks_the_degree_as_accepting_alternatives(line):
    (found,) = classify(line)
    assert found.note == "equivalent accepted"


def test_a_certificate_or_training_line_is_listed_as_optional_education():
    (found,) = classify_optional(
        "Certification or formal training in Agile, DevOps is considered an asset."
    )
    assert found.kind == "education" and found.note.startswith("optional")


def test_a_line_without_education_wording_gives_no_optional_entry():
    assert classify_optional("Experience with React") == []


@pytest.mark.parametrize(
    "title",
    [
        "Software Development Lead",
        "Principal Developer",
        "Staff Engineer",
        "IT Manager",
        "Senior .NET Full Stack Engineer",
    ],
)
def test_a_senior_word_in_the_title_is_listed_as_a_level(title):
    found = title_level(title)
    assert found is not None and found.kind == "level" and found.line == title


@pytest.mark.parametrize("title", ["Software Developer", "Full-Stack .NET Developer", "Leader"])
def test_an_ordinary_title_has_no_level(title):
    assert title_level(title) is None


# ── soft skills: listed, never scored (ADR 0023) ──


def _soft(parsed):
    return [(r.kind, r.line) for r in parsed.soft_requirements if r.kind == "soft skill"]


def test_a_soft_skills_section_is_listed_whole_and_never_scored():
    parsed = parse_jd(
        "Dev\n\n## Requirements\n- C#\n\n## Soft Skills\n- Curious mindset\n- Team spirit\n"
        "\n## Nice to have\n- Docker\n"
    )
    assert parsed.required_for_rating == ["C#"]
    assert parsed.nice_to_have == ["Docker"]
    assert _soft(parsed) == [("soft skill", "Curious mindset"), ("soft skill", "Team spirit")]


@pytest.mark.parametrize(
    "heading", ["Personal Qualities", "Personal Attributes", "Interpersonal Skills", "Competencies"]
)
def test_other_soft_skill_headings_work_the_same_way(heading):
    parsed = parse_jd(f"Dev\n\n## Requirements\n- C#\n\n## {heading}\n- Warm and approachable\n")
    assert parsed.required_for_rating == ["C#"]
    assert _soft(parsed) == [("soft skill", "Warm and approachable")]


def test_a_technical_competencies_heading_is_not_a_soft_skills_section():
    parsed = parse_jd("Dev\n\n## Technical Competencies\n- Docker\n")
    assert _soft(parsed) == []
    assert parsed.required_for_rating == [] and parsed.nice_to_have == []


def test_a_soft_skill_line_in_a_technical_list_is_listed_not_scored():
    parsed = parse_jd(
        "Dev\n\n## Requirements\n- C#\n- Strong communication and collaboration skills\n"
        "- Strong debugging, analytical, and problem-solving skills\n"
    )
    assert parsed.required_for_rating == ["C#"]
    assert len(_soft(parsed)) == 2


def test_a_soft_skill_line_among_the_nice_to_haves_is_listed_not_scored():
    parsed = parse_jd("Dev\n\n## Nice to have\n- Docker\n- Self-starter with initiative\n")
    assert parsed.nice_to_have == ["Docker"]
    assert _soft(parsed) == [("soft skill", "Self-starter with initiative")]


def test_a_line_that_names_a_skill_as_well_keeps_scoring_that_skill():
    parsed = parse_jd(
        "Dev\n\n## Requirements\n- Strong communication skills when working with Azure teams\n"
    )
    assert "Azure" in parsed.required_for_rating
    assert _soft(parsed) == []


def test_a_years_line_with_a_soft_phrase_still_reads_as_years():
    parsed = parse_jd("Dev\n\n## Requirements\n- 5+ years of leadership experience\n")
    assert [r.kind for r in parsed.soft_requirements] == ["years"]


def test_soft_skill_lines_do_not_use_up_the_first_five_required_lines():
    lines = [
        "Excellent communication",
        "Interpersonal skills",
        "C#",
        "SQL",
        "Angular",
        "Docker",
        "Git",
        "Rust",
    ]
    parsed = parse_jd("Dev\n\n## Requirements\n" + "".join(f"- {line}\n" for line in lines))
    # Rust is the sixth technical line: still the tail, as when no soft lines come first
    assert "rust" not in parsed.core_skills
    assert {"c#", "sql", "angular", "docker", "git"} <= parsed.core_skills


@pytest.mark.parametrize(
    "line",
    [
        "Strong analytical skills",
        "Excellent verbal skills",
        "A self-starter",
        "Proactive attitude",
        # real posting wording: a hyphenated phrase, a pair, and a language line
        "Superlative organizational and time-management skills, including independent "
        "management of deadlines.",
        "Excellent written and spoken English.",
    ],
)
def test_the_phrases_added_for_adr_0023_are_recognised(line):
    from jobomatic.fit.soft_skills import is_soft_skill

    assert is_soft_skill(line)


def test_a_soft_skill_entry_is_labelled_and_never_carries_years():
    entry = soft_skill("Excellent communication")
    assert (entry.kind, entry.minimum_years) == ("soft skill", None)


def test_a_posting_that_ends_its_requirements_with_qualities_lists_them_instead_of_scoring_them():
    parsed = parse_jd(
        "# Position\nWeb Developer\n\nRequirements:\n"
        "- 5+ years of professional experience with C# web development.\n"
        "- Superlative organizational and time-management skills, including independent "
        "management of deadlines.\n"
        "- Excellent written and spoken English.\n"
    )
    assert not [r for r in parsed.required if "english" in r or "organizational" in r]
    lines = [s.line for s in parsed.soft_requirements if s.kind == "soft skill"]
    assert len(lines) == 2
