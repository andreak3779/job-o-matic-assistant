"""Unit tests for src/jobomatic/presence/skill_text.py — the generic SKILL.md
prose-template parsing and skill-term cleanup helpers shared by every
Project 3 profile-update generator (LinkedIn, GitHub, Jobgether,
Indeed/ZipRecruiter, Pluralsight)."""

from __future__ import annotations

from jobomatic.presence.skill_text import (
    clean_skill_term,
    derive_skill_terms,
    fenced_blocks,
    section_text,
    split_top_level_commas,
    substitute_fragments,
)

SAMPLE_SKILL_MD = """\
# Update Job Board Profiles Skill

## Copy Fragments
```
cert_status_short: "AZ-900 Certified"
github_copilot_course_count: "7"
```

## Character Limits
Headline: 100 chars
"""


def test_section_text_extracts_named_section() -> None:
    block = section_text(SAMPLE_SKILL_MD, "Character Limits")
    assert block is not None
    assert "Headline" in block
    assert "Copy Fragments" not in block


def test_section_text_missing_returns_none() -> None:
    assert section_text(SAMPLE_SKILL_MD, "Nonexistent Section") is None


def test_fenced_blocks_extracts_code_block_content() -> None:
    block = section_text(SAMPLE_SKILL_MD, "Copy Fragments")
    assert block is not None
    blocks = fenced_blocks(block)
    assert len(blocks) == 1
    assert 'cert_status_short: "AZ-900 Certified"' in blocks[0]


def test_substitute_fragments_replaces_known_and_leaves_unknown() -> None:
    text = "{cert_status_short} and {unknown_fragment}"
    result = substitute_fragments(text, {"cert_status_short": "AZ-900 Certified"})
    assert result == "AZ-900 Certified and {unknown_fragment}"


def test_split_top_level_commas_respects_parens() -> None:
    parts = split_top_level_commas("C#, Entity Framework Core (v6, v8), Angular")
    assert parts == ["C#", "Entity Framework Core (v6, v8)", "Angular"]


def test_clean_skill_term_strips_trailing_parens() -> None:
    assert clean_skill_term("Entity Framework Core (course-level)") == "Entity Framework Core"


def test_clean_skill_term_drops_long_multiclause_phrases() -> None:
    assert clean_skill_term("SOLID principles and design patterns") is None


def test_derive_skill_terms_dedupes_cleans_and_excludes() -> None:
    categories = {
        "Backend": "C#, Entity Framework Core (course-level), SOLID principles and design patterns",
        "Frontend": "Angular, TypeScript, RxJS",
    }
    terms = derive_skill_terms(categories, exclude={"C#"})
    assert "C#" not in terms
    assert "Entity Framework Core" in terms
    assert "SOLID principles and design patterns" not in terms
    assert "Angular" in terms


def test_derive_skill_terms_respects_limit() -> None:
    categories = {
        "Backend": "C#, Entity Framework Core, SQL Server",
        "Frontend": "Angular, TypeScript, RxJS",
    }
    terms = derive_skill_terms(categories, limit=2)
    assert len(terms) == 2
