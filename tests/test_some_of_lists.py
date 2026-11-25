"""A "some of" list is one requirement over a pool of names (ADR 0038)."""

from __future__ import annotations

import pytest

from jobomatic.commands.cover_letter import _display_skill
from jobomatic.fit.engine import rate_fit, rate_parsed_jd, render_fit_table, skill_match_terms
from jobomatic.fit.parser import parse_jd
from jobomatic.fit.terms import load_satisfied_by, some_of_list
from tests.profile_fixtures import Project, SkillCategory, WorkExperience, make_profile

LINE = (
    "Experience with some of what we work with day-to-day: PHP, Drupal, JavaScript, NodeJS, "
    "React, NextJS, AWS, Docker, Lando"
)
NAMES = [
    "PHP",
    "Drupal",
    "JavaScript",
    "NodeJS",
    "React",
    "NextJS",
    "AWS",
    "Docker",
    "Lando",
]


def _profile(*bullets: str, courses: list[str] | None = None, **extra):
    roles = [WorkExperience(title="Dev", company="Acme", dates="2020", bullets=list(bullets))]
    return make_profile(
        experience=roles,
        technical_skills=[SkillCategory("Courses", courses or [])],
        **extra,
    )


def _posting(*lines: str) -> str:
    return "Dev\n\n## Requirements\n" + "".join(f"- {line}\n" for line in lines)


def test_every_listed_name_is_kept_known_or_not() -> None:
    assert some_of_list(LINE) == NAMES


@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("Experience with some or all of: C#, SQL, and Azure.", ["C#", "SQL", "Azure"]),
        ("Knows a few of these: Git, Docker or Kubernetes, etc.", ["Git", "Docker", "Kubernetes"]),
        (
            "Several of the following: AWS (Lambda, S3), Docker, Redis. We train the rest.",
            ["AWS (Lambda, S3)", "Docker", "Redis"],
        ),
        ("Some of our stack: .NET, Node.js, SQL", [".NET", "Node.js", "SQL"]),
        ("Some of the following - PHP, Drupal, AWS", ["PHP", "Drupal", "AWS"]),
        ("Some of our stack (PHP, AWS (S3), Docker) in production", ["PHP", "AWS (S3)", "Docker"]),
        ("Some of: PHP, Drupal, AWS - we will teach you the rest", ["PHP", "Drupal", "AWS"]),
        ("Some of: PHP, Drupal, AWS (etc.)", ["PHP", "Drupal", "AWS"]),
    ],
)
def test_some_of_wordings(sentence: str, expected: list[str]) -> None:
    assert some_of_list(sentence) == expected


@pytest.mark.parametrize(
    "sentence",
    [
        # no colon: no list follows
        "Exposure to the following for some or all of that time",
        "Some of our product areas lean more front-end, others more back-end",
        # not skills
        "Some of our benefits include: health, dental, and parking",
        # too short to be a pool
        "Some of: Python, Go",
        # prose, not names
        "Some of your time: writing the services our customers depend on, Docker, SQL",
        "Experience with any of: PHP, Drupal, JavaScript",
    ],
)
def test_other_sentences_are_not_some_of_lists(sentence: str) -> None:
    assert some_of_list(sentence) is None


def test_the_parser_makes_one_rated_item_and_keeps_the_flat_names() -> None:
    parsed = parse_jd(_posting(LINE, "Git"))
    assert parsed.required_for_rating == ["some of: " + " / ".join(NAMES), "Git"]
    assert parsed.required == [*NAMES, "Git"]


def test_two_names_in_production_meet_the_list_and_claim_only_those() -> None:
    profile = _profile("Built services in PHP and Docker")
    result = rate_parsed_jd(parse_jd(_posting(LINE)), profile)
    [row] = result.required
    assert (row.status, row.rating_status) == ("match", "match")
    assert row.skill == "php / docker"
    assert row.evidence == "Acme: production"
    assert len(row.members) == len(NAMES)


