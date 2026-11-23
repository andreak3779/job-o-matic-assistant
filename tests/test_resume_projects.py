"""Which projects the deterministic resume shows, and how the self-directed role avoids repeating them.

The rules: pinned projects first, then the best match for the posting, at most ``budget.PROJECTS``;
a project with no ``resume_bullets`` is never used; a private repository shows no link; a bullet of
the self-directed role that names a shown project is left out.
"""

from __future__ import annotations

from types import SimpleNamespace

from jobomatic import bootstrap
from jobomatic.commands.resume import _job_content, _project_content, _subtitle, draft_resume
from jobomatic.documents import budget, skim
from jobomatic.fit.parser import parse_jd
from jobomatic.profile.model import Project, Role

NO_POSTING = SimpleNamespace(required=[], nice_to_have=[])


def _project(name: str, *, pin: bool = False, bullets: int = 2, stack=None, **extra) -> Project:
    return Project(
        name=name,
        url=f"https://github.com/example/{name}",
        stack=stack or ["Python"],
        description=f"{name} description",
        resume_pin=pin,
        resume_bullets=[f"{name} bullet {n}." for n in range(bullets)],
        **extra,
    )


def _profile(*projects: Project):
    return bootstrap.load_profile().model_copy(update={"projects": list(projects)})


def _posting(*required: str):
    return SimpleNamespace(required=list(required), nice_to_have=[])


def test_the_pinned_projects_come_first_whatever_the_posting_asks_for() -> None:
    profile = _profile(
        _project("Alpha", stack=["Angular"]),
        _project("Beta", pin=True, stack=["Python"]),
        _project("Gamma", stack=["Angular"]),
    )
    shown = _project_content(profile, _posting("Angular"))
    assert [p.name for p in shown][0] == "Beta"


def test_the_other_slots_go_to_the_best_match_for_the_posting() -> None:
    profile = _profile(
        _project("Alpha", stack=["Docker"]),
        _project("Beta", pin=True),
        _project("Gamma", stack=["Angular", "NgRx"]),
    )
    assert [p.name for p in _project_content(profile, _posting("Angular", "NgRx"))] == [
        "Beta",
        "Gamma",
        "Alpha",
    ]


def test_ties_keep_the_order_of_the_profile() -> None:
    profile = _profile(_project("Alpha"), _project("Beta"), _project("Gamma"))
    assert [p.name for p in _project_content(profile, NO_POSTING)] == ["Alpha", "Beta", "Gamma"]


def test_at_most_the_budgeted_number_of_projects_and_bullets() -> None:
    profile = _profile(*(_project(f"P{n}", pin=True, bullets=5) for n in range(6)))
    shown = _project_content(profile, NO_POSTING)
    assert len(shown) == budget.PROJECTS
    assert all(len(p.bullets) == budget.PROJECT_BULLETS for p in shown)


def test_a_project_with_no_resume_bullets_is_never_shown_even_if_pinned() -> None:
    profile = _profile(_project("Quiet", pin=True, bullets=0), _project("Loud"))
    assert [p.name for p in _project_content(profile, NO_POSTING)] == ["Loud"]


def test_no_project_has_bullets_means_no_projects() -> None:
    assert _project_content(_profile(_project("Quiet", bullets=0)), NO_POSTING) == []


def test_a_private_repository_shows_no_link() -> None:
    profile = _profile(_project("Open"), _project("Hidden", repo_private=True))
    links = {p.name: p.link for p in _project_content(profile, NO_POSTING)}
    assert links["Open"] == "github.com/example/Open"
    assert links["Hidden"] == ""


def test_a_bullet_over_the_word_limit_is_shortened() -> None:
    long = _project("Long")
    long = long.model_copy(update={"resume_bullets": ["One two three four five. " * 12]})
    shown = _project_content(_profile(long), NO_POSTING)
    assert skim.words(shown[0].bullets[0]) <= skim.BULLET_WORDS


def test_the_subtitle_stops_before_the_link_would_wrap() -> None:
    stack = ["Python", "MCP (Model Context Protocol)", "Claude Desktop integration", "Claude Code"]
    subtitle = _subtitle(stack)
    assert subtitle == "Python · MCP (Model Context Protocol)"
    assert len(subtitle) <= budget.PROJECT_SUBTITLE_CHARS
    assert _subtitle(
        ["A very long first item that is over the limit by itself, really"]
    ).startswith("A very long")  # always at least the first item


def _roles(*bullets_by_role: tuple[str, list[str]]) -> SimpleNamespace:
    return SimpleNamespace(
        resume_roles=[
            Role(title=t, company=c, dates="2025", bullets=b) for (t, c), b in bullets_by_role
        ]
    )


def test_a_self_directed_bullet_naming_a_shown_project_is_left_out() -> None:
    profile = _roles(
        (("Self-directed", ""), ["Built CookingTime, a Blazor app.", "Finished 40 courses."]),
        (("Developer", "Acme"), ["Shipped CookingTime-like features at work."]),
    )
    jobs = _job_content(profile, NO_POSTING, frozenset({"cookingtime"}))
    assert jobs[0].bullets == ["Finished 40 courses."]
    assert jobs[1].bullets == ["Shipped CookingTime-like features at work."]  # employers untouched


def test_the_role_keeps_its_own_bullets_if_filtering_would_empty_it() -> None:
    profile = _roles((("Self-directed", ""), ["Built CookingTime, a Blazor app."]))
    jobs = _job_content(profile, NO_POSTING, frozenset({"cookingtime"}))
    assert jobs[0].bullets == ["Built CookingTime, a Blazor app."]


def test_with_no_shown_projects_nothing_is_filtered() -> None:
    profile = _roles((("Self-directed", ""), ["Built CookingTime, a Blazor app."]))
    assert _job_content(profile, NO_POSTING)[0].bullets == ["Built CookingTime, a Blazor app."]


def test_the_demo_resume_has_its_pinned_project_and_stays_within_the_budget() -> None:
    jd = (__import__("pathlib").Path(__file__).parent / "fixtures" / "strong-fit-jd.md").read_text(
        encoding="utf-8"
    )
    profile = bootstrap.load_profile()
    resume = draft_resume(profile, parse_jd(jd), jd)
    assert [p.name for p in resume.projects] == ["CookingTime"]
    assert skim.problems(resume) == []
