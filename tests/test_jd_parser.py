"""Tests for jobomatic.fit.parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobomatic.fit.parser import parse_jd

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

SAMPLE_JD = """\
# Senior Full-Stack .NET Developer

**Company:** Contoso Cloud Solutions
**Location:** Remote

## Required Skills
- 5+ years C# / .NET Core / ASP.NET Core Web API
- Strong Azure fundamentals (App Service, Azure Functions, Cosmos DB)
- Angular or React frontend development
- SQL Server / T-SQL query optimization
- CI/CD with GitHub Actions and Docker
- Unit testing with xUnit and integration testing
- REST API design and microservices architecture
- Legacy system modernization experience

## Nice to Have
- Azure AI / OpenAI integration
- Blazor WebAssembly
- Kubernetes / container orchestration
- Python scripting for automation
- GitHub Copilot and prompt engineering experience
- MongoDB or other NoSQL databases
"""


def test_required_and_nice_separated() -> None:
    parsed = parse_jd(SAMPLE_JD)
    joined_required = " ".join(parsed.required)
    joined_nice = " ".join(parsed.nice_to_have)
    assert "Azure fundamentals" in joined_required
    assert "Kubernetes" in joined_nice
    assert "Azure AI" in joined_nice
    assert "Blazor WebAssembly" in joined_nice


def test_years_prefix_stripped() -> None:
    parsed = parse_jd(SAMPLE_JD)
    # The 5+ years prefix on the first item should be gone.
    assert not any(item.lower().startswith("5") for item in parsed.required)


def test_compound_phrases_split() -> None:
    parsed = parse_jd(SAMPLE_JD)
    # "Angular or React frontend development" splits on "or".
    assert "Angular" in parsed.required or "React" in parsed.required
    # "C# / .NET Core / ASP.NET Core Web API" splits on "/".
    assert any("C#" in item for item in parsed.required)
    assert any(".NET Core" in item for item in parsed.required)


def test_title_and_company_extracted() -> None:
    parsed = parse_jd(SAMPLE_JD)
    assert parsed.title == "Senior Full-Stack .NET Developer"
    assert parsed.company == "Contoso Cloud Solutions"


def test_unknown_role_when_no_title() -> None:
    parsed = parse_jd("Some prose with no heading or company line.")
    assert parsed.title == "Unknown Role"
    assert parsed.company == "Unknown Company"


def test_location_extracted_from_bold_line() -> None:
    parsed = parse_jd(SAMPLE_JD)
    assert parsed.location == "Remote"


def test_location_is_none_when_absent() -> None:
    parsed = parse_jd("Some prose with no location line.")
    assert parsed.location is None


def test_job_id_extracted_from_bold_line() -> None:
    text = (
        "# Senior Developer\n\n**Company:** Acme Corp\n**Location:** Remote\n"
        "**Job ID:** REQ-4821\n\n## Required Skills\n- C#\n"
    )
    parsed = parse_jd(text)
    assert parsed.job_id == "REQ-4821"


def test_job_id_is_none_when_absent() -> None:
    parsed = parse_jd(SAMPLE_JD)
    assert parsed.job_id is None


# ── Regression tests for atypical-JD-formatting fixes ───────────────────────
#
# job_description_fit's readiness plan found three concrete failure modes on
# atypically-formatted real JDs. Two are fixed here (heading regexes broadened
# for unconventional phrasing; a line that's already a bullet, or that ends
# in sentence punctuation, is never treated as a section-heading trigger even
# if it contains a heading-like word). The third — a JD with no recognizable
# section headings at all — is a known, accepted limitation: it now fails
# safely (nothing captured) instead of the old behavior (silently
# miscategorizing every bullet as nice-to-have). A general-purpose rewrite to
# handle heading-less prose JDs is out of scope; `parse_jd`'s docstring
# self-describes as "Naively extract..." for a reason.


def test_prose_paragraph_with_bonus_keyword_no_longer_hijacks_the_nice_heading() -> None:
    """A prose sentence mentioning "a bonus" ends in a period, so the
    sentence-punctuation guard now keeps it from being misread as a Nice to
    Have heading. This JD has no real section headings at all, so nothing is
    captured — a safe, honest failure mode, not the old miscategorization
    into nice_to_have."""
    text = (FIXTURES_DIR / "atypical-no-headings-jd.md").read_text(encoding="utf-8")
    parsed = parse_jd(text)
    assert parsed.required == []
    assert parsed.nice_to_have == []


def test_unconventional_heading_phrasing_is_recognized() -> None:
    """ "What You'll Bring" now matches the broadened `_REQUIRED_HEADING_RE`,
    so its bullets are captured as required skills instead of silently
    dropped."""
    text = (FIXTURES_DIR / "atypical-whatyoullbring-jd.md").read_text(encoding="utf-8")
    parsed = parse_jd(text)
    joined_required = " ".join(parsed.required)
    assert "ASP.NET Core" in joined_required
    assert "Azure" in joined_required
    assert "SQL Server" in joined_required
    assert "Kubernetes" in " ".join(parsed.nice_to_have)


def test_unmarked_prose_bullets_under_recognized_heading_are_captured() -> None:
    """Some real postings (BigHand's Consultant/Developer listing) flatten
    their bullets to plain indented sentences with no "-"/"•" marker when
    copy-pasted. Under a recognized required-skills heading, these must still
    be captured as content instead of silently dropped to an empty required
    list (which previously forced a spurious "Pass — No required skills
    provided" rating)."""
    text = (FIXTURES_DIR / "atypical-unmarked-prose-bullets-jd.md").read_text(encoding="utf-8")
    parsed = parse_jd(text)
    assert parsed.required != []
    joined_required = " ".join(parsed.required)
    assert "T-SQL" in joined_required


def test_unrecognized_heading_after_required_section_closes_it() -> None:
    """A heading the parser doesn't recognize as required/nice/benefits-like
    (e.g. a sub-heading such as "Strong development skills and experience:")
    must NOT close the active section — it has no ending punctuation and no
    bullet marker, so it looks heading-shaped, but treating every such line
    as a section-closer would drop the real requirements that follow it. Only
    a recognized closing heading (e.g. "What we offer") should end the
    section — otherwise the following benefits list gets miscategorized as
    required skills indefinitely."""
    text = (FIXTURES_DIR / "atypical-unmarked-prose-bullets-jd.md").read_text(encoding="utf-8")
    parsed = parse_jd(text)
    joined_required = " ".join(parsed.required).lower()
    assert "holiday" not in joined_required
    assert "remote working" not in joined_required
    assert "global presence" not in joined_required


def test_nested_nice_to_have_phrase_no_longer_flips_section_mid_required_list() -> None:
    """A required-section bullet containing the phrase "nice to have" (e.g.
    "Kubernetes experience is nice to have but strongly preferred") is a
    bullet, not a heading, so it no longer flips `section` — every bullet in
    the Required Skills list, including that one, stays required. Whether
    that specific skill should really count as required is exactly the kind
    of judgment call left to the SKILL.md's sanity-check fallback, not
    something the parser should resolve with keyword heuristics."""
    text = (FIXTURES_DIR / "atypical-nested-nice-to-have-jd.md").read_text(encoding="utf-8")
    parsed = parse_jd(text)
    joined_required = " ".join(parsed.required)
    assert "Kubernetes" in joined_required
    assert "SQL Server" in joined_required
    assert "GitHub Actions" in joined_required
    assert parsed.nice_to_have == ["Python scripting for automation"]


# ── location_check (job-search location rules) ───────────────────────────────


def test_parse_jd_populates_location_check_with_disqualifier() -> None:
    parsed = parse_jd(
        "# Senior Developer\n\n**Company:** Acme\n**Location:** Montréal, QC (Hybrid)\n\n"
        "## Requirements\n- C#\n"
    )
    assert parsed.location_check.disqualified
    assert any("Quebec" in d for d in parsed.location_check.disqualifiers)


def test_parse_jd_location_check_clean_for_remote_posting() -> None:
    parsed = parse_jd("# Dev\n\n**Location:** Remote\n\n## Requirements\n- C#\n")
    assert not parsed.location_check.disqualified
    assert parsed.location_check.flags == ()


def test_parse_jd_location_check_defaults_clean_when_no_location_info() -> None:
    parsed = parse_jd("Some prose with no location line.")
    assert not parsed.location_check.disqualified


# ── Sentence-style bullets, extra headings, unscored lines ───────────────────


def _prose_jd() -> str:
    return (FIXTURES_DIR / "prose-qualifications-jd.md").read_text(encoding="utf-8")


def test_required_qualifications_and_hyphenated_nice_to_have_headings_are_recognized() -> None:
    parsed = parse_jd(_prose_jd())
    assert parsed.required, "Required Qualifications heading was not recognized"
    assert parsed.nice_to_have, "Nice-to-Have Qualifications heading was not recognized"


def test_sentence_bullets_yield_skill_terms_not_whole_sentences() -> None:
    parsed = parse_jd(_prose_jd())
    assert parsed.required == [
        "C#",
        ".NET",
        "GitHub Copilot / Claude Code / Windsurf",
        "Azure",
        "event-driven",
        "microservice",
        "distributed systems",
        "OOP",
        "design patterns",
        "SOLID",
        "secure development",
        "testing",
    ]


def test_nice_section_sentences_also_become_terms() -> None:
    parsed = parse_jd(_prose_jd())
    joined = " ".join(parsed.nice_to_have)
    assert "Azure DevOps" in joined
    assert "Azure OpenAI" in joined
    assert "CI/CD" in joined  # kept whole, not split into "CI" / "CD"


def test_responsibilities_section_does_not_leak_into_required_skills() -> None:
    parsed = parse_jd(_prose_jd())
    # "Agile SCRUM" and "code reviews" appear only under Responsibilities.
    joined = " ".join(parsed.required + parsed.nice_to_have).lower()
    assert "scrum" not in joined
    assert "code review" not in joined
    assert "saas" not in joined


def test_salary_heading_closes_the_nice_section() -> None:
    parsed = parse_jd(_prose_jd())
    assert "Not provided in posting" not in " ".join(parsed.nice_to_have)


def test_a_degree_line_is_a_soft_requirement_not_an_unscored_line() -> None:
    parsed = parse_jd(_prose_jd())
    assert parsed.unscored_required == ()
    kinds = [(s.kind, s.note) for s in parsed.soft_requirements]
    assert ("education", "equivalent accepted") in kinds
    # The posting's "5+ years ... with strong C# and .NET experience" line is listed too and
    # still scored for its skills.
    assert ("years", "minimum 5 years") in kinds


def test_unscored_lines_are_only_collected_for_the_required_section() -> None:
    text = (
        "# Dev\n\n## Requirements\n- A requirement sentence naming no technology at all\n"
        "- C#\n\n## Nice to have\n- A genuinely interesting sentence with no technology named\n"
    )
    parsed = parse_jd(text)
    assert parsed.unscored_required == ("A requirement sentence naming no technology at all",)
    assert parsed.nice_to_have == []


def test_parenthetical_detail_does_not_turn_a_short_skill_into_prose() -> None:
    # Regression: "Strong Azure fundamentals (App Service, Azure Functions, Cosmos DB)"
    # is a short skill name plus detail; it must keep its alias-bearing phrase.
    parsed = parse_jd(
        "# Dev\n\n## Required Skills\n"
        "- Strong Azure fundamentals (App Service, Azure Functions, Cosmos DB)\n"
    )
    assert parsed.required == [
        "Strong Azure fundamentals (App Service, Azure Functions, Cosmos DB)"
    ]


def test_short_bullets_keep_the_original_split_behaviour() -> None:
    parsed = parse_jd("# Dev\n\n## Requirements\n- Angular or React frontend development\n")
    assert parsed.required == ["Angular", "React frontend development"]


@pytest.mark.parametrize(
    "heading",
    ["Preferred Qualifications", "Nice-to-Have Qualifications", "Nice to Haves", "Bonus Points"],
)
def test_qualification_style_nice_headings_are_not_read_as_required(heading: str) -> None:
    parsed = parse_jd(f"# Dev\n\n## Requirements\n- C#\n\n## {heading}\n- Kubernetes\n")
    assert parsed.required == ["C#"]
    assert parsed.nice_to_have == ["Kubernetes"]


@pytest.mark.parametrize("heading", ["You Have…", "You have...", "Who you are", "Qualifications"])
def test_more_required_heading_phrasings_are_recognized(heading: str) -> None:
    parsed = parse_jd(f"# Dev\n\n## {heading}\n- C#\n- Azure\n")
    assert parsed.required == ["C#", "Azure"]


def test_label_value_headings_and_indented_unmarked_lines_are_parsed() -> None:
    """Regression: a JD saved as "# Company / value / # Postion / value" with
    indented, marker-less, punctuation-less list lines under a "Things we're
    looking for" heading used to parse to an empty required list (rated Pass,
    "No required skills provided") and title "Company"."""
    text = (FIXTURES_DIR / "atypical-label-value-indented-jd.md").read_text(encoding="utf-8")
    parsed = parse_jd(text)
    assert parsed.title == "Software Developer"
    assert parsed.company == "Contoso Dental"
    joined_required = " ".join(parsed.required).lower()
    # "Strong SQL" asks for SQL: the filler word is not part of what is searched for.
    assert "SQL" in parsed.required
    assert "strong sql" not in joined_required
    # A sentence naming no known skill is listed for the user to read, not rated as a gap (A).
    assert "troubleshooting production issues" not in joined_required
    assert any("troubleshooting production issues" in line for line in parsed.unscored_required)
    joined_nice = " ".join(parsed.nice_to_have).lower()
    assert "healthcare" in joined_nice
    # Nice-to-have lines must not leak into required, nor the intro prose in.
    assert "healthcare" not in joined_required
    assert not any("seeking" in item.lower() for item in parsed.required)


def test_long_prose_requirement_stays_whole_in_required_items() -> None:
    text = (FIXTURES_DIR / "atypical-label-value-indented-jd.md").read_text(encoding="utf-8")
    parsed = parse_jd(text)
    assert any(
        i.lower().startswith("strong sql and relational database skills")
        for i in parsed.required_for_rating
    )
    # The flat keyword list is unchanged for consumers that want fragments.
    assert not any(i.lower().startswith("strong sql and relational") for i in parsed.required)


def test_short_skill_lists_still_split_in_required_items() -> None:
    parsed = parse_jd(SAMPLE_JD)
    assert "Angular" in parsed.required_for_rating
    assert "React" in parsed.required_for_rating or any(
        "React" in i for i in parsed.required_for_rating
    )


def test_a_such_as_list_is_one_alternatives_requirement_in_the_parsed_posting() -> None:
    parsed = parse_jd(
        "Backend Developer\n\n"
        "## Required Skills\n"
        "- Experience using AI-assisted development tools such as GitHub Copilot, Claude Code, "
        "or Cursor\n"
        "- Strong C# and .NET Core experience in production systems\n"
    )
    assert "GitHub Copilot / Claude Code / Cursor" in parsed.required_for_rating
    for single in ("GitHub Copilot", "Claude Code", "Cursor"):
        assert single not in parsed.required_for_rating


def test_a_short_bullet_choosing_between_same_kind_tools_is_one_requirement() -> None:
    parsed = parse_jd(
        "Backend Developer\n\n## Required Skills\n- AWS or Azure\n- Entity Framework/Dapper\n"
        "- C# and SQL\n"
    )
    assert parsed.required_for_rating == ["AWS / Azure", "Entity Framework / Dapper", "C#", "SQL"]


@pytest.mark.parametrize(
    ("bullet", "expected"),
    [
        ("Experience with Azure or Google Cloud", "Azure / Google Cloud"),
        ("Experience with React or Angular", "React / Angular"),
        ("Angular or React experience", "Angular / React"),
        ("Proficiency in C# or Java", "C# / Java"),
        ("Experience with SQL Server or PostgreSQL", "SQL Server / PostgreSQL"),
        ("Strong experience with AWS, Azure, or GCP", "AWS / Azure / GCP"),
    ],
)
def test_an_either_or_bullet_with_filler_words_is_one_requirement(
    bullet: str, expected: str
) -> None:
    parsed = parse_jd(f"Backend Developer\n\n## Required Skills\n- {bullet}\n")
    assert parsed.required == [expected]
    assert parsed.required_for_rating == [expected]


def test_two_tools_joined_by_and_stay_two_requirements_with_filler_words() -> None:
    parsed = parse_jd(
        "Backend Developer\n\n## Required Skills\n- Experience with Docker and Kubernetes\n"
    )
    assert parsed.required_for_rating == ["Docker", "Kubernetes"]


def test_an_either_or_between_different_kinds_of_tool_is_not_merged() -> None:
    parsed = parse_jd(
        "Backend Developer\n\n## Required Skills\n- Experience with Azure or Docker\n"
    )
    assert "Azure / Docker" not in parsed.required_for_rating


def test_an_orm_choice_inside_a_long_bullet_is_one_requirement() -> None:
    parsed = parse_jd(
        "Backend Developer\n\n## Required Skills\n"
        "- Proficiency with .NET Core, Entity Framework/ Dapper, and Web APIs\n"
    )
    assert "Entity Framework / Dapper" in parsed.required_for_rating
    assert "Dapper" not in parsed.required_for_rating


def test_an_ambiguous_word_is_listed_once_to_confirm_and_never_scored() -> None:
    parsed = parse_jd(
        "Backend Developer\n\n## Required Skills\n"
        "- Solid CI/CD practices and pipelines\n"
        "- Solid grasp of unit testing in production systems\n"
        "- Knowledge of SOLID principles in production systems\n"
    )
    # "Solid grasp of…" is ordinary English (the adjective rule); "Solid CI/CD practices" is asked
    assert parsed.terms_to_confirm == (("solid", "Solid CI/CD practices and pipelines"),)
    assert "SOLID" in parsed.required_for_rating  # the capitals line is the skill
    assert "Solid" not in parsed.required_for_rating


# ── title and company from the shapes real postings arrive in ────────────────────────────


@pytest.mark.parametrize(
    ("text", "title", "company"),
    [
        # a copied web page: the first line carries both
        (
            "Sr. Software Engineer (.NET core, Angular) | Example Co\n11 minutes\n\n"
            "Sr. Software Engineer (.NET core, Angular)\n\nCanada · 5 days ago\n\n"
            "About the job\n\nAbout Example CoExample Co helps customers.\n",
            "Sr. Software Engineer (.NET core, Angular)",
            "Example Co",
        ),
        (
            "Backend Developer at Example Co\n\nRequirements\n- C#\n",
            "Backend Developer",
            "Example Co",
        ),
        ("Backend Developer | Remote | Example Co\n", "Backend Developer", "Example Co"),
        # label lines, plain or bold
        ("Role: Web Developer\nCompany: Example Co\n", "Web Developer", "Example Co"),
        ("**Job Title:** QA Analyst\n**Company:** Example Co\n", "QA Analyst", "Example Co"),
        # a "#" inside a heading-style title or company (C#, F#) is part of the name
        (
            "# Company\nExample Co\n# Position\nSenior Developer (C#/MS-SQL) - Western Canada\n",
            "Senior Developer (C#/MS-SQL)",
            "Example Co",
        ),
        ("# Company\nC# Shop\n# Position\nWeb Developer\n", "Web Developer", "C# Shop"),
        # "About <Company>" on its own line, when nothing better is given
        ("Great opportunity\n\nAbout Example Co\nWe build things.\n", "Unknown Role", "Example Co"),
    ],
)
def test_title_and_company_are_read_from_the_shapes_postings_arrive_in(
    text: str, title: str, company: str
) -> None:
    parsed = parse_jd(text)
    assert (parsed.title, parsed.company) == (title, company)


@pytest.mark.parametrize(
    "text",
    [
        # "role" inside a sentence is not a label
        "The Role\n\nExample Co is looking for a developer. This is a fully remote role open to "
        "candidates in the United States and Canada.\n",
        # "at" inside a word ("that", "relate") is not "at <Company>"
        "Overview\n\nWork that You Will Do daily relates to platforms.\n",
        # a first line that is a sentence, or names no role, is not a title
        "We are hiring a developer to join our team.\n",
        "Job Description\n\nSome prose.\n",
        "About us\nWe build things.\n",
    ],
)
def test_prose_never_becomes_the_title_or_company(text: str) -> None:
    parsed = parse_jd(text)
    assert (parsed.title, parsed.company) == ("Unknown Role", "Unknown Company")


def test_a_pasted_posting_gets_a_readable_application_folder_name() -> None:
    from jobomatic import paths

    parsed = parse_jd(
        "Sr. Software Engineer (.NET core, Angular) | Example Co\n\nAbout the job\nBuild things.\n"
    )
    name = paths.folder_name("2026-11-05", parsed.company, parsed.title)
    assert name == "2026-11-05_example-co_sr-software-engineer-net-core-angular"


def test_a_possible_typo_is_listed_once_with_its_line_and_never_scored() -> None:
    parsed = parse_jd(
        "Backend Developer\n\n## Required Skills\n"
        "- Experience with Typscript and Angular in production systems\n"
        "- Typscript testing with Jest in production systems\n"
    )
    assert parsed.possible_typos == (
        (
            "Typscript",
            "typescript",
            "Experience with Typscript and Angular in production systems",
        ),
    )
    assert "Typscript" not in " ".join(parsed.required_for_rating)


def test_a_short_bullet_of_a_term_plus_filler_is_searched_as_the_term() -> None:
    parsed = parse_jd(
        "Dev\n\n## Requirements\n"
        "- Strong Postgresql skills\n"
        "- Good SQL knowledge\n"
        "- Azure fundamentals\n"
        "- Excellent communication\n"
    )
    # "Azure fundamentals" keeps its wording: no meaningful word is dropped. The soft skill is
    # listed, not scored (ADR 0023).
    assert parsed.required == ["Postgresql", "SQL", "Azure fundamentals"]
    assert [(r.kind, r.line) for r in parsed.soft_requirements] == [
        ("soft skill", "Excellent communication")
    ]


@pytest.mark.parametrize(
    "line,expected_nice",
    [
        ("Preferred: experience with Kubernetes in production environments", "Kubernetes"),
        ("Nice to have: GraphQL", "GraphQL"),
        ("Terraform (preferred)", "Terraform"),
        ("Kubernetes experience is a plus", "Kubernetes"),
        ("Knowledge of Redis would be an asset", "Redis"),
        ("Experience with Redis, a bonus", "Redis"),
    ],
)
def test_a_line_that_marks_itself_optional_is_a_nice_to_have_under_a_required_heading(
    line: str, expected_nice: str
) -> None:
    parsed = parse_jd(f"# Dev\n\n## Requirements\n- Experience with Docker\n- {line}\n")
    assert parsed.required == ["Docker"]
    assert parsed.nice_to_have == [expected_nice]


def test_a_required_line_without_a_marker_stays_required() -> None:
    parsed = parse_jd("# Dev\n\n## Requirements\n- Strong C# skills\n- Experience with Docker\n")
    assert parsed.required == ["C#", "Docker"]
    assert parsed.nice_to_have == []


def test_a_preferred_marker_does_not_change_the_line_it_is_removed_from_otherwise() -> None:
    marked = parse_jd(
        "# Dev\n\n## Requirements\n"
        "- Preferred: experience building Azure applications using event-driven architectures\n"
    )
    plain = parse_jd(
        "# Dev\n\n## Nice to have\n"
        "- Experience building Azure applications using event-driven architectures\n"
    )
    assert marked.required == []
    assert marked.nice_to_have == plain.nice_to_have


@pytest.mark.parametrize(
    "line",
    [
        "Knowledge of Azure (preferred but not mandatory)",
        "Azure is not mandatory",
        "Azure, preferred but not mandatory",
    ],
)
def test_preferred_but_not_mandatory_marks_a_line_as_a_nice_to_have(line: str) -> None:
    parsed = parse_jd(f"# Dev\n\n## Requirements\n- Experience with Docker\n- {line}\n")
    assert parsed.required == ["Docker"]
    assert [t.lower() for t in parsed.nice_to_have] == ["azure"]


def test_a_tool_named_after_such_as_is_matched_as_one_of_the_alternatives() -> None:
    parsed = parse_jd(
        "# Dev\n\n## Requirements\n"
        "- Familiarity with Agile methodologies and version control tools such as Git, Bitbucket.\n"
    )
    assert "Git / Bitbucket" in parsed.required


def test_strongly_preferred_keeps_a_line_required_even_with_nice_to_have_wording() -> None:
    parsed = parse_jd(
        "# Dev\n\n## Requirements\n- Kubernetes experience is nice to have but strongly preferred\n"
    )
    assert "Kubernetes" in " ".join(parsed.required)
    assert parsed.nice_to_have == []


# ── "preferably" / "ideally": only the part after the word is optional ──


def test_preferably_makes_only_what_follows_it_a_nice_to_have():
    parsed = parse_jd(
        "Dev\n\n## Minimum Qualifications\n"
        "- 8+ years of software development experience, preferably in SaaS or cloud products\n"
        "- Experience with C#\n"
    )
    assert parsed.required_for_rating == ["C#"]
    assert "SaaS" in parsed.nice_to_have
    assert [s.minimum_years for s in parsed.soft_requirements] == [8]


def test_ideally_works_like_preferably_and_keeps_the_required_part():
    parsed = parse_jd("Dev\n\n## Requirements\n- Experience with Docker, ideally Kubernetes\n")
    assert parsed.required_for_rating == ["Docker"]
    assert parsed.nice_to_have == ["Kubernetes"]


def test_a_line_that_starts_with_preferably_is_wholly_optional():
    parsed = parse_jd("Dev\n\n## Requirements\n- Preferably experience with Kubernetes\n- C#\n")
    assert parsed.required_for_rating == ["C#"]
    assert parsed.nice_to_have == ["Kubernetes"]


def test_strongly_preferred_still_leaves_the_line_required():
    parsed = parse_jd("Dev\n\n## Requirements\n- Azure experience, strongly preferred\n")
    assert parsed.required_for_rating == ["Azure experience, strongly preferred"]
    assert parsed.nice_to_have == []


# ── two bullets run together by a copy-paste ──


def test_a_full_stop_followed_by_a_dash_starts_a_new_bullet():
    parsed = parse_jd(
        "Dev\n\n## Requirements\n"
        "    Understands the product lifecycle.- Experience with AWS or other cloud platforms\n"
        "    Experience with Docker\n"
    )
    assert "AWS / Azure / GCP / Google Cloud" in parsed.required_for_rating
    assert "Docker" in parsed.required_for_rating


def test_a_dash_inside_a_sentence_is_not_a_new_bullet():
    parsed = parse_jd("Dev\n\n## Requirements\n- Node.js - Express experience\n")
    assert len(parsed.required_for_rating) >= 1


def test_solid_understanding_is_ordinary_english_and_not_asked_about() -> None:
    parsed = parse_jd(
        "Dev\n\n## Requirements\n- Has solid understanding of the product development lifecycle\n"
    )
    assert parsed.terms_to_confirm == ()


@pytest.mark.parametrize("heading", ["What Are The Must-haves..", "Must-Have Skills", "Must haves"])
def test_a_hyphenated_must_have_heading_starts_the_required_section(heading: str) -> None:
    parsed = parse_jd(f"Dev\n\n{heading}\n\n     Experience with Docker\n")
    assert parsed.required_for_rating == ["Docker"]


# ── "is a strong asset" and friends mark a line optional ──


@pytest.mark.parametrize(
    "marker", ["is a strong asset", "is a real plus", "would be a big bonus", "is an asset"]
)
def test_an_adjective_before_asset_plus_or_bonus_still_marks_the_line_optional(marker: str):
    parsed = parse_jd(f"Dev\n\n## Requirements\n- C#\n- Experience with React {marker}\n")
    assert parsed.required_for_rating == ["C#"]
    assert "React" in parsed.nice_to_have


# ── employer and title when the posting does not label them ──


def test_the_company_is_taken_from_an_opening_sentence_naming_it():
    parsed = parse_jd(
        "Position : Automation Developer\n\nExampleCo is the largest regional dealer group.\n"
        "\n## Requirements\n- Power Automate\n"
    )
    assert parsed.company == "ExampleCo"


def test_the_company_is_taken_from_a_name_repeated_three_times():
    parsed = parse_jd(
        "Principal Developer\n\nThe Docs team in Exampleware R&D seeks a developer. "
        "Join a cloud-powered Exampleware experience built with Exampleware tools.\n"
        "\n## Requirements\n- Java\n"
    )
    assert parsed.company == "Exampleware"


def test_a_skill_repeated_in_the_text_is_not_taken_for_the_company():
    parsed = parse_jd(
        "Developer\n\nWe use Python daily, with Python services, plus Python tooling.\n"
        "\n## Requirements\n- Java\n"
    )
    assert parsed.company == "Unknown Company"


def test_a_leading_requisition_number_is_removed_from_the_title():
    parsed = parse_jd("26WD100016, Principal Software Developer\n\n## Requirements\n- Java\n")
    assert parsed.title == "Principal Software Developer"


# ── the lead posting: sections, labels, boilerplate, certificates, level, unknown names ──

_LEAD = (
    "Software Development Lead | Example Retail Co\n\nYour Role:\n"
    "    Lead the design of software solutions.\n\n"
    "Desired Skills & Experience:\n"
    "    Minimum of 5 years of experience in large-scale software development.\n"
    "    Hands-on experience in Python, C#, and Oracle.\n"
    "    Knowledge of integration platforms such as Frobnicator or similar middleware "
    "is considered an asset.\n"
    "    Certification or formal training in Agile, DevOps is considered an asset.\n\n"
    "Location: 1 Main Street, Exampleton XX\n\nReports To: Director\n\n"
    "We create a collaborative culture by:\n\nBeing Enterprising\n"
    "    Committing to our Customer\n    Working with Passion\n"
    "    Building Trust Example Retail Co is committed to inclusion and diversity.\n"
)


def test_a_desired_skills_heading_starts_the_required_section():
    parsed = parse_jd(_LEAD)
    assert parsed.required_for_rating == ["Python", "C#", "Oracle"]


def test_labels_and_culture_and_closing_text_do_not_become_requirements():
    parsed = parse_jd(_LEAD)
    joined = " ".join(parsed.required + parsed.nice_to_have).lower()
    for junk in ("customer", "passion", "trust", "inclusion", "exampleton", "director"):
        assert junk not in joined


def test_a_certificate_line_among_the_assets_is_listed_and_never_scored():
    parsed = parse_jd(_LEAD)
    assert "Agile" not in parsed.nice_to_have and "DevOps" not in parsed.nice_to_have
    assert any(
        s.kind == "education" and s.note.startswith("optional") for s in parsed.soft_requirements
    )


def test_a_senior_title_is_listed_first_among_the_soft_requirements():
    parsed = parse_jd(_LEAD)
    assert parsed.soft_requirements[0].kind == "level"
    assert parsed.soft_requirements[0].line == "Software Development Lead"


def test_an_unrecognised_name_in_a_list_of_examples_is_reported_not_scored():
    parsed = parse_jd(_LEAD)
    assert [name for name, _ in parsed.unknown_names] == ["Frobnicator"]
    assert "Frobnicator" not in parsed.nice_to_have


# ── a Bounteous-style posting: Good-to-Have, Experience, "Skill: details", level in the body ──


@pytest.mark.parametrize("heading", ["Good-to-Have Skills", "Good to have", "Good-To-Haves:"])
def test_a_good_to_have_heading_starts_the_nice_to_have_section(heading: str) -> None:
    parsed = parse_jd(f"Dev\n\n## Must-Have Skills\n- C#\n\n## {heading}\n- Docker\n")
    assert parsed.required_for_rating == ["C#"]
    assert parsed.nice_to_have == ["Docker"]


@pytest.mark.parametrize("heading", ["Experience", "Relevant Experience:", "Required Experience"])
def test_a_bare_experience_heading_starts_the_required_section(heading: str) -> None:
    parsed = parse_jd(
        f"Dev\n\n{heading}\n\n    6+ years of development\n    Experience with Docker\n"
    )
    assert parsed.required_for_rating == ["Docker"]
    assert [s.minimum_years for s in parsed.soft_requirements if s.kind == "years"] == [6]


def test_a_skill_with_a_detail_list_after_a_colon_is_scored_as_the_skill_only() -> None:
    parsed = parse_jd(
        "Dev\n\n## Requirements\n"
        "- React: Components, Hooks, state management, reusable UI design, and performance.\n"
        "- Node.js: REST APIs, authentication/authorization, error handling, and logging.\n"
    )
    assert parsed.required_for_rating == ["React", "Node.js"]


@pytest.mark.parametrize(
    "line",
    [
        "Monitoring: Datadog, Splunk",  # a kind of tool: the list IS the requirement
        "Languages: C#, Java, Python",  # the head is not a skill
        "Experience across the complete SDLC: design, testing, deployment",  # head too long
    ],
)
def test_a_detail_list_is_kept_when_the_head_is_not_one_plain_skill(line: str) -> None:
    parsed = parse_jd(f"Dev\n\n## Requirements\n- {line}\n")
    assert len(parsed.required_for_rating) >= 1
    joined = " ".join(parsed.required_for_rating).lower()
    assert any(word in joined for word in ("datadog", "c#", "sdlc"))


def test_a_requirement_named_in_two_lists_counts_once() -> None:
    parsed = parse_jd(
        "Dev\n\nExperience\n    Strong hands-on experience with React, Node.js and SQL.\n\n"
        "Must-Have Skills\n    React: Components and Hooks.\n    SQL: Strong query-writing skills.\n"
    )
    names = [item.lower() for item in parsed.required_for_rating]
    assert names.count("react") == 1 and names.count("sql") == 1


def test_a_level_written_before_the_title_in_the_text_is_listed_when_the_title_has_none() -> None:
    parsed = parse_jd(
        "Full Stack Engineer | Example Co\n\nWe are looking for a Senior Full Stack Engineer "
        "who owns an application.\n\n## Requirements\n- React\n"
    )
    levels = [s for s in parsed.soft_requirements if s.kind == "level"]
    assert [s.line for s in levels] == ["Senior Full Stack Engineer"]


def test_no_level_line_is_added_when_the_text_names_none() -> None:
    parsed = parse_jd("Full Stack Engineer | Example Co\n\n## Requirements\n- React\n")
    assert not [s for s in parsed.soft_requirements if s.kind == "level"]


def test_an_ai_assisted_automation_line_becomes_an_ai_row_and_a_workflow_automation_row() -> None:
    parsed = parse_jd("Dev\n\n## Requirements\n- Modern AI-assisted automation techniques\n- C#\n")
    assert parsed.required_for_rating == ["AI", "Workflow Automation", "C#"]


def _required(*bullets: str) -> list[str]:
    body = "".join(f"- {b}\n" for b in bullets)
    return parse_jd(f"Dev\n\n## Requirements\n{body}").required_for_rating


@pytest.mark.parametrize(
    "bullet",
    ["CI/CD", "CI/CD pipelines", "Experience with CI/CD pipelines", "ci/cd"],
)
def test_ci_cd_is_one_requirement_not_ci_and_cd(bullet: str) -> None:
    assert _required(bullet, "C#") == [
        bullet.split()[-1] if bullet.lower() == "ci/cd" else "CI/CD",
        "C#",
    ]


def test_a_slash_between_alternatives_is_still_one_choice_row() -> None:
    assert _required("Jenkins/TeamCity") == ["Jenkins / TeamCity"]


@pytest.mark.parametrize(
    ("bullet", "expected"),
    [
        ("Experience with Azure and REST APIs", ["Azure", "REST API"]),
        ("SQL Server and Entity Framework Core", ["SQL Server", "Entity Framework Core"]),
        ("Familiarity with Git, CI/CD and Docker", ["Git", "CI/CD", "Docker"]),
    ],
)
def test_a_list_of_skills_in_a_sentence_is_one_row_per_skill(
    bullet: str, expected: list[str]
) -> None:
    # The posting asks for all of them, so a gap in one must not hide behind evidence for another.
    assert _required(bullet) == expected


@pytest.mark.parametrize(
    ("bullet", "expected"),
    [
        # a meaningful word remains, so the sentence is rated whole, as before
        (
            "Object-oriented programming and software design principles",
            ["Object-oriented programming and software design principles"],
        ),
        (
            "REST API design and microservices architecture",
            ["REST API design and microservices architecture"],
        ),
        # alternatives and examples keep their existing handling
        (
            "Solid backend programming experience in C#/.NET, or a comparable language such as Java",
            ["C#", ".NET", "Java"],
        ),
    ],
)
def test_a_sentence_that_is_not_only_a_list_of_skills_is_handled_as_before(
    bullet: str, expected: list[str]
) -> None:
    assert _required(bullet) == expected


# -- lists, parentheses and version floors (ADR 0009) -------------------------------------------


def _required(*lines: str) -> list[str]:
    body = "\n".join(f"- {line}" for line in lines)
    return parse_jd(f"Developer\n\n## Requirements\n{body}\n").required_for_rating


def test_a_bare_comma_list_is_one_requirement_per_name():
    assert _required("SSRS, SSIS, Crystal Reports", "Sharepoint, Sharepoint Online") == [
        "SSRS",
        "SSIS",
        "Crystal Reports",
        "Sharepoint",
        "Sharepoint Online",
    ]


def test_a_parenthesis_is_detail_on_its_line_and_is_never_split():
    assert _required("JavaScript (utilizing JSON and AJAX)") == [
        "JavaScript (utilizing JSON and AJAX)"
    ]
    assert _required("Microsoft .NET Platform (4.0 or higher)") == [
        "Microsoft .NET Platform (4.0 or higher)"
    ]


def test_a_version_floor_is_not_a_second_skill():
    assert _required("Microsoft SQL Server 2008 or later") == ["Microsoft SQL Server 2008 or later"]
    assert _required("Java 11 or higher, Spring") == ["Java 11", "Spring"]


def test_a_comma_that_adds_a_qualifier_is_not_a_list():
    assert _required("Azure experience, strongly preferred") == [
        "Azure experience, strongly preferred"
    ]


def test_a_heading_with_detail_keeps_its_list():
    assert _required("Monitoring: Datadog, Splunk") == ["Monitoring: Datadog, Splunk"]


# -- the offer section is not a requirements list (ADR 0009) ---------------------------------------


_OFFER_POSTING = """Developer - Springfield, ON

Requirements:

    C#
    SQL Server
    Experience with Agile development techniques

{heading}

    An IT consulting practice with over 35 years of experience across Canada
    Exciting employee ownership options
    Support for your professional development program
"""


@pytest.mark.parametrize(
    "heading",
    [
        "What you can expect from us:",
        "What you'll get:",
        "What you will receive",
        "What we provide:",
        "What's in it for you",
        "In return:",
        "Our offer",
        "We offer:",
        "Total rewards",
        "Life at Acme",
    ],
)
def test_an_offer_section_heading_ends_the_requirements(heading):
    parsed = parse_jd(_OFFER_POSTING.format(heading=heading))
    assert parsed.required_for_rating == [
        "C#",
        "SQL Server",
        "Experience with Agile development techniques",
    ]
    assert not any(
        r.kind == "years" for r in parsed.soft_requirements
    )  # the "35 years" is the firm


def test_what_you_will_bring_still_opens_the_requirements():
    parsed = parse_jd("Developer\n\n## What you'll bring\n- C#\n- SQL Server\n")
    assert parsed.required_for_rating == ["C#", "SQL Server"]


# -- more headings, run-together headings, qualities and APIs (ADR 0009, 0023) -----------------


@pytest.mark.parametrize(
    "heading",
    [
        "✨ What You Bring",
        "What you bring",
        "You Should Get In Touch If",
        "You should have",
        "About you",
        "Your background",
        "The ideal candidate",
    ],
)
def test_more_requirements_headings_open_the_list(heading: str) -> None:
    parsed = parse_jd(f"Developer\n\n{heading}\n\n    C#\n    SQL Server\n")
    assert parsed.required_for_rating == ["C#", "SQL Server"]


@pytest.mark.parametrize(
    "heading",
    ["Why this role is unique", "Why you'll love it", "Benefits Overview", "Additional Perks",
     "About Acme Corp:", "What You'll Find Here"],
)  # fmt: skip
def test_more_closing_headings_end_the_list(heading: str) -> None:
    parsed = parse_jd(
        f"Developer\n\nRequirements\n\n    C#\n\n{heading}\n\n    Free snacks\n    Yoga\n"
    )
    assert parsed.required_for_rating == ["C#"]


def test_about_you_and_about_the_role_do_not_end_the_list() -> None:
    parsed = parse_jd("Developer\n\nRequirements\n\n    C#\n\nAbout you\n\n    SQL Server\n")
    assert parsed.required_for_rating == ["C#", "SQL Server"]


def test_a_heading_run_into_the_next_sentence_is_split_from_it() -> None:
    parsed = parse_jd(
        "Developer\n\nRequirements\n\n    C#\n\n"
        "What You'll Find HereTo do great work, you need to be well. We offer cake.\n"
        "    Mind: tools and support\n    Body: health coverage\n"
    )
    assert parsed.required_for_rating == ["C#"]


def test_a_sentence_run_into_the_next_heading_is_split_from_it() -> None:
    parsed = parse_jd(
        "Developer\n\nRequirements\n\n    C#\n\nWe hire across teams.Benefits Overview\n"
        "    Free snacks\n"
    )
    assert parsed.required_for_rating == ["C#"]


def test_a_sentence_at_the_left_margin_ends_an_indented_list() -> None:
    parsed = parse_jd(
        "Developer\n\nRequirements\n\n    C#\n    SQL Server\n\n"
        "We hire across several teams and will match you to the best fit.\n"
    )
    assert parsed.required_for_rating == ["C#", "SQL Server"]


def test_a_flat_list_of_unindented_sentences_still_counts() -> None:
    parsed = parse_jd("Developer\n\nRequirements\n\nExperience with C# and SQL Server.\n")
    assert parsed.required_for_rating  # nothing marked the list, so the line is read as before


def test_qualities_written_as_sentences_are_listed_not_scored() -> None:
    parsed = parse_jd(
        "Developer\n\nRequirements\n\n"
        "    C#\n"
        "    You care about outcomes, not just output.\n"
        "    Strong ownership, with the ability to take vague problems to a shipped solution.\n"
        "    You are comfortable working across different technical systems and concerns.\n"
    )
    assert parsed.required_for_rating == ["C#"]
    assert len([s for s in parsed.soft_requirements if s.kind == "soft skill"]) == 3


def test_a_capability_sentence_with_no_known_skill_is_still_rated() -> None:
    parsed = parse_jd(
        "Developer\n\nRequirements\n\n    Experience troubleshooting production issues end-to-end\n"
    )
    assert parsed.required_for_rating  # a capability the profile can be searched for, not a quality


def test_api_work_is_a_skill_not_a_sentence_to_match_whole() -> None:
    parsed = parse_jd(
        "Developer\n\nRequirements\n\n    Experience building APIs and integrating with external systems\n"
    )
    assert "API" in parsed.required_for_rating


# ── asterisk bullets (Indeed pastes) ──


def test_asterisk_bullets_are_read_as_a_required_list() -> None:
    parsed = parse_jd(
        "Developer\n\n## Requirements\n\n* C#\n* Microsoft SQL Server 2008 or later\n* Silverlight\n"
    )
    assert parsed.required == ["C#", "Microsoft SQL Server 2008", "Silverlight"]


def test_asterisk_bullets_match_dash_bullets() -> None:
    star = parse_jd("Developer\n\n## Requirements\n\n* C#\n* Docker\n")
    dash = parse_jd("Developer\n\n## Requirements\n\n- C#\n- Docker\n")
    assert star.required == dash.required


def test_bold_and_italic_lines_are_not_asterisk_bullets() -> None:
    parsed = parse_jd("Developer\n\n**Requirements:**\n\n- C#\n- Docker\n\n*Apply today*\n")
    assert parsed.required == ["C#", "Docker"]


# ── web-service protocol terms (SOAP, WSDL, WCF) ──


def test_a_soa_line_names_soap_wsdl_and_wcf_as_requirements() -> None:
    parsed = parse_jd(
        "Developer\n\n## Requirements\n"
        "- Experience with Service Oriented Architectures (SOA), with implementations using "
        "Web Services (WSDL, SOAP, XML, and XML Schemas) and Windows Communication Foundation (WCF)\n"
    )
    required = {item.lower() for item in parsed.required_for_rating}
    assert {"soap", "wsdl", "wcf"} <= required


def test_soap_in_lowercase_prose_is_not_the_protocol() -> None:
    parsed = parse_jd("Dev\n\n## Requirements\n- Comfortable working with soap and water\n- C#\n")
    assert "soap" not in {item.lower() for item in parsed.required_for_rating}


# ── fixes found by running real LinkedIn pastes (Quest, Clover, Atlassian, IDENTOS, Lime, ...) ──


def test_an_even_better_heading_opens_the_nice_to_have_list() -> None:
    """Atlassian: "If You've Got These Skills, Even Better" put AWS, Java and Rust in required."""
    text = "# Dev\n\n## Qualifications\n- C#\n\nIf You've Got These Skills, Even Better\n\n- AWS\n- Rust\n"
    parsed = parse_jd(text)
    assert parsed.required == ["C#"]
    assert parsed.nice_to_have == ["AWS", "Rust"]


def test_a_plus_in_brackets_makes_only_those_words_optional() -> None:
    """IDENTOS: "(UML a plus)" moved object-oriented, OpenAPI and Swagger to nice-to-have."""
    text = (
        "# Dev\n\n## Must-Have\n"
        "- Solid object-oriented design and documenting designs with OpenAPI/Swagger (UML a plus)\n"
        "- Git\n"
    )
    parsed = parse_jd(text)
    assert "object-oriented" in parsed.required
    assert "OpenAPI" in parsed.required and "Git" in parsed.required
    assert parsed.nice_to_have == ["UML"]


def test_a_bracket_with_only_a_marker_still_makes_the_whole_line_optional() -> None:
    parsed = parse_jd("# Dev\n\n## Requirements\n- C#\n- Terraform (a bonus)\n")
    assert parsed.required == ["C#"]
    assert parsed.nice_to_have == ["Terraform"]


def test_two_slash_stacks_joined_by_or_are_one_choice() -> None:
    """IDENTOS: Java/Spring/Hibernate or React/TypeScript required both stacks (Spring a core gap)."""
    text = (
        "# Dev\n\n## Must-Have\n"
        "- 2+ years of working experience and proficiency in Java/Spring/Hibernate or "
        "React/TypeScript, with working familiarity with the other\n"
    )
    assert parse_jd(text).required == ["Java / Spring / Hibernate / React / TypeScript"]


def test_a_company_name_ending_in_a_period_does_not_hide_the_title() -> None:
    """IDENTOS: the "." of "Inc." made the first line look like a sentence ("Unknown Role")."""
    parsed = parse_jd(
        "Software Developer (12 month Contract) | IDENTOS Inc.\n\n## Requirements\n- C#\n"
    )
    assert parsed.title.startswith("Software Developer")
    assert "IDENTOS" in parsed.company


@pytest.mark.parametrize(
    "line",
    [
        "- Technical proficiency to understand the design and implementation of projects",
        "    Technical proficiency to understand the design of projects",
        "    Experience with large lumber mill equipment.",  # six words: rated whole before
    ],
)
def test_a_required_sentence_naming_no_skill_is_listed_not_rated(line: str) -> None:
    """Part A: rated whole, such a line could only ever read as a gap (Clover, Lime, Super.com)."""
    parsed = parse_jd(f"# Dev\n\n## Requirements\n- C#\n{line}\n")
    assert parsed.required == ["C#"]
    assert [item.strip() for item in parsed.unscored_required] == [
        line.strip().removeprefix("- ").rstrip(".")
    ]


def test_a_description_of_the_employers_stack_is_not_a_requirement_list() -> None:
    """Super.com: "Our Technology" bullets were read as nice-to-haves, with duplicate rows."""
    text = (
        "# Dev\n\n## Requirements\n- C#\n\nBonus Points For\n- SQL\n\n"
        "Our Technology\n- We use Postgres, Redis and Kubernetes on AWS.\n"
    )
    assert parse_jd(text).nice_to_have == ["SQL"]


def test_imp_heading_opens_a_quoted_paragraph_of_requirements() -> None:
    """Accion Labs: "Imp:" then a quoted paragraph (ending in ."), none of it was read."""
    text = (
        '# Dev\n\nQualifications:\n\n    Strong C#.\n\nImp:\n\n"Proven expertise in designing '
        'RESTful APIs, including authentication using JWT tokens. Strong grasp of design patterns."\n'
    )
    required = parse_jd(text).required
    assert any("JWT" in item for item in required) and "design patterns" in required


def test_a_heading_that_merely_contains_imp_is_not_a_requirements_heading() -> None:
    """ "Implementation details" does not open the required list: Kubernetes stays out of it."""
    parsed = parse_jd("# Dev\n\n## Preferred\n- C#\n\nImplementation details\n- Kubernetes\n")
    assert "Kubernetes" not in parsed.required


# ── fixes found by the HCLTech paste (a flat page: no bullets, no indent, a "Company • City" line) ──


def test_the_company_is_read_from_a_company_and_location_header_line() -> None:
    parsed = parse_jd(
        "C# SQL Developer (Remote)\n\nHCLTech • Canada (Remote)\n\n## Requirements\n- C#\n"
    )
    assert parsed.title == "C# SQL Developer (Remote)"
    assert parsed.company == "HCLTech"


def test_flat_lines_under_a_colon_heading_are_its_items_until_the_closing_sentence() -> None:
    text = (
        "# Dev\n\n✅ Required Skills:\n\n5-8 years of experience\n\n"
        "Strong programming expertise in C#\n\nStrong experience with SQL Server and database "
        "development\n\n📩 Interested or know someone who would be a great fit? Apply now.\n"
    )
    parsed = parse_jd(text)
    assert parsed.required == ["C#", "SQL Server"]
    assert parsed.unscored_required == ()


def test_flat_lines_after_a_heading_with_no_colon_are_still_not_items() -> None:
    parsed = parse_jd("# Dev\n\nRequirements\n\nPython\n\nAzure\n")
    assert parsed.required == []


def test_flat_lines_after_an_unknown_colon_heading_are_not_items() -> None:
    text = "# Dev\n\nRequired Skills:\n\nC#\n\nSomething else entirely:\n\nSomeone's hobbies\n"
    assert parse_jd(text).required == ["C#"]


def test_work_authorization_is_listed_for_the_user_and_never_scored() -> None:
    parsed = parse_jd("# Dev\n\n## Requirements\n- C#\n- Authorized to work in Canada\n")
    assert parsed.required == ["C#"]
    assert [s.kind for s in parsed.soft_requirements if s.kind == "eligibility"] == ["eligibility"]


# --- Round three: the LinkedIn job card, trait lines, either/or lines ---------------------------

_CARD = (
    "Company logo for, {company}.\n\n{company}\n\n{title} \n\n"
    "Canada · 6 days ago · Over 100 applicants\n\nRemote\nFull-time\n\nAbout the job\n\n"
    "What we're looking for\n\n    Angular\n    Python\n"
)


@pytest.mark.parametrize(
    "company,title",
    [
        ("ClickUp", "Staff Frontend Engineer"),
        ("Quantum World Technologies Inc.", "Full Stack Engineer"),
        ("Prompt.io", "Software Engineer"),
    ],
)
def test_a_linkedin_job_card_header_gives_title_and_company(company: str, title: str) -> None:
    parsed = parse_jd(_CARD.format(company=company, title=title))
    assert (parsed.title, parsed.company) == (title, company)


def test_the_job_card_title_wins_over_a_body_label() -> None:
    text = _CARD.format(company="AspiringIT", title="Software Architect (C#, .Net, Azure)")
    parsed = parse_jd(text + "\nJob title: Something else\n")
    assert parsed.title == "Software Architect (C#, .Net, Azure)"


def test_ideal_candidate_also_has_opens_the_nice_to_have_list() -> None:
    parsed = parse_jd(
        "# Dev\n\nMinimum requirements for the role:\n    Python\n\n"
        "An ideal candidate also has:\n    Docker\n"
    )
    assert "Python" in parsed.required
    assert "Docker" not in parsed.required
    assert "Docker" in parsed.nice_to_have


def test_ideal_candidate_alone_is_still_a_requirements_heading() -> None:
    parsed = parse_jd("# Dev\n\nIdeal candidate\n    Python\n")
    assert parsed.required == ["Python"]


@pytest.mark.parametrize(
    "line",
    [
        "You are motivated by accountability",
        "You are results-oriented",
        "Customer obsessed. You put the customer first",
        "Strong programming/coding fundamentals",
    ],
)
def test_trait_lines_are_soft_skills_not_skill_rows(line: str) -> None:
    parsed = parse_jd(f"# Dev\n\n## Requirements\n- C#\n- {line}\n")
    assert parsed.required == ["C#"]
    assert [s.kind for s in parsed.soft_requirements] == ["soft skill"]


def test_how_you_work_is_a_soft_section() -> None:
    parsed = parse_jd(
        "# Dev\n\n## What we're looking for\n- C#\n\nHOW YOU WORK\n"
        "    You take ownership of your work and follow through on commitments.\n"
        "    You write Python every day.\n"
    )
    assert parsed.required == ["C#"]


def test_a_call_to_action_ends_the_requirements_list() -> None:
    parsed = parse_jd(
        "# Dev\n\nWhat We're Looking For\n\nGit workflows\n\nAccess to a computer\n\n"
        "Why Apply?\n\n100% Asynchronous & Flexible: pick tasks around your schedule\n\nApply Now!\n"
    )
    joined = " ".join(parsed.required).lower()
    assert "apply" not in joined
    assert "asynchronous" not in joined
    assert not any("apply" in line.lower() for line in parsed.unscored_required)


def test_a_linkedin_category_suffix_is_not_part_of_the_skill() -> None:
    parsed = parse_jd(
        "# Dev\n\nRequirements\n\n• 2+ years of work experience with Python (Programming Language)\n"
    )
    assert not any("programming language" in item.lower() for item in parsed.required)


def test_a_plain_or_line_is_one_choice_row() -> None:
    parsed = parse_jd("# Dev\n\n## Requirements\n- Fullstack or backend development experience\n")
    assert parsed.required == ["Fullstack / backend development experience"]


def test_eligibility_in_closing_boilerplate_is_listed_but_a_long_paragraph_is_not() -> None:
    short = "Applicants must be authorized to work in the United States or Canada."
    long = " ".join(["word"] * 45) + " the legal right to work at the company."
    parsed = parse_jd(f"# Dev\n\n## Requirements\n- C#\n\nEqual opportunity\n{short}\n{long}\n")
    assert [s.line for s in parsed.soft_requirements if s.kind == "eligibility"] == [short]


# --- Round four: headers without a logo line, long heading-like sentences, optional marker -----


def test_a_job_card_without_the_logo_line_gives_title_and_company() -> None:
    parsed = parse_jd(
        "Render\n\nSoftware Engineer, Expansion (all levels) \n\n"
        "Canada · 1 day ago · Over 100 people clicked apply\n\nRemote\n\n"
        "What We're Looking For\n    Python\n"
    )
    assert (parsed.title, parsed.company) == ("Software Engineer, Expansion (all levels)", "Render")


def test_a_title_pipe_company_first_line_is_not_taken_for_a_card() -> None:
    parsed = parse_jd(
        "Senior Software Engineer | Samsara\n\nSenior Software Engineer\n\n"
        "Canada · Reposted 1 week ago · Over 100 people clicked apply\n\nRequirements\n    Python\n"
    )
    assert parsed.company == "Samsara"


def test_a_long_sentence_holding_a_heading_word_does_not_open_a_section() -> None:
    parsed = parse_jd(
        "# Dev\n\nAbout You\n    Python\n\n"
        "We treat tools like Cursor as core infrastructure, not nice-to-haves, day to day you will\n"
        "    Build web applications with Docker\n"
    )
    assert "Docker" not in parsed.nice_to_have
    assert "Docker" not in parsed.required


def test_a_wrapped_if_you_dont_meet_every_requirement_line_ends_the_list() -> None:
    parsed = parse_jd(
        "# Dev\n\nAbout You\n    Python\n\n"
        "If you don't meet 100% of the above qualifications, you should still\n"
        " consider applying.\n"
    )
    assert parsed.required == ["Python"]
    assert not parsed.unscored_required


def test_a_colon_ended_heading_may_be_long() -> None:
    parsed = parse_jd(
        "# Dev\n\nThings we're looking for in terms of more specific skill-sets and experience:\n"
        "    Python\n"
    )
    assert parsed.required == ["Python"]


def test_an_optional_bracket_marks_the_line_as_nice_to_have() -> None:
    parsed = parse_jd("# Dev\n\n## Requirements\n- Python\n- WordPress (Optional)\n")
    assert parsed.required == ["Python"]
    assert parsed.nice_to_have == ["WordPress"]


def test_the_required_line_count_includes_soft_and_unscored_lines() -> None:
    parsed = parse_jd(
        "# Dev\n\n## Requirements\n- Python\n- Strong communication skills\n"
        "- Experience with large lumber mill equipment\n"
    )
    assert parsed.required_line_count == 3


# --- Round five: Indeed header, "plus" per sentence, eligibility, years in words -----------------


@pytest.mark.parametrize(
    "first_lines,title",
    [
        (
            "ca.indeed.com\nSenior Full Stack Engineer - Remote - Indeed.com\n",
            "Senior Full Stack Engineer",
        ),
        (
            "ca.indeed.com\nSenior Full-Stack Web Developer (C#/MS-SQL/Front-end) - Western Canada - "
            "Saskatoon, SK S7K 5T6 - Indeed.com\n",
            "Senior Full-Stack Web Developer (C#/MS-SQL/Front-end)",
        ),
        (
            "ca.indeed.com\nWeb Front End Developer - Canada - Indeed.com\n",
            "Web Front End Developer",
        ),
    ],
)
def test_an_indeed_paste_with_the_domain_on_its_own_line_gives_the_title(
    first_lines: str, title: str
) -> None:
    assert parse_jd(first_lines + "\nRequirements\n    Python\n").title == title


def test_a_company_that_opens_a_sentence_with_was_founded_is_the_company() -> None:
    parsed = parse_jd(
        "ca.indeed.com\nWeb Developer - Canada - Indeed.com\n\nBluestream was founded in 1997 as a "
        "database company.\n\nRequirements\n    Python\n"
    )
    assert parsed.company == "Bluestream"


def test_job_title_words_and_places_are_not_the_company() -> None:
    body = " ".join(["The Software team in Canada builds Software for Canada."] * 4)
    parsed = parse_jd(
        f"Senior Software Developer - Remote - Indeed.com\n\n{body}\n\nRequirements\n    Python\n"
    )
    assert parsed.company == "Unknown Company"


def test_a_plus_applies_only_to_the_sentence_it_stands_in() -> None:
    parsed = parse_jd(
        "# Dev\\n\\n## Requirements\\n".replace("\\n", "\n")
        + "- 5+ years of core front-end skills: HTML, CSS, Javascript. Experience with Vue is a plus.\n"
    )
    assert {"HTML", "CSS", "Javascript"} <= set(parsed.required)
    assert "Vue" in parsed.nice_to_have
    assert "Vue" not in parsed.required


def test_a_plus_in_a_one_sentence_line_still_moves_the_whole_line() -> None:
    parsed = parse_jd("# Dev\n\n## Requirements\n- Python\n- Docker is a plus\n")
    assert parsed.required == ["Python"]
    assert parsed.nice_to_have == ["Docker"]


def test_a_colon_run_into_a_years_figure_is_split() -> None:
    parsed = parse_jd(
        "# Dev\n\nRequirements:\n"
        "    Minimums apply - do not apply without them herein:5+ years of C# web development.\n"
    )
    assert parsed.required == ["C# web development"]
    assert any(
        s.kind == "years" and s.line.startswith("5+ years") for s in parsed.soft_requirements
    )


@pytest.mark.parametrize(
    "line",
    [
        "The successful candidate must be a Canadian Citizen or Permanent Resident.",
        "Candidates must be eligible to hold a Government of Canada Level 3 Security Clearance.",
        "This role is open to candidates residing in British Columbia, Alberta, or Ontario.",
    ],
)
def test_citizenship_clearance_and_residency_lines_are_listed_as_eligibility(line: str) -> None:
    parsed = parse_jd(f"# Dev\n\n## Requirements\n- Python\n\n{line}\n")
    assert [s.line for s in parsed.soft_requirements if s.kind == "eligibility"] == [line]


def test_years_written_with_a_word_and_a_bracketed_figure() -> None:
    parsed = parse_jd(
        "# Dev\n\n## Requirements\n- Six (6+) years of experience in software development.\n"
    )
    assert [s.note for s in parsed.soft_requirements if s.kind == "years"] == ["minimum 6 years"]


def test_additional_information_ends_the_preferred_list() -> None:
    parsed = parse_jd(
        "# Dev\n\nAdditional (Preferred) Requirements:\n    Docker\n\nAdditional Information\n"
        "Total compensation for this role is market competitive.\n"
    )
    assert parsed.nice_to_have == ["Docker"]


def test_a_vendor_named_before_its_product_is_not_the_company() -> None:
    body = "Microsoft SQL Server and Microsoft Azure; Microsoft SQL Server again.\n" * 3
    parsed = parse_jd(
        f"Senior Developer - Remote - Indeed.com\n\n{body}\nRequirements\n    Python\n"
    )
    assert parsed.company == "Unknown Company"


# --- Round six --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "heading",
    ["We’re looking for:", "We're looking for:", "We are looking for:"[:0] or "We're looking for"],
)
def test_a_bare_were_looking_for_heading_opens_the_requirements(heading: str) -> None:
    parsed = parse_jd(f"# Dev\n\nAbout us\nWe build things.\n\n{heading}\n    Python\n    SQL\n")
    assert parsed.required == ["Python", "SQL"]


def test_a_sentence_that_starts_with_were_looking_for_is_not_a_heading() -> None:
    parsed = parse_jd(
        "# Dev\n\nAbout You\n    Python\n\nWe're looking for a person who loves Docker\n"
    )
    assert "Docker" not in parsed.required


def test_what_youll_be_doing_ends_the_requirements_list() -> None:
    parsed = parse_jd(
        "# Dev\n\nWhat We're Looking For:\n    Python\n\nWhat You'll Be Doing:\n"
        "    Build the test suite in Docker.\n\nWho You Are:\n    SQL\n"
    )
    assert parsed.required == ["Python", "SQL"]


def test_a_required_spoken_language_is_listed_not_scored() -> None:
    line = "Professional working proficiency in both English and Mandarin Chinese is a must."
    parsed = parse_jd(f"# Dev\n\nRequirements\n    Python\n    {line}\n")
    assert parsed.required == ["Python"]
    assert [s.line for s in parsed.soft_requirements if s.kind == "language"] == [line]


def test_legal_eligibility_to_work_is_eligibility() -> None:
    parsed = parse_jd(
        "# Dev\n\nRequirements\n    Python\n    Legal eligibility to work in Canada.\n"
    )
    assert [s.kind for s in parsed.soft_requirements] == ["eligibility"]


def test_a_security_rating_or_background_check_is_eligibility() -> None:
    parsed = parse_jd(
        '# Dev\n\nRequirements\n    Python\n    Must obtain and maintain a "Clear" security rating.\n'
    )
    assert [s.kind for s in parsed.soft_requirements] == ["eligibility"]


def test_structure_contract_and_contract_developer_make_a_contract_posting() -> None:
    from jobomatic.fit.salary import is_contract_posting

    assert is_contract_posting("Structure: Contract, 1 opening")
    assert is_contract_posting("We have an opening for a contract Full Stack Developer.")
    assert is_contract_posting("They are on contract until June.")
    assert not is_contract_posting(
        "Full-time permanent position with a signed employment contract."
    )


def test_a_location_preference_line_is_soft_not_a_skill() -> None:
    parsed = parse_jd(
        "# Dev\n\nPreferred Qualifications\n- Springfield-based candidates are preferred.\n- Redis\n"
    )
    assert parsed.nice_to_have == ["Redis"]


def test_a_title_dash_company_first_line_gives_the_company() -> None:
    for first, company in [
        (
            "Technical Lead, Software Development - Acme Industries Limited",
            "Acme Industries Limited",
        ),
        ("ENTERPRISE REPORT DEVELOPER - Prairie Hydro", "Prairie Hydro"),
    ]:
        parsed = parse_jd(f"workopolis.com\n{first}\n6 minutes\n\nRequirements\n    Python\n")
        assert parsed.company == company


def test_a_dash_and_a_place_is_not_a_company() -> None:
    parsed = parse_jd("Senior Developer - Springfield\n\nRequirements\n    Python\n")
    assert parsed.company != "Springfield"


def test_a_company_with_a_corporate_suffix_on_the_second_line() -> None:
    parsed = parse_jd(
        "Senior Software Engineer\nExample Canada Inc.\nToronto ON - Work Remotely\nfull-time\n\n"
        "Requirements\n    Python\n"
    )
    assert parsed.company == "Example Canada Inc."


def test_a_university_named_often_is_the_company_and_is_not_an_education_line() -> None:
    body = (
        "Experience with University of Waterloo web services preferred.\n"
        "The University of Waterloo is committed to equity.\n"
    )
    parsed = parse_jd(f"IT Administrator - Indeed.com\n\nRequirements\n    Python\n    {body}")
    assert parsed.company == "University of Waterloo"
    assert not any(s.kind == "education" for s in parsed.soft_requirements)


def test_hard_wrapped_bullets_are_joined_and_or_lines_are_dropped() -> None:
    parsed = parse_jd(
        "# Dev\n\nQualifications:\n\n    Demonstrated experience designing, developing, and maintaining\n\n"
        "reporting solutions in Python and SQL required.\n\nOR\n\n    Experience with Docker required.\n"
    )
    assert "or" not in [r.lower() for r in parsed.required]
    assert not any(line.startswith("reporting") for line in parsed.unscored_required)
    assert {"Python", "SQL", "Docker"} <= set(parsed.required)


def test_a_short_lowercase_list_is_not_joined() -> None:
    from jobomatic.fit.parser import _join_wrapped

    lines = ["Requirements", "", "python", "sql", "docker"]
    assert _join_wrapped(lines) == lines


def test_an_is_preferred_or_highly_desirable_line_is_nice_to_have() -> None:
    parsed = parse_jd(
        "# Dev\n\nExperience:\n    Python experience required.\n"
        "    Experience supporting Docker and Redis is preferred.\n"
        "    Kubernetes experience is highly desirable.\n"
    )
    assert "Python" in parsed.required
    assert {"Docker", "Redis", "Kubernetes"} <= set(parsed.nice_to_have)
    assert not {"Docker", "Redis", "Kubernetes"} & set(parsed.required)


def test_a_strongly_preferred_line_stays_required() -> None:
    parsed = parse_jd("# Dev\n\nRequirements\n    Docker experience is strongly preferred.\n")
    assert parsed.required == ["Docker experience is strongly preferred"]
    assert parsed.nice_to_have == []


def test_years_written_as_a_word() -> None:
    parsed = parse_jd(
        "# Dev\n\nRequirements\n    Three years of directly related support experience required.\n"
    )
    assert [s.note for s in parsed.soft_requirements if s.kind == "years"] == ["minimum 3 years"]


def test_a_bracket_of_examples_after_a_term_is_dropped() -> None:
    parsed = parse_jd(
        "# Dev\n\nBonus Skills:\n- Experience with Agile methodologies (Scrum/Kanban).\n"
    )
    assert parsed.nice_to_have == ["Agile"]


def test_a_bracket_with_other_words_keeps_its_detail() -> None:
    parsed = parse_jd(
        "# Dev\n\nRequirements\n- Strong Azure fundamentals (App Service, Functions, Cosmos DB)\n"
    )
    assert any("app service" in item.lower() for item in parsed.required_for_rating)


def test_the_length_of_a_degree_is_not_years_of_experience() -> None:
    parsed = parse_jd(
        "# Dev\n\nQualifications:\n"
        "    A four year degree in Computer Science plus a minimum of three years related experience.\n"
    )
    assert [s.note for s in parsed.soft_requirements if s.kind == "years"] == ["minimum 3 years"]


def test_travel_and_a_criminal_record_search_are_eligibility() -> None:
    for line in [
        "Be able to travel to the US.",
        "Employment is contingent upon a satisfactory response from a Criminal Record Search.",
        "Willing to travel up to 25% of the time.",
    ]:
        parsed = parse_jd(f"# Dev\n\n## Requirements\n- Python\n\n{line}\n")
        assert [s.line for s in parsed.soft_requirements if s.kind == "eligibility"] == [line]


def test_a_bare_location_heading_ends_the_list() -> None:
    parsed = parse_jd(
        "# Dev\n\nNice to have:\n    Docker\n\nLocation\n\nPacific Time zone preferred. Remote-first.\n"
    )
    assert parsed.nice_to_have == ["Docker"]


def test_leading_or_mentoring_is_one_choice_row() -> None:
    parsed = parse_jd("# Dev\n\nBonus points:\n- Experience leading or mentoring engineers\n")
    assert len(parsed.nice_to_have) == 1
    assert " / " in parsed.nice_to_have[0]


def test_passion_and_self_directed_lines_are_soft_skills() -> None:
    parsed = parse_jd(
        "# Dev\n\nMust have:\n- Python\n- Passion to use software to impact the physical world\n"
        "- Self-directed work style: you take a problem from ambiguity through delivery\n"
    )
    assert parsed.required == ["Python"]
    assert [s.kind for s in parsed.soft_requirements] == ["soft skill", "soft skill"]


# --- The dot of ".NET" and WebAPI ----------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [".NET Framework (VB/C#)", ".NET Web Services (WebAPI)", ".NET Core", ".NET"],
)
def test_the_leading_dot_of_dot_net_is_kept(line: str) -> None:
    parsed = parse_jd(f"# Dev\n\n## Requirements\n- {line}\n")
    assert parsed.required[0].startswith(".NET")


