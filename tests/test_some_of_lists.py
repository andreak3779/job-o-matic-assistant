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
    "style",
    ["service-oriented architecture", "SOA", "Clean Architecture", "hexagonal architecture"],
)
def test_an_architecture_style_meets_software_architecture_and_not_the_reverse(style: str) -> None:
    built = rate_fit(["software architecture"], [], _profile(f"Implemented {style} in C#"))
    assert built.required[0].status == "match"
    studied = rate_fit(["software architecture"], [], _profile("Wrote C#", courses=[style]))
    assert studied.required[0].status == "course"
    reverse = rate_fit([style], [], _profile("Led software architecture discussions"))
    assert reverse.required[0].status == "gap"


def test_one_architecture_style_does_not_stand_in_for_another() -> None:
    result = rate_fit(["clean architecture"], [], _profile("Implemented SOA in C#"))
    assert result.required[0].status == "gap"


@pytest.mark.parametrize("bullet", ["Drew system architecture diagrams", "Configured SOAP clients"])
def test_other_wording_does_not_meet_software_architecture(bullet: str) -> None:
    result = rate_fit(["software architecture"], [], _profile(bullet))
    assert result.required[0].status == "gap"


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


MAY_INCLUDE = (
    "Developer\n\n"
    "Each requirement we receive varies, but the skillset may include:\n"
    "Expertise in the following development environments and tools:\n\n"
    "    Microsoft SQL Server 2008 or later\n"
    "    Microsoft .NET Platform (4.0 or higher)\n"
    "    SSRS, SSIS, Crystal Reports\n"
    "    Resharper\n\n"
    "Experience Required:\n\n"
    "    Git\n"
)


def test_a_skill_set_that_may_include_a_list_is_one_requirement() -> None:
    parsed = parse_jd(MAY_INCLUDE)
    assert parsed.required_for_rating == [
        "some of: Microsoft SQL Server / Microsoft .NET Platform / SSRS / SSIS / Crystal Reports"
        " / Resharper",
        "Git",
    ]


def test_skills_may_include_on_one_line() -> None:
    assert some_of_list("Skills may include: C#, SQL, Azure") == ["C#", "SQL", "Azure"]


def test_duties_that_may_include_things_are_not_a_pool() -> None:
    assert some_of_list("Your duties may include: C#, SQL, Azure") is None


@pytest.mark.parametrize(
    "requirement", ["Oracle 12c or later", "Java 11 or higher", "Windows Server 2019 or newer"]
)
def test_a_version_floor_is_not_matched_by_the_word_itself(requirement: str) -> None:
    profile = _profile("The work was later carried to a higher tier on newer hardware")
    assert rate_fit([requirement], [], profile).required[0].status == "gap"


def test_a_version_floor_still_finds_the_skill() -> None:
    profile = _profile("Administered SQL Server databases")
    result = rate_fit(["Microsoft SQL Server 2008 or later"], [], profile)
    assert result.required[0].status == "match"


@pytest.mark.parametrize(
    "line,item",
    [
        ("Windows Communication Foundation", "Windows Communication Foundation"),
        ("Windows Communication Foundation (WCF)", "WCF"),
        ("Windows Presentation Foundation (WPF)", "WPF"),
    ],
)
def test_a_windows_foundation_is_one_skill_and_not_windows(line: str, item: str) -> None:
    parsed = parse_jd(_posting(f"Experience building services with {line}"))
    assert parsed.required_for_rating == [item]
    assert item.lower() in parsed.core_skills


def test_the_long_name_finds_the_acronym() -> None:
    result = rate_fit(["Windows Presentation Foundation"], [], _profile("Built a WPF client"))
    assert result.required[0].status == "match"


def test_jira_agile_is_the_tool_and_agile_the_practice() -> None:
    line = "Experience with Agile development techniques and supporting tools such as Jira Agile"
    parsed = parse_jd(_posting(line))
    assert parsed.required_for_rating == ["Agile", "Jira Agile"]


