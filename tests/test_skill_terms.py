"""Tests for jobomatic.fit.terms — skill-name extraction from sentence-style JD bullets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobomatic.fit.terms import (
    conjoined_terms,
    extract_skill_terms,
    find_possible_typos,
    find_terms_to_confirm,
    find_unknown_names,
    is_kind_term,
    load_alternative_groups,
    load_caps_only,
    load_category_terms,
    load_kind_nouns,
    load_list_only,
    load_or_other,
    load_phrase_expansions,
    load_umbrella_terms,
    load_umbrellas,
    load_vocabulary,
    phrase_expansion,
    reduce_to_terms,
    umbrella_parts,
)


@pytest.mark.parametrize(
    "sentence,expected",
    [
        (
            "Experience building Azure applications using event-driven or microservice architectures",
            ["Azure", "event-driven", "microservice"],
        ),
        ("professional software development with strong C# and .NET experience", ["C#", ".NET"]),
        (
            "Strong knowledge of OOP, design patterns, SOLID principles, secure development, and testing",
            ["OOP", "design patterns", "SOLID", "secure development", "testing"],
        ),
        (
            "Hands-on with ASP.NET Core, Azure DevOps pipelines and CI/CD",
            ["ASP.NET Core", "Azure DevOps", "CI/CD"],
        ),
    ],
)
def test_extracts_terms_in_the_postings_own_spelling(sentence: str, expected: list[str]) -> None:
    assert extract_skill_terms(sentence) == expected


def test_longest_term_wins_over_its_prefix() -> None:
    # "GitHub Copilot" must not also yield a bare "copilot"; "ASP.NET Core" not ".NET".
    assert extract_skill_terms("Daily use of GitHub Copilot with ASP.NET Core") == [
        "GitHub Copilot",
        "ASP.NET Core",
    ]


def test_or_comparable_collapses_preceding_list_into_one_alternatives_entry() -> None:
    result = extract_skill_terms(
        "Advanced experience with GitHub Copilot, Claude Code, Windsurf, or comparable platforms"
    )
    assert result == ["GitHub Copilot / Claude Code / Windsurf"]


def test_alternatives_only_cover_the_clause_before_or_comparable() -> None:
    result = extract_skill_terms(
        "Strong Azure skills and experience with GitHub Copilot or comparable tools"
    )
    assert "Azure" in result
    assert "GitHub Copilot" in result  # a single term before "or comparable" stays itself


def test_plain_or_is_not_treated_as_alternatives() -> None:
    # Only "or comparable/similar/equivalent/other" marks alternatives; a bare
    # "or" stays conservative — each term is its own required skill.
    assert extract_skill_terms("Experience with Kubernetes or Docker in production systems") == [
        "Kubernetes",
        "Docker",
    ]


def test_examples_after_such_as_are_one_alternatives_entry() -> None:
    # One requirement, met by any one tool; the broad "AI" label is dropped (umbrella term).
    result = extract_skill_terms(
        "Experience using AI-assisted development tools such as GitHub Copilot, Claude Code, or Cursor"
    )
    assert result == ["GitHub Copilot / Claude Code / Cursor"]


@pytest.mark.parametrize(
    "sentence",
    [
        "Familiar with build tooling, e.g. Docker, Kubernetes and Terraform",
        "Experience with tooling including Docker, Kubernetes, and Terraform",
        "Experience with tooling like Docker, Kubernetes or Terraform",
        "Experience with tooling for example Docker, Kubernetes, Terraform",
    ],
)
def test_every_example_marker_collapses_the_list_whether_it_ends_in_and_or_or(
    sentence: str,
) -> None:
    assert extract_skill_terms(sentence) == ["Docker / Kubernetes / Terraform"]


def test_a_single_example_stays_itself() -> None:
    assert extract_skill_terms("Experience with cloud platforms such as Azure") == ["Azure"]


def test_examples_stop_at_a_new_requirement_in_the_same_sentence() -> None:
    result = extract_skill_terms(
        "Tools such as GitHub Copilot, Claude Code, and experience with Docker"
    )
    assert sorted(result) == ["Docker", "GitHub Copilot / Claude Code"]


def test_examples_stop_at_a_semicolon() -> None:
    result = extract_skill_terms("Tools such as Docker, Kubernetes; Azure DevOps pipelines")
    assert sorted(result) == ["Azure DevOps", "Docker / Kubernetes"]


def test_terms_before_the_marker_are_not_swept_into_the_examples() -> None:
    result = extract_skill_terms("Strong Python and cloud tools such as Docker or Kubernetes")
    assert sorted(result) == ["Docker / Kubernetes", "Python"]


def test_an_umbrella_label_is_dropped_before_or_comparable_too() -> None:
    result = extract_skill_terms(
        "AI-assisted tools such as GitHub Copilot, Claude Code, or comparable platforms"
    )
    assert result == ["GitHub Copilot / Claude Code"]


def test_sentence_with_no_known_skill_returns_empty() -> None:
    assert extract_skill_terms("Computer science degree or equivalent practical experience") == []


def test_ordinary_english_words_do_not_false_match() -> None:
    # "go", "rest", "c" are deliberately not in the vocabulary.
    assert extract_skill_terms("We value go-getters who go above and beyond and rest easy") == []


def test_duplicates_are_removed_case_insensitively() -> None:
    assert extract_skill_terms("Azure experience, azure certifications and AZURE skills") == [
        "Azure"
    ]


def test_plural_forms_match() -> None:
    assert extract_skill_terms("Design and ship microservices backed by containers and agents") == [
        "microservices",
        "containers",
        "agents",
    ]


def test_shipped_vocabulary_loads() -> None:
    vocab = load_vocabulary()
    assert "azure" in vocab and "c#" in vocab and "kubernetes" in vocab


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"terms": []}, "non-empty"),
        ({"terms": "azure"}, "non-empty"),
        ({"terms": [1, 2]}, "non-empty"),
        ({"terms": ["azure", "x"]}, "at least 2"),
        ({}, "non-empty"),
    ],
)
def test_malformed_vocabulary_fails_loudly(tmp_path: Path, payload: dict, match: str) -> None:
    path = tmp_path / "vocab.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_vocabulary(path)


# ── alternative groups (ADR 0021): same-kind tools joined by "/" or "or" are one requirement ──


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        (
            "Proficiency with .NET Core, Entity Framework/ Dapper, and Microservices",
            [".NET Core", "Entity Framework / Dapper", "Microservices"],
        ),
        ("Experience with AWS or Azure cloud platforms", ["AWS / Azure"]),
        ("Experience with C#, Java, or Python in production", ["C# / Java / Python"]),
        ("Experience shipping apps with React/Angular frontends", ["React / Angular"]),
        ("Experience with Kafka, RabbitMQ or SQS in production", ["Kafka / RabbitMQ / SQS"]),
    ],
)
def test_same_group_terms_joined_by_slash_or_or_are_one_alternatives_entry(
    sentence: str, expected: list[str]
) -> None:
    assert extract_skill_terms(sentence) == expected


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        # "and" asks for both
        (
            "Experience with React and Angular in production apps",
            ["React", "Angular"],
        ),
        ("Strong C# and Java and Python skills in production systems", ["C#", "Java", "Python"]),
        # a plain comma list says nothing about choice
        ("Experience with Azure, AWS, GCP in production", ["Azure", "AWS", "GCP"]),
        # different groups are different requirements
        ("Experience with C#/.NET Core web services in production", ["C#", ".NET Core"]),
        # HTML and CSS are asked for together; JavaScript/TypeScript is one skill (owner's call)
        (
            "Build tooling around JavaScript/TypeScript and HTML/CSS for production sites",
            ["JavaScript / TypeScript", "HTML", "CSS"],
        ),
    ],
)
def test_and_commas_and_cross_group_terms_stay_separate_requirements(
    sentence: str, expected: list[str]
) -> None:
    assert extract_skill_terms(sentence) == expected


def test_a_group_run_does_not_swallow_a_term_after_an_and() -> None:
    result = extract_skill_terms("Experience with Azure or AWS and Kubernetes in production")
    assert sorted(result) == ["Azure / AWS", "Kubernetes"]


def test_the_shipped_groups_are_valid_and_only_name_known_terms() -> None:
    groups = load_alternative_groups()
    assert groups["entity framework"] == groups["dapper"]
    assert groups["azure"] == groups["aws"]
    assert groups["azure"] != groups["c#"]
    assert groups["javascript"] == groups["typescript"]
    assert "css" not in groups and "html" not in groups


@pytest.mark.parametrize(
    ("groups", "match"),
    [
        ({"orm": ["entity framework", "not-a-term"]}, "not in 'terms'"),
        ({"a": ["azure", "aws"], "b": ["aws", "gcp"]}, "two alternative groups"),
        ({"orm": ["dapper"]}, "at least two terms"),
        ("nope", "must be an object"),
    ],
)
def test_malformed_groups_fail_loudly(tmp_path: Path, groups: object, match: str) -> None:
    path = tmp_path / "vocab.json"
    path.write_text(
        json.dumps(
            {
                "terms": ["entity framework", "dapper", "azure", "aws", "gcp"],
                "alternative_groups": groups,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=match):
        load_alternative_groups(path)


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        (
            "Experience building web apps with ASP.NET Core MVC, ASP.NET Core Blazor or "
            "ASP.NET Web Forms",
            ["ASP.NET Core MVC / ASP.NET Core Blazor / ASP.NET Web Forms"],
        ),
        ("Experience with ASP.NET MVC or Blazor in production systems", ["ASP.NET MVC / Blazor"]),
        # "and" asks for both
        (
            "Experience with ASP.NET Core MVC and ASP.NET Core Blazor in production",
            ["ASP.NET Core MVC", "ASP.NET Core Blazor"],
        ),
        # Web Forms is its own skill, not the generic "ASP.NET"
        (
            "Hands-on experience with ASP.NET Web Forms in legacy applications",
            ["ASP.NET Web Forms"],
        ),
    ],
)
def test_aspnet_ui_frameworks_keep_their_own_names_and_join_only_as_a_choice(
    sentence: str, expected: list[str]
) -> None:
    assert extract_skill_terms(sentence) == expected


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        # html5 or htmls: a plural of a singular-only term is searched as the singular, which
        # the fit engine matches in either form
        ("Experience with Node.js, HTMLS, CSS, and Python", ["Node.js", "HTML", "CSS", "Python"]),
        ("Experience building apps with HTMLs and Dockers in production", ["HTML", "Docker"]),
        # a term that is itself in the vocabulary as a plural keeps its spelling
        ("Experience with LLMs and microservices in production systems", ["LLMs", "microservices"]),
    ],
)
def test_a_plural_of_a_singular_term_is_returned_as_the_singular(
    sentence: str, expected: list[str]
) -> None:
    assert extract_skill_terms(sentence) == expected


def test_a_plural_inside_an_alternatives_list_is_returned_as_the_singular() -> None:
    result = extract_skill_terms("Tools such as Dockers, Kubernetes in production systems")
    assert result == ["Docker / Kubernetes"]


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        # the adjective is not the design principles
        ("Solid understanding of CI/CD practices and pipelines", ["CI/CD"]),
        ("Solid backend experience in C# and Python in production", ["C#", "Python"]),
        # in capitals it is the skill
        ("Knowledge of SOLID principles in production systems", ["SOLID"]),
        ("Solid foundation in OOP and SOLID design for production services", ["OOP", "SOLID"]),
    ],
)
def test_solid_counts_as_a_skill_only_when_written_in_capitals(
    sentence: str, expected: list[str]
) -> None:
    assert extract_skill_terms(sentence) == expected


def test_the_shipped_caps_only_terms_are_known_terms() -> None:
    assert load_caps_only() == {"solid"}


@pytest.mark.parametrize(
    ("caps_only", "match"),
    [(["not-a-term"], "not in 'terms'"), ("solid", "must be a list")],
)
def test_malformed_caps_only_fails_loudly(tmp_path: Path, caps_only: object, match: str) -> None:
    path = tmp_path / "vocab.json"
    path.write_text(json.dumps({"terms": ["solid", "python"], "caps_only": caps_only}))
    with pytest.raises(ValueError, match=match):
        load_caps_only(path)


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Solid CI/CD practices and pipelines", ["solid"]),
        ("Solid understanding of CI/CD practices and pipelines", []),  # the adjective
        ("solid principles and Solid design in production systems", ["solid"]),  # once
        ("Knowledge of SOLID principles in production systems", []),  # capitals: the skill
        ("Experience with Python in production systems", []),
    ],
)
def test_ambiguous_words_not_in_capitals_are_listed_to_confirm(
    sentence: str, expected: list[str]
) -> None:
    assert find_terms_to_confirm(sentence) == expected


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        # category + examples = one requirement, met by the category or any example
        ("Experience with NoSQL databases such as MongoDB", ["NoSQL / MongoDB"]),
        (
            "Experience with message queues such as SQS, RabbitMQ, or Kafka",
            ["message queues / SQS / RabbitMQ / Kafka"],
        ),
        (
            "Experience using AI-assisted development tools such as GitHub Copilot, Claude Code, "
            "or Cursor",
            ["GitHub Copilot / Claude Code / Cursor"],
        ),
        # a product is not a category: Python alone must not meet "Python libraries such as ..."
        (
            "Experience with Python libraries such as Pandas and NumPy in production",
            ["Pandas / NumPy", "Python"],
        ),
        # a label with no vocabulary term, or far from the marker, does not join
        ("Experience with cloud platforms such as Azure", ["Azure"]),
        (
            "Experience with testing, and other practices in teams, tools such as Jest or Jasmine",
            ["Jest / Jasmine", "testing"],
        ),
    ],
)
def test_a_category_term_joins_its_examples_but_a_product_does_not(
    sentence: str, expected: list[str]
) -> None:
    assert extract_skill_terms(sentence) == expected


def test_the_shipped_category_terms_are_known_terms_and_name_kinds_not_products() -> None:
    categories = load_category_terms()
    assert {"nosql", "message queues"} <= categories
    assert not categories & {"ai", "generative ai", "machine learning", "deep learning"}
    assert not categories & {"python", "azure", "docker", "mongodb", "react"}


@pytest.mark.parametrize(
    ("category_terms", "match"),
    [(["not-a-term"], "not in 'terms'"), ("nosql", "must be a list")],
)
def test_malformed_category_terms_fail_loudly(
    tmp_path: Path, category_terms: object, match: str
) -> None:
    path = tmp_path / "vocab.json"
    path.write_text(json.dumps({"terms": ["nosql", "python"], "category_terms": category_terms}))
    with pytest.raises(ValueError, match=match):
        load_category_terms(path)


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        # the umbrella is dropped when examples follow: any AI project would otherwise meet it
        (
            "Experience using AI-assisted development tools such as GitHub Copilot, Claude Code, "
            "or Cursor",
            ["GitHub Copilot / Claude Code / Cursor"],
        ),
        ("AI-assisted tools such as GitHub Copilot in production", ["GitHub Copilot"]),
        (
            "Experience with machine learning libraries such as Pandas and NumPy",
            ["Pandas / NumPy"],
        ),
        # an umbrella that is itself the requirement is scored as usual
        (
            "Experience with AI and machine learning in production systems",
            ["AI", "machine learning"],
        ),
    ],
)
def test_an_umbrella_term_is_dropped_when_examples_follow_and_kept_when_alone(
    sentence: str, expected: list[str]
) -> None:
    assert extract_skill_terms(sentence) == expected


def test_the_shipped_umbrella_terms() -> None:
    assert load_umbrella_terms() == {"ai", "generative ai", "machine learning", "deep learning"}


@pytest.mark.parametrize(
    ("umbrella", "category", "match"),
    [
        (["not-a-term"], [], "not in 'terms'"),
        (["ai"], ["ai"], "both an umbrella term and a category term"),
        ("ai", [], "must be a list"),
    ],
)
def test_malformed_umbrella_terms_fail_loudly(
    tmp_path: Path, umbrella: object, category: list[str], match: str
) -> None:
    path = tmp_path / "vocab.json"
    path.write_text(
        json.dumps(
            {"terms": ["ai", "python"], "umbrella_terms": umbrella, "category_terms": category}
        )
    )
    with pytest.raises(ValueError, match=match):
        load_umbrella_terms(path)


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        (
            "Experience with Typscript and Javscript",
            [("Typscript", "typescript"), ("Javscript", "javascript")],
        ),
        ("Deploying to kubernates clusters", [("kubernates", "kubernetes")]),
        ("a transposed Postgresql is fine but Postgresqul is not", [("Postgresqul", "postgresql")]),
    ],
)
def test_a_word_one_letter_from_a_long_skill_name_is_a_possible_typo(
    sentence: str, expected: list[tuple[str, str]]
) -> None:
    assert find_possible_typos(sentence) == expected


@pytest.mark.parametrize(
    "sentence",
    [
        "Agile sprint planning with signals, strings and informs",  # short words near SignalR, Spring...
        "Experience with TypeScript, JavaScript and Kubernetes",  # spelled right
        "Docker containers and a single container image",  # plural and singular of a known term
        "Python3 and SQLite3 scripts",  # version numbers
        "Strong written and verbal communication skills",  # ordinary English
    ],
)
def test_correct_spelling_and_ordinary_words_are_never_flagged(sentence: str) -> None:
    assert find_possible_typos(sentence) == []


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("Strong Postgresql skills", ["Postgresql"]),
        ("Good SQL knowledge", ["SQL"]),
        ("Solid React experience", ["React"]),
        ("Knowledge of Git", ["Git"]),
        ("Experience with Docker", ["Docker"]),
    ],
)
def test_a_short_requirement_that_is_a_term_plus_filler_reduces_to_the_term(phrase, expected):
    assert reduce_to_terms(phrase) == expected


@pytest.mark.parametrize(
    "phrase",
    [
        "Python",  # nothing to strip
        "Azure fundamentals",  # "fundamentals" says something: keep the phrase
        "Excellent communication",  # no known term
        "Strong Postgresql tuning habits",  # extra words are never dropped
        "Unit testing with Jasmine",  # two terms: one requirement, kept whole
    ],
)
def test_a_phrase_with_nothing_to_strip_or_a_meaningful_extra_word_is_left_alone(phrase):
    assert reduce_to_terms(phrase) is None


# ── "or other <kind>": any tool of the group meets the requirement ──


@pytest.mark.parametrize(
    "sentence,expected",
    [
        (
            "Experience in building cloud services using AWS, or other cloud platforms",
            ["AWS / Azure / GCP / Google Cloud"],
        ),
        (
            "Experience using Azure or any other cloud providers",
            ["Azure / AWS / GCP / Google Cloud"],
        ),
        (
            "Experience with Entity Framework or other ORMs",
            ["Entity Framework / Entity Framework Core / EF Core / Dapper / Nhibernate"],
        ),
    ],
)
def test_or_other_kind_after_a_tool_means_any_tool_of_that_group(sentence, expected):
    assert extract_skill_terms(sentence) == expected


def test_the_kind_named_in_an_or_other_phrase_is_not_a_skill_of_its_own():
    terms = extract_skill_terms("Experience with Jenkins or other CI/CD tools")
    assert len(terms) == 1 and terms[0].startswith("Jenkins / ")
    assert "CI/CD" not in terms


@pytest.mark.parametrize(
    "sentence",
    [
        "Experience with Kafka or other cloud platforms",  # Kafka is not a cloud platform
        "Experience with AWS or other languages",  # "languages" is too broad to name a group
        "Experience with AWS",  # nothing said about other tools
    ],
)
def test_or_other_does_not_widen_a_requirement_it_does_not_name(sentence):
    assert "Azure" not in " ".join(extract_skill_terms(sentence))


def test_or_other_with_an_unknown_group_fails_loudly(tmp_path: Path):
    path = tmp_path / "vocab.json"
    path.write_text(
        json.dumps(
            {
                "terms": ["aws", "azure"],
                "alternative_groups": {"cloud": ["aws", "azure"]},
                "or_other": {"database": ["databases"]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not an alternative group"):
        load_or_other(path)


# ── list-only terms: "Go" is the language only inside a list of terms ──


@pytest.mark.parametrize(
    "sentence,expected",
    [
        (
            "Proficiency in web technologies, such as Java, Go, GraphQL, etc.",
            ["Java / Go / GraphQL"],
        ),
        ("Experience with Go or Rust", ["Go / Rust"]),
        ("Experience with Java, Go", ["Java", "Go"]),
    ],
)
def test_go_counts_when_it_sits_in_a_list_of_terms(sentence, expected):
    assert extract_skill_terms(sentence) == expected


@pytest.mark.parametrize(
    "sentence",
    [
        "Experience with Go",  # alone: could be the English word
        "Ready to go to market with Java",
        "Strong in C# and go",  # lower case is the verb
    ],
)
def test_go_alone_or_in_lower_case_is_not_the_language(sentence):
    assert "Go" not in extract_skill_terms(sentence)
    assert "go" not in " ".join(extract_skill_terms(sentence)).lower().split(" / ")


def test_a_list_only_term_unknown_to_the_vocabulary_fails_loudly(tmp_path: Path):
    path = tmp_path / "vocab.json"
    path.write_text(json.dumps({"terms": ["azure"], "list_only": ["go"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="not in 'terms'"):
        load_list_only(path)


# ── "Solid understanding of…" is an adjective, not the SOLID principles ──


@pytest.mark.parametrize(
    "sentence",
    [
        "Has solid understanding of the product development lifecycle",
        "Solid grasp of unit testing",
        "Solid experience building APIs",
    ],
)
def test_solid_before_understanding_or_experience_is_ordinary_english(sentence):
    assert find_terms_to_confirm(sentence) == []


def test_solid_elsewhere_in_lower_case_is_still_asked_about():
    assert find_terms_to_confirm("Knowledge of solid principles") == ["solid"]


@pytest.mark.parametrize(
    "sentence",
    [
        "Has solid understanding of the product development lifecycle",
        "Knowledge of the software development life cycle",
        "Understanding of SDLC",
    ],
)
def test_the_development_lifecycle_in_any_wording_is_a_known_skill(sentence):
    assert len(extract_skill_terms(sentence)) == 1


# ── a bracket after a category term lists examples of it ──


def test_a_bracket_of_examples_after_a_category_term_is_one_requirement():
    terms = extract_skill_terms(
        "Familiarity with the broader Microsoft Power Platform ecosystem "
        "(Power Apps, Power BI, SharePoint, Teams)"
    )
    assert terms == ["Power Platform / Power Apps / Power BI / SharePoint"]


def test_a_bracket_after_an_ordinary_skill_is_left_alone():
    terms = extract_skill_terms("Strong Azure fundamentals (App Service, Functions, Cosmos DB)")
    assert terms == ["Azure", "App Service", "Cosmos DB"]


# ── "OAuth authentication": the kind word after a specific term adds nothing ──


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        (
            "Working knowledge of REST APIs, JSON, and OAuth authentication",
            ["REST API", "JSON", "OAuth"],
        ),
        ("Experience with JWT authorization", ["JWT"]),
        ("Experience with authentication", ["authentication"]),
    ],
)
def test_a_kind_word_directly_after_a_specific_term_is_dropped(sentence, expected):
    assert extract_skill_terms(sentence) == expected


def test_a_kind_noun_unknown_to_the_vocabulary_fails_loudly(tmp_path: Path):
    path = tmp_path / "vocab.json"
    path.write_text(
        json.dumps({"terms": ["azure"], "kind_nouns": ["authentication"]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="not in 'terms'"):
        load_kind_nouns(path)


def test_workflow_automation_wordings_are_one_either_or_requirement():
    terms = extract_skill_terms(
        "building and maintaining automated workflows or business process automations"
    )
    assert terms == ["automated workflow / business process automation"]


# ── names in a list of examples that the skill list does not know ──


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("tools such as Frobnicator, Zorp, or Acme Suite", ["Frobnicator", "Zorp", "Acme Suite"]),
        ("Knowledge of ToolOne, ToolTwo, Java, or similar technologies", ["ToolTwo"]),
        ("Knowledge of tools like Docker and Kubernetes", []),
        ("Experience with Azure", []),
        ("platforms such as MuleSoft or similar middleware", []),  # MuleSoft is a known term now
    ],
)
def test_unrecognised_capitalised_names_in_an_example_list_are_found(sentence, expected):
    assert find_unknown_names(sentence) == expected


@pytest.mark.parametrize(
    "sentence",
    [
        "Knowledge of .NET MAUI",
        "Oracle APEX experience",
        "Experience with Oracle Pro*C",
        "Strong release management and production support",
    ],
)
def test_the_lead_posting_products_are_known_terms(sentence):
    assert extract_skill_terms(sentence)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("monitoring", True), ("NoSQL", True), ("AI", True), ("React", False), ("Node.js", False)],
)
def test_a_kind_term_names_a_kind_of_tool_not_a_product(text, expected):
    assert is_kind_term(text) is expected


# ── Agile/Scrum and JavaScript/TypeScript are each one skill when written with "/" or "or" ──


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Familiarity with Agile/Scrum development methodologies", ["Agile / Scrum"]),
        ("Experience with Agile or Scrum", ["Agile / Scrum"]),
        ("Strong proficiency in JavaScript and/or TypeScript.", ["JavaScript / TypeScript"]),
        (
            "Experience with React, JavaScript/TypeScript, and SQL",
            ["React", "JavaScript / TypeScript", "SQL"],
        ),
        ("Agile and Scrum", ["Agile", "Scrum"]),  # "and" keeps them separate
        ("JavaScript and TypeScript", ["JavaScript", "TypeScript"]),
    ],
)
def test_agile_scrum_and_javascript_typescript_join_only_with_slash_or_or(sentence, expected):
    assert extract_skill_terms(sentence) == expected


def test_a_term_plus_development_methodology_or_practices_reduces_to_the_term():
    assert reduce_to_terms("C# development") == ["C#"]
    assert reduce_to_terms("Agile practices") == ["Agile"]


# ── umbrellas scored by their parts (ADR 0022) ──


def test_the_owners_ai_parts_are_loaded_and_generative_ai_shares_them():
    parts = umbrella_parts("AI")
    assert parts is not None
    for expected in (
        "agentic",
        "rag",
        "embeddings",
        "claude code",
        "ollama",
        "llm",
        "mcp",
        "vector database",
        "prompt engineering",
        "langchain",
    ):
        assert expected in parts
    assert umbrella_parts("generative ai") == parts
    assert umbrella_parts("react") is None


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"umbrellas": {"cloud": ["azure", "aws"]}}, "not an umbrella term"),
        ({"umbrellas": {"ai": ["nope"]}}, "not in 'terms'"),
        ({"umbrellas": {"ai": []}}, "non-empty list"),
        ({"umbrellas": {"ai": ["ai"]}}, "itself an umbrella"),
        ({"umbrellas": {"ai": "ml"}}, "no parts"),
    ],
)
def test_a_bad_umbrella_entry_fails_loudly(tmp_path: Path, payload: dict, match: str):
    path = tmp_path / "vocab.json"
    base = {
        "terms": ["ai", "ml", "azure", "aws", "claude code"],
        "umbrella_terms": ["ai", "ml"],
        **payload,
    }
    path.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_umbrellas(path)


# ── a phrase that stands for two skills ──


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Modern AI-assisted automation techniques", ["AI", "Workflow Automation"]),
        ("Experience with AI-powered automation", ["AI", "Workflow Automation"]),
        ("AI assisted automation", ["AI", "Workflow Automation"]),
        ("Experience with automation", []),
    ],
)
def test_ai_assisted_automation_stands_for_ai_and_workflow_automation(sentence, expected):
    assert phrase_expansion(sentence) == expected


def test_a_line_with_an_expansion_phrase_and_another_skill_keeps_both():
    terms = extract_skill_terms("AI-assisted automation of Azure DevOps pipelines")
    assert {"AI", "Azure DevOps", "Workflow Automation"} <= set(terms)


def test_the_microsoft_ai_tools_are_ai_parts():
    parts = umbrella_parts("ai")
    assert parts is not None and "copilot studio" in parts and "ai builder" in parts


def test_a_phrase_expansion_with_an_unknown_term_fails_loudly(tmp_path: Path):
    path = tmp_path / "vocab.json"
    path.write_text(
        json.dumps({"terms": ["ai"], "phrase_expansions": {"x automation": ["ai", "nope"]}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not in 'terms'"):
        load_phrase_expansions(path)


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Experience with Azure and REST APIs", ["Azure", "REST API"]),
        ("Docker, Kubernetes and Helm", ["Docker", "Kubernetes", "Helm"]),
        ("Familiarity with Git, CI/CD and Docker", ["Git", "CI/CD", "Docker"]),
    ],
)
def test_conjoined_terms_returns_every_skill_of_a_plain_list(sentence, expected):
    assert conjoined_terms(sentence) == expected


@pytest.mark.parametrize(
    "sentence",
    [
        "Azure",  # one term is not a list
        "Azure fundamentals and REST APIs",  # "fundamentals" is a meaningful word
        "Docker or Kubernetes",  # a choice
        "Azure and REST APIs, e.g. OpenAPI",  # examples
        "Python/Java",  # alternatives
    ],
)
def test_conjoined_terms_refuses_anything_it_would_have_to_reinterpret(sentence):
    assert conjoined_terms(sentence) is None


@pytest.mark.parametrize(
    "sentence",
    [
        "Accessibility (WCAG)",  # a parenthesis explains one requirement
        "Monitoring and observability with Azure Monitor",  # "with" is not a list link
        "xunit testing",  # two words of one requirement, no separator
        "CI/CD with GitHub Actions and Docker",  # "with" between the first two terms
    ],
)
def test_conjoined_terms_does_not_split_a_description_into_a_list(sentence):
    assert conjoined_terms(sentence) is None
