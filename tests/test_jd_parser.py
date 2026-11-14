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
    assert "troubleshooting production issues" in joined_required
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