def test_a_logo_line_names_the_company_by_its_full_name() -> None:
    text = (
        "Example Consulting logo\nDeveloper\nSpringfield\n\n## Requirements\n- Git\n\n"
        "Example Consulting Group is committed to a fair process.\n"
    )
    parsed = parse_jd(text)
    assert (parsed.title, parsed.company) == ("Developer", "Example Consulting Group")


GENERAL = (
    "You have 5+ years of experience in software with proficiency in one or more common "
    "languages, and are also familiar with various databases and web frontend technology."
)


def test_general_kinds_of_skill_on_a_years_line_are_scored() -> None:
    parsed = parse_jd(_posting(GENERAL))
    assert parsed.required_for_rating == [
        "common languages",
        "various databases",
        "web frontend technology",
    ]
    assert [s.kind for s in parsed.soft_requirements] == ["years"]


def test_a_general_kind_is_met_by_any_of_its_members() -> None:
    profile = _profile("Built Angular screens in C# over SQL Server")
    result = rate_parsed_jd(parse_jd(_posting(GENERAL)), profile)
    assert [m.status for m in result.required] == ["match", "match", "match"]
    assert "[via " in result.required[0].evidence


def test_a_general_kind_with_no_member_is_a_gap() -> None:
    result = rate_fit(["various databases"], [], _profile("Taught pottery"))
    assert result.required[0].status == "gap"


def test_named_examples_replace_the_general_kind() -> None:
    line = "Proficiency in modern programming languages such as TypeScript, C#, or Python"
    assert parse_jd(_posting(line)).required_for_rating == ["TypeScript / C# / Python"]


def test_coding_agent_work_meets_an_ai_agents_requirement_and_not_the_reverse() -> None:
    profile = _project("Built with AI coding agents.")
    assert rate_fit(["ai agents"], [], profile).required[0].status == "portfolio"
    agents = _project("Studied AI agents.")
    assert rate_fit(["ai coding agents"], [], agents).required[0].status == "gap"


UNMARKED = (
    "Dev\n\nWhat You Bring\n"
    "Experience with .NET / C# is a strong asset\n"
    "Experience with some of what we use: PHP, Drupal, Docker\n"
    "Comfort in a Linux shell for day-to-day tasks, plus some understanding of hosting\n"
    "What We Bring\n"
    "A team that enjoys Python on Fridays\n"
)


def test_a_copy_with_no_bullets_or_indents_keeps_its_requirements() -> None:
    parsed = parse_jd(UNMARKED)
    assert parsed.required_for_rating == ["some of: PHP / Drupal / Docker", "Linux"]
    assert parsed.nice_for_rating == [".NET", "C#"]


def test_a_statement_that_a_skill_is_an_asset_is_not_a_heading() -> None:
    text = "Dev\n\n## Requirements\n- Git\nDocker is a strong asset\n- Python\n"
    parsed = parse_jd(text)
    assert parsed.required_for_rating == ["Git", "Python"]
    assert parsed.nice_for_rating == ["Docker"]


@pytest.mark.parametrize("indent", ["    ", ""])
def test_a_list_wrapped_after_a_comma_is_one_list(indent: str) -> None:
    text = _posting(f"Experience with some of: PHP, Drupal, JavaScript,\n{indent}AWS, Docker")
    assert parse_jd(text).required_for_rating == [
        "some of: PHP / Drupal / JavaScript / AWS / Docker"
    ]


def test_a_separate_line_after_a_comma_is_not_joined() -> None:
    text = (
        "Dev\n\n## Requirements\n"
        "    Senior experience using C# and ASP.NET Core,\n"
        "    Experience with Docker in production\n"
    )
    required = parse_jd(text).required
    assert required[:2] == ["C#", "ASP.NET Core"]
    assert "Docker" in required[-1]


