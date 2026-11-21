"""The skim budget (ADR 0035): a recruiter can tell in 15 seconds whether the candidate fits.

The limits are in ``documents.skim``. These tests hold the generators to them, show that content
over a limit is refused with the field named, and check that cutting prose never cuts mid-thought.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from jobomatic import applications
from jobomatic.commands import render as render_command
from jobomatic.documents import service, skim
from jobomatic.interfaces.mcp import server

FIXTURES = Path(__file__).parent / "fixtures"
STRONG = FIXTURES / "strong-fit-jd.md"


def _resume() -> dict:
    return json.loads((FIXTURES / "documents" / "resume.json").read_text(encoding="utf-8"))


def _letter() -> dict:
    return json.loads((FIXTURES / "documents" / "cover-letter.json").read_text(encoding="utf-8"))


# -- shorten ---------------------------------------------------------------------------------


def test_text_inside_the_budget_is_left_alone() -> None:
    assert skim.shorten("Built a thing.  It worked.", 10) == "Built a thing. It worked."


def test_it_cuts_at_the_last_whole_sentence() -> None:
    text = "Built the API in C#. Cut the load time by half. Then wrote a long story about it."
    assert skim.shorten(text, 11) == "Built the API in C#. Cut the load time by half."


def test_a_long_sentence_is_cut_at_a_clause_not_in_the_middle_of_one() -> None:
    text = (
        "Participated in Agile development using Jira for sprints and story pointing; "
        "tracked assigned tasks and shared progress at daily scrums; "
        "took part in reviews and retrospectives with cross-functional teams"
    )
    assert skim.shorten(text, 20) == (
        "Participated in Agile development using Jira for sprints and story pointing; "
        "tracked assigned tasks and shared progress at daily scrums"
    )


def test_a_cut_never_adds_words_or_ends_on_a_connector() -> None:
    text = "one two three four five six seven eight nine ten eleven twelve"
    cut = skim.shorten(text, 6)
    assert text.startswith(cut) and skim.words(cut) <= 6
    assert not skim.shorten("alpha beta gamma delta with epsilon zeta", 5).endswith("with")


def test_the_summary_keeps_the_sentences_that_speak_to_the_posting() -> None:
    text = "I build APIs. I like hiking. I ship Claude Code workflows. I knit."
    chosen = skim.pick_sentences(text, 8, lambda s: 1 if "Claude" in s else 0)
    assert chosen == "I build APIs. I ship Claude Code workflows."  # the first always stays


# -- the generators meet the budget ----------------------------------------------------------


def test_the_generated_resume_and_letter_are_within_the_budget() -> None:
    from jobomatic import bootstrap
    from jobomatic.commands.cover_letter import draft_letter
    from jobomatic.commands.resume import draft_resume
    from jobomatic.fit.engine import rate_parsed_jd
    from jobomatic.fit.parser import parse_jd

    jd = STRONG.read_text(encoding="utf-8")
    profile = bootstrap.load_profile()
    parsed = parse_jd(jd)
    assert skim.problems(draft_resume(profile, parsed, jd)) == []
    letter, _ = draft_letter(profile, parsed, rate_parsed_jd(parsed, profile), "Acme")
    assert skim.problems(letter) == []


def test_the_headline_is_the_candidates_role_and_skills_they_have() -> None:
    from jobomatic.commands.resume import _build_tagline

    class Ident:
        headline = "**Full-Stack .NET Developer | Enterprise Applications**"

    class Profile:
        identity = Ident()

    class Parsed:
        title = "Senior AI Software Developer"

    tagline = _build_tagline(
        Parsed(),
        Profile(),
        [".NET", "Claude Code", "Claude", "C# and .NET development", "AI", "Azure"],
    )
    assert tagline == "Full-Stack .NET Developer | Claude Code · AI · Azure"


# -- content over the budget is refused, naming the field ------------------------------------


def test_a_resume_that_cannot_be_skimmed_is_refused_with_every_field_named(tmp_path: Path) -> None:
    data = _resume()
    data["tagline"] = "Senior Developer | " + " · ".join(f"skill{i}" for i in range(15))
    data["experience"][0]["bullets"][0] = " ".join(["word"] * (skim.BULLET_WORDS + 5))
    out = tmp_path / "r.docx"
    with pytest.raises(ToolError) as caught:
        server.render_resume(data, str(STRONG), out=str(out))
    message = str(caught.value)
    assert "too long to skim in 15 seconds" in message
    assert "tagline" in message and "experience[0]" in message and "bullet 0" in message
    assert not out.exists() and applications.load_applications() == []


def test_a_letter_that_cannot_be_skimmed_is_refused(tmp_path: Path) -> None:
    data = _letter()
    data["hook"] = "I like this role. It suits me. I would be a fit. Please read on."
    data["closing"] = " ".join(["please"] * 40)
    with pytest.raises(ToolError) as caught:
        server.render_cover_letter(data, str(STRONG), out=str(tmp_path / "c.docx"))
    assert "hook" in str(caught.value) and "closing" in str(caught.value)


def test_content_inside_the_budget_renders(tmp_path: Path) -> None:
    server.render_resume(_resume(), str(STRONG), out=str(tmp_path / "r.docx"))
    server.render_cover_letter(_letter(), str(STRONG), out=str(tmp_path / "c.docx"))
    assert (tmp_path / "r.docx").is_file() and (tmp_path / "c.docx").is_file()


def test_the_part_time_kinds_have_no_budget() -> None:
    content = service.parse_content(
        "part-time-resume", (FIXTURES / "documents" / "part-time-resume.json").read_text("utf-8")
    )
    assert skim.problems(content) == []
    service.ensure_skimmable(content)


def test_a_refusal_is_a_command_error_not_a_crash(tmp_path: Path) -> None:
    data = _resume()
    data["summary"] = [" ".join(["word"] * (skim.SUMMARY_WORDS + 1))]
    result = render_command.run("resume", json.dumps(data), out=tmp_path / "r.docx")
    assert result.status == "error" and "summary" in result.messages[-1].text