def test_one_name_in_production_counts_as_partial_but_stays_truthful() -> None:
    result = rate_parsed_jd(parse_jd(_posting(LINE)), _profile("Built services in PHP"))
    [row] = result.required
    assert (row.status, row.rating_status, row.skill) == ("match", "course", "php")
    assert "| some of 9 listed | 🟡 |" in render_fit_table(result)


def test_coursework_only_is_partial() -> None:
    profile = _profile(courses=["React", "AWS"])
    [row] = rate_parsed_jd(parse_jd(_posting(LINE)), profile).required
    assert (row.status, row.rating_status, row.skill) == ("course", "course", "react / aws")


def test_portfolio_evidence_is_partial_and_named_alone() -> None:
    profile = _profile(
        courses=["React"],
        portfolio_projects=[
            Project(name="Demo", url="https://example.com/demo", description="Runs in Docker")
        ],
    )
    [row] = rate_parsed_jd(parse_jd(_posting(LINE)), profile).required
    assert (row.status, row.skill) == ("portfolio", "docker")


def test_legacy_only_evidence_stays_legacy() -> None:
    old = [WorkExperience(title="Dev", company="Oldco", dates="2001", bullets=["Wrote PHP"])]
    profile = make_profile(experience=[], legacy_experience=old)
    [row] = rate_parsed_jd(parse_jd(_posting(LINE)), profile).required
    assert row.rating_status == "legacy"


def test_a_list_with_no_evidence_is_a_core_gap() -> None:
    result = rate_parsed_jd(parse_jd(_posting(LINE)), _profile("Taught pottery"))
    [row] = result.required
    assert row.status == "gap" and row.core
    assert result.rating == "Pass"


def test_missing_names_are_not_gaps_and_all_are_shown() -> None:
    profile = _profile("Built services in PHP and Docker")
    result = rate_parsed_jd(parse_jd(_posting(LINE)), profile)
    assert result.rating == "Good"
    table = render_fit_table(result)
    assert '**"Some of" list (required)**' in table
    for name in NAMES:
        assert f"| {name.lower()} |" in table


def test_a_name_in_the_list_is_not_counted_again_as_a_nice_to_have() -> None:
    result = rate_fit(
        required=["some of: PHP / Docker / AWS"],
        nice_to_have=["docker"],
        profile=_profile("Built services in PHP and Docker"),
    )
    assert result.nice_to_have == []


def test_a_list_read_from_many_lines_is_not_a_thin_read() -> None:
    posting = _posting(LINE, "A reliable internet connection and a quiet room to work in")
    result = rate_parsed_jd(parse_jd(posting), _profile("Built services in PHP and Docker"))
    assert result.low_confidence_message is None


def test_a_document_names_the_evidenced_names_as_the_posting_wrote_them() -> None:
    parsed = parse_jd(_posting(LINE))
    assert _display_skill("php / docker", parsed) == "PHP / Docker"


@pytest.mark.parametrize("written,profile_says", [("NodeJS", "Node.js"), ("NextJS", "Next.js")])
def test_a_spelling_without_the_dot_finds_the_dotted_one(written: str, profile_says: str) -> None:
    result = rate_fit([written], [], _profile(f"Built tools with {profile_says}"))
    assert result.required[0].status == "match"


def test_ubuntu_experience_meets_a_linux_requirement_and_not_the_reverse() -> None:
    ubuntu = rate_fit(["linux"], [], _profile("Administered Ubuntu servers"))
    assert ubuntu.required[0].status == "match"
    linux = rate_fit(["ubuntu"], [], _profile("Administered Linux servers"))
    assert linux.required[0].status == "gap"
    assert "linux" not in skill_match_terms("ubuntu")


@pytest.mark.parametrize(
    "raw,message",
    [
        ('{"terms": ["linux"], "satisfied_by": []}', "must be an object"),
        ('{"terms": ["linux"], "satisfied_by": {"linux": []}}', "non-empty list"),
        ('{"terms": ["linux"], "satisfied_by": {"linux": ["beos"]}}', "not in 'terms'"),
    ],
)
def test_a_bad_satisfied_by_entry_fails_loudly(tmp_path, raw: str, message: str) -> None:
    path = tmp_path / "vocabulary.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_satisfied_by(path)