def test_names_one_per_line_at_the_same_indent_join_their_list() -> None:
    text = (
        "Dev\n\n## Requirements\n"
        "    Experience with some of the following:\n    PHP\n    Drupal\n    Docker\n"
        "    Comfort working in a shell every single day\n"
    )
    assert parse_jd(text).required_for_rating == ["some of: PHP / Drupal / Docker"]


def test_a_company_named_by_two_words_is_not_cut_to_the_second() -> None:
    text = (
        "Developer\n\nWe have news: Example Commerce is looking for you. We follow Example "
        "Commerce standards, and offers from Example Commerce need a check.\n\n"
        "## Requirements\n- Git\n"
    )
    assert parse_jd(text).company == "Example Commerce"


def test_a_part_that_says_the_umbrella_name_replaces_the_umbrella() -> None:
    line = "You build systems with AI agents and care about the impact AI can have"
    assert parse_jd(_posting(line)).required_for_rating == ["AI agents"]


def test_named_languages_replace_the_general_kind_beside_them() -> None:
    line = "Skills in one or more modern languages (C#, TypeScript, Java, or similar)"
    assert parse_jd(_posting(line)).required_for_rating == ["C# / TypeScript / Java"]


def test_a_two_word_skill_is_not_read_as_a_two_word_company() -> None:
    text = (
        "Developer\n\nWe build on Power Platform daily, extend Power Platform often and "
        "teach Power Platform.\n\n## Requirements\n- Git\n"
    )
    assert parse_jd(text).company != "Power Platform"


STACK = (
    "Dev\n\n## What you bring\n- Git\n\n"
    "Our stack spans TypeScript/Node.js, React, .NET, SQL Server/Azure SQL, CI/CD, and Azure. "
    "You don't need all of it. You should be deep in several of these.\n"
)


def test_a_stack_to_know_part_of_is_one_requirement() -> None:
    parsed = parse_jd(STACK)
    assert parsed.required_for_rating == [
        "Git",
        "some of: TypeScript / Node.js / React / .NET / SQL Server / Azure SQL / CI/CD / Azure",
    ]


def test_a_stack_that_is_only_described_is_not_a_requirement() -> None:
    text = "Dev\n\n## Requirements\n- Git\n\nOur stack spans React, .NET and Azure. We love it.\n"
    assert parse_jd(text).required_for_rating == ["Git"]


@pytest.mark.parametrize("mark", ["●", "○", "◦", "▪", "‣"])
def test_other_bullet_marks_are_removed_from_a_requirement(mark: str) -> None:
    parsed = parse_jd(f"Dev\n\n## Requirements\n{mark} Git\n{mark} Docker\n")
    assert parsed.required_for_rating == ["Git", "Docker"]


def test_what_a_company_offers_is_not_part_of_the_requirements() -> None:
    text = (
        "Dev\n\n## Highly Preferred Qualifications\n- Git\n\nWhat Example Co Offers\n\n"
        "    Competitive Wages\n    Paid Parental Leave\n"
    )
    assert parse_jd(text).nice_for_rating == ["Git"]


@pytest.mark.parametrize(
    "line",
    [
        "AI driven approach to SDLC",
        "An AI-assisted approach to software development",
        "AI first mindset",
    ],
)
def test_an_ai_way_of_working_asks_for_ai(line: str) -> None:
    assert parse_jd(_posting(line)).required_for_rating == ["AI"]


@pytest.mark.parametrize(
    "line", ["Experience with Agentic AI workflows", "Experience with agentic workflows"]
)
def test_agentic_ai_work_is_one_skill_met_by_coding_agent_work(line: str) -> None:
    [item] = parse_jd(_posting(line)).required_for_rating
    assert item.lower().startswith("agentic")
    profile = _project("Built with AI coding agents.")
    assert rate_fit([item], [], profile).required[0].status == "portfolio"


def test_claude_code_written_closed_is_the_same_tool() -> None:
    line = "Familiarity with coding agents, such as ClaudeCode or Copilot"
    parsed = parse_jd(_posting(line))
    assert "ClaudeCode / Copilot" in parsed.required_for_rating
    assert parsed.unknown_names == ()
    result = rate_fit(["claudecode"], [], _project("Built with Claude Code."))
    assert result.required[0].status == "portfolio"