def test_a_stray_leading_full_stop_is_still_dropped() -> None:
    parsed = parse_jd("# Dev\n\n## Requirements\n- ... Python\n- . SQL\n")
    assert parsed.required == ["Python", "SQL"]


@pytest.mark.parametrize(
    "heads,title,company",
    [
        (
            "# Example Healthcare\n# Senior Software Developer",
            "Senior Software Developer",
            "Example Healthcare",
        ),
        (
            "# Senior Software Developer\n# Example Healthcare",
            "Senior Software Developer",
            "Example Healthcare",
        ),
    ],
)
def test_two_top_level_headings_are_the_company_and_the_title(
    heads: str, title: str, company: str
) -> None:
    parsed = parse_jd(f"\n{heads}\n\n## Requirements\n* Python\n")
    assert (parsed.title, parsed.company) == (title, company)


def test_two_headings_that_both_name_roles_are_left_alone() -> None:
    parsed = parse_jd("# Senior Developer\n# Backend Engineer\n\n## Requirements\n* Python\n")
    assert parsed.title == "Senior Developer"
    assert parsed.company == "Unknown Company"


def test_headings_separated_by_a_blank_line_are_not_a_pair() -> None:
    parsed = parse_jd(
        "# Example Healthcare\n\n# Senior Software Developer\n\n## Requirements\n* Python\n"
    )
    assert parsed.company != "Example Healthcare"


def test_full_stack_application_development_is_asked_for_as_full_stack() -> None:
    parsed = parse_jd(
        "# Dev\n\nMust have:\n"
        "- Full-stack application development: you can build and ship a complete product across "
        "web, backend, and mobile, not just isolated features\n"
    )
    assert parsed.required == ["Full-stack"]