def test_an_eluta_page_gives_title_and_company() -> None:
    text = "eluta.ca\nBack End Developer / Example Co\n5–6 minutes\n\n## Requirements\n- Git\n"
    parsed = parse_jd(text)
    assert (parsed.title, parsed.company) == ("Back End Developer", "Example Co")


@pytest.mark.parametrize("lead", ["", "www.eluta.ca\n"])
def test_a_first_line_of_position_and_company_is_split(lead: str) -> None:
    parsed = parse_jd(lead + "Back End Developer / Example Co\n\n## Requirements\n- Git\n")
    assert (parsed.title, parsed.company) == ("Back End Developer", "Example Co")


def test_only_the_last_slash_separates_the_company() -> None:
    parsed = parse_jd("Developer / Team Lead / Example Co\n\n## Requirements\n- Git\n")
    assert (parsed.title, parsed.company) == ("Developer / Team Lead", "Example Co")


@pytest.mark.parametrize(
    "second",
    ["Team Lead", "Programmer Analyst", "Back End", "C#", ".NET", "Remote", "Toronto", "Intern"],
)
def test_a_slash_before_something_else_is_not_a_company(second: str) -> None:
    parsed = parse_jd(f"Developer / {second}\n\n## Requirements\n- Git\n")
    assert parsed.company != second


def test_solid_hands_on_is_ordinary_english() -> None:
    parsed = parse_jd(_posting("Solid hands-on back-end development experience"))
    assert parsed.terms_to_confirm == ()


DUTIES = (
    "## What you'll do\nWe're seeing a growing amount of .NET work, so if you've got .NET "
    "experience, we especially want to hear from you.\n\n"
)


def test_what_the_duties_especially_want_is_required_even_when_listed_as_an_asset() -> None:
    posting = (
        "Dev\n\n"
        + DUTIES
        + "## What you bring\n- Git\n- Experience with .NET / C# is a strong asset\n"
        + "- Redis is an asset\n"
    )
    parsed = parse_jd(posting)
    assert parsed.required_for_rating == ["Git", ".NET", "C#"]
    assert parsed.required == ["Git", ".NET", "C#"]
    assert parsed.nice_for_rating == ["Redis"]
    assert {".net", "c#"} <= parsed.core_skills


def test_a_strong_asset_the_posting_does_not_stress_stays_optional() -> None:
    parsed = parse_jd(_posting("Git", "Experience with .NET / C# is a strong asset"))
    assert parsed.required_for_rating == ["Git"]
    assert parsed.nice_for_rating == [".NET", "C#"]


REQUIREMENTS = "Dev\n\n## Requirements\n"
GROUP = ["some of: PHP / Drupal / AWS"]


@pytest.mark.parametrize(
    "body,required",
    [
        ("Experience with some of the following:\n- PHP\n- Drupal\n- AWS\n", GROUP),
        ("Experience with some of the following:\n    PHP\n    Drupal\n    AWS\n", GROUP),
        ("Some of these:\n\n- PHP\n\n- Drupal\n\n- AWS\n", GROUP),
        # under a bullet, only the deeper lines belong to the list
        ("- Some of these:\n    - PHP\n    - Drupal\n    - AWS\n- Git\n", [*GROUP, "Git"]),
    ],
)
def test_a_list_under_the_introduction_is_one_requirement(body: str, required) -> None:
    assert parse_jd(REQUIREMENTS + body).required_for_rating == required


def test_an_introduction_that_is_the_heading_still_opens_the_section() -> None:
    parsed = parse_jd("Dev\n\nYou have some of the following:\n- PHP\n- Drupal\n- AWS\n")
    assert parsed.required_for_rating == GROUP