@pytest.mark.parametrize("skill", ["TDD", "xUnit", "design principles", "AS400"])
def test_a_resolved_framing_gap_covers_each_skill_it_names(skill: str) -> None:
    profile = make_profile(
        experience=[],
        resolved_framing_gaps=[
            "TDD/xUnit/NUnit — leads the first bullet",
            "OOP/design principles — in the summary",
            "IBM i / AS400 — the database work ran on it",
        ],
    )
    row = rate_fit([skill], [], profile).required[0]
    assert (row.status, row.evidence) == ("match", "resolved framing gap")


@pytest.mark.parametrize("skill", ["summary", "bullet", "3.5"])
def test_the_note_on_a_resolved_gap_is_not_a_skill(skill: str) -> None:
    profile = make_profile(
        experience=[],
        technical_skills=[],
        ats_keywords={},
        portfolio_projects=[],
        resolved_framing_gaps=["Web Forms (.NET 3.5/4.x) — in the summary bullet"],
    )
    assert rate_fit([skill], [], profile).required[0].status == "gap"


BREADTH = (
    "Strong understanding of web frameworks, APIs, and databases, and experience working with "
    "multiple programming languages."
)


def test_a_line_naming_kinds_of_skill_asks_for_each() -> None:
    parsed = parse_jd(_posting(BREADTH))
    assert [item.lower() for item in parsed.required_for_rating] == [
        "web frameworks",
        "api",
        "multiple programming languages",
        "various databases",
    ]


def test_each_kind_is_met_by_any_of_its_members() -> None:
    profile = _profile("Built Angular screens and APIs in C# over SQL Server")
    result = rate_parsed_jd(parse_jd(_posting(BREADTH)), profile)
    assert {m.status for m in result.required} == {"match"}


def test_the_word_databases_alone_is_not_a_requirement() -> None:
    parsed = parse_jd(_posting("Git", "You will back up the databases and keep notes on them"))
    assert parsed.required_for_rating == ["Git"]


def test_named_web_frameworks_replace_the_kind_beside_them() -> None:
    line = "Experience with web frameworks such as Django, Flask, or FastAPI"
    assert parse_jd(_posting(line)).required_for_rating == ["Django / Flask / FastAPI"]


def _combination_posting(intro: str) -> str:
    return (
        "Dev\n\nTechnical Requirements\n\n"
        f"The stack depends on the product. You'll draw on {intro}\n\n"
        "    Languages and frameworks C# and PHP (ASP.NET Core, Laravel), and Angular.\n"
        "    Cloud and infrastructure AWS (ECS, SQS), Docker and GitHub Actions pipelines.\n"
        "    Experience with public APIs is a strong plus for this work.\n"
        "    Knowing each one of these is not required, comfort with Linux matters more.\n"
    )


@pytest.mark.parametrize(
    "intro", ["some combination of", "some combination of:", "some mix of the following"]
)
def test_some_combination_of_a_stack_is_one_requirement(intro: str) -> None:
    parsed = parse_jd(_combination_posting(intro))

    lists = [item for item in parsed.required_items if item.startswith("some of: ")]
    assert len(lists) == 1
    names = lists[0].removeprefix("some of: ").split(" / ")
    # skills named in brackets are listed; an asset line and a remark are not part of the list
    assert {"C#", "PHP", "ASP.NET Core", "Laravel", "AWS", "ECS", "SQS", "Docker"} <= set(names)
    assert "API" not in names
    assert "Linux" not in names
    assert "API" in parsed.nice_to_have
    assert "Linux" in parsed.required


def test_a_bracket_on_a_short_list_line_is_detail_on_the_name() -> None:
    posting = _posting(
        "Experience with some of the following:",
        "  JavaScript (utilizing JSON)",
        "  C#",
        "  Docker",
    ).replace("-   ", "  - ")

    items = parse_jd(posting).required_items

    assert items == ["some of: JavaScript / C# / Docker"]


def test_release_management_meets_an_sdlc_requirement_and_not_the_reverse() -> None:
    releases = _profile("Coordinated release management across environments")
    lifecycle = _profile("Worked through the whole SDLC")

    assert rate_fit(["SDLC"], [], releases).required[0].status == "match"
    assert rate_fit(["release management"], [], lifecycle).required[0].status == "gap"


@pytest.mark.parametrize(
    "requirement,bullet",
    [
        ("GitHub Actions", "Ran releases through a GitLab CI/CD pipeline"),
        ("GitHub Actions", "Deployed containers with Docker"),
        ("GitHub Actions", "Led the DevOps practice"),
        ("CD with GitHub Actions", "Ran releases through a GitLab CI/CD pipeline"),
        ("Docker", "Ran releases through a GitLab CI/CD pipeline"),
        ("Docker", "Wrote GitHub Actions workflows"),
        ("CI/CD", "Deployed containers with Docker"),
    ],
)
def test_one_delivery_tool_does_not_stand_in_for_another(requirement: str, bullet: str) -> None:
    result = rate_fit([requirement], [], _profile(bullet))

    assert result.required[0].status == "gap"


@pytest.mark.parametrize(
    "requirement,bullet",
    [
        ("CI/CD", "Wrote GitHub Actions workflows"),
        ("CD with GitHub Actions", "Wrote GitHub Actions workflows"),
        ("DevOps", "Wrote GitHub Actions workflows"),
        ("DevOps", "Deployed containers with Docker"),
        ("DevOps", "Ran releases through a GitLab CI/CD pipeline"),
    ],
)
def test_a_delivery_tool_still_meets_the_broader_requirement(requirement: str, bullet: str) -> None:
    assert rate_fit([requirement], [], _profile(bullet)).required[0].status == "match"


def test_portfolio_github_actions_is_not_claimed_from_a_job_that_used_gitlab() -> None:
    site = Project(
        name="A site",
        url="https://example.com/site",
        description="GitHub Actions workflows deploy it",
        skills_evidence=[],
    )
    profile = _profile("Ran releases through a GitLab CI/CD pipeline", portfolio_projects=[site])

    assert rate_fit(["GitHub Actions"], [], profile).required[0].status == "portfolio"


@pytest.mark.parametrize(
    "requirement,bullet",
    [
        ("C#", "Worked as a software developer on a web API"),
        ("C#", "Full-stack developer building Java services"),
        ("ASP.NET Core", "Worked as a software developer in Java"),
        ("GitHub Copilot", "Practised prompt engineering"),
        ("prompt engineering", "Used GitHub Copilot daily"),
        ("Python", "Wrote shell scripting for log rotation"),
        ("Python", "Built process automation workflows"),
        ("xUnit", "Wrote unit testing suites with NUnit"),
        ("MongoDB", "Modelled data in a NoSQL document db"),
    ],
)
def test_a_related_skill_does_not_stand_in_for_the_one_asked(requirement: str, bullet: str) -> None:
    profile = _profile(bullet, portfolio_projects=[], ats_keywords={})

    assert rate_fit([requirement], [], profile).required[0].status == "gap"


@pytest.mark.parametrize(
    "requirement,bullet",
    [
        ("C#", "Built services on .NET"),
        ("GitHub Copilot", "Paired with Copilot daily"),
        ("unit testing", "Wrote xUnit suites"),
        ("scripting", "Wrote Python tooling"),
        ("Python scripting", "Wrote Python tooling"),
        ("NoSQL", "Modelled data in MongoDB"),
        ("MongoDB", "Ran Mongo clusters"),
        ("professional software development experience", "Wrote C# services"),
    ],
)
def test_a_narrower_or_same_skill_still_meets_the_requirement(
    requirement: str, bullet: str
) -> None:
    assert rate_fit([requirement], [], _profile(bullet)).required[0].status == "match"