def test_a_list_under_a_nice_to_have_introduction_is_optional() -> None:
    body = "- Git\n\nNice to have some of these:\n- PHP\n- Drupal\n- AWS\n"
    parsed = parse_jd(REQUIREMENTS + body)
    assert (parsed.required_for_rating, parsed.nice_for_rating) == (["Git"], GROUP)


def test_sentences_under_the_introduction_give_their_skills_and_the_rest_is_listed() -> None:
    body = (
        "Some of these:\n- Experience building services in C#\n- Knowledge of AWS in production\n"
        "- Docker\n- A love of tidy and well written documentation\n"
    )
    parsed = parse_jd(REQUIREMENTS + body)
    assert parsed.required_for_rating == ["some of: C# / AWS / Docker"]
    assert parsed.unscored_required == ("A love of tidy and well written documentation",)


def test_too_short_a_list_under_the_introduction_is_left_as_written() -> None:
    parsed = parse_jd(REQUIREMENTS + "Some of the following:\n- PHP\n- Drupal\n")
    assert parsed.required_for_rating == ["PHP", "Drupal"]


@pytest.mark.parametrize(
    "line,item",
    [
        ("Experience with one or more of: PHP, Drupal, AWS", "PHP / Drupal / AWS"),
        ("Experience with at least one of the following: PHP, Drupal, AWS", "PHP / Drupal / AWS"),
        ("One of the following: Angular, React, Vue", "Angular / React / Vue"),
        ("One or more of: C#, Java", "C# / Java"),
        ("Any of: C#, Java", "C# / Java"),
        ("At least one of C# or Java", "C# / Java"),
    ],
)
def test_one_of_a_list_is_a_choice(line: str, item: str) -> None:
    assert parse_jd(_posting(line)).required_for_rating == [item]


def test_one_of_in_ordinary_prose_is_not_a_choice() -> None:
    parsed = parse_jd(_posting("Join one of the leading firms building with C# and SQL"))
    assert parsed.required_for_rating == ["C#", "SQL"]


def test_a_known_name_in_a_choice_is_not_reported_as_unknown() -> None:
    parsed = parse_jd(_posting("At least one of the following languages: Python, Go, C#, or Rust"))
    assert parsed.required_for_rating == ["Python / Go / C# / Rust"]
    assert parsed.unknown_names == ()


def _project(description: str, *evidence: str):
    project = Project(
        name="Demo",
        url="https://example.com/demo",
        description=description,
        skills_evidence=list(evidence),
    )
    return make_profile(
        experience=[], technical_skills=[], ats_keywords={}, portfolio_projects=[project]
    )


@pytest.mark.parametrize("word", ["orchestration", "container orchestration"])
def test_orchestration_with_another_tool_is_not_kubernetes(word: str) -> None:
    profile = _project("A web app.", f"Used {word} (Docker Compose)")
    assert rate_fit(["kubernetes"], [], profile).required[0].status == "gap"


def test_kubernetes_experience_meets_a_container_orchestration_requirement() -> None:
    profile = _project("Runs on K8s.")
    assert rate_fit(["container orchestration"], [], profile).required[0].status == "portfolio"
    assert rate_fit(["kubernetes"], [], profile).required[0].status == "portfolio"


@pytest.mark.parametrize(
    "sentence",
    [
        "Containerization and Kubernetes deployment are planned, not done.",
        "Kubernetes manifests are planned.",
        "Kubernetes support is not yet built.",
    ],
)
def test_work_a_project_has_not_done_is_no_evidence(sentence: str) -> None:
    profile = _project(f"A web app. {sentence}", sentence)
    assert rate_fit(["kubernetes"], [], profile).required[0].status == "gap"


def test_the_rest_of_a_project_with_planned_work_still_counts() -> None:
    profile = _project("Built with a written plan and Docker. Kubernetes is planned, not done.")
    assert rate_fit(["docker"], [], profile).required[0].status == "portfolio"


def test_docker_experience_meets_a_containerization_requirement() -> None:
    profile = _profile("Deployed applications with Docker")
    assert rate_fit(["containerization"], [], profile).required[0].status == "match"
