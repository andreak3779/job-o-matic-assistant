"""The resume page budget (``jobomatic.documents.pagefit``), the page-limit check and its CLI flag.

Everything here is pure or uses a fake page counter, so it runs without LibreOffice. The two tests
that really convert a document skip themselves when no working converter is installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from jobomatic.documents import pagefit, service
from jobomatic.documents.adapters.page_count import LibreOfficePageCounter
from jobomatic.documents.model import ResumeContact, ResumeJob, SkillLine, TailoredResume
from jobomatic.documents.service import DocumentError, PageCountUnavailable

BULLET = (
    "Built and maintained a service-oriented API with layered services and automated tests. " * 2
)


def _resume(
    *,
    roles: int = 6,
    bullets: int = 10,
    skill_lines: int = 9,
    own_work: bool = False,
    summary: str = "Full-stack developer with a decade of enterprise experience.",
) -> TailoredResume:
    jobs = [
        ResumeJob(
            title=f"Developer {n}",
            company="" if (own_work and n == 0) else f"Exampleton Co {n}",
            location="Springfield",
            dates=f"20{10 + n} - 20{11 + n}",
            bullets=[f"{BULLET}(role {n}, bullet {b})" for b in range(bullets)],
        )
        for n in range(roles)
    ]
    skills = [
        SkillLine(
            label=f"Area {n}",
            skills=", ".join(f"Skill{n}_{k} (detail a, detail b)" for k in range(30)),
        )
        for n in range(skill_lines)
    ]
    return TailoredResume(
        contact=ResumeContact(
            name="Sarah Ashford", email="sarah@example.com", phone="(410) 555-0142"
        ),
        tagline="Full-Stack .NET Developer | C# · ASP.NET Core · Azure",
        summary=[summary],
        skills=skills,
        experience=jobs,
        additional_experience="Analyst and programmer roles for insurance and government clients.",
        education=["Diploma, Example College, 1997"],
        certifications=["Microsoft Azure Fundamentals (AZ-900), certified April 2026"],
    )


def _bullets(content: TailoredResume) -> list[int]:
    return [len(job.bullets) for job in content.experience]


def test_content_that_already_fits_is_returned_unchanged() -> None:
    small = _resume(roles=2, bullets=2, skill_lines=3)
    small = small.model_copy(
        update={"skills": [s.model_copy(update={"skills": "C#, SQL"}) for s in small.skills]}
    )
    assert pagefit.fit_resume(small) == small


def test_a_long_resume_is_trimmed_to_fit_and_keeps_every_role() -> None:
    long = _resume()
    assert pagefit.estimate_height(long) > pagefit.budget_height()
    fitted = pagefit.fit_resume(long)
    assert pagefit.estimate_height(fitted) <= pagefit.budget_height()
    assert len(fitted.experience) == len(long.experience)
    assert [j.title for j in fitted.experience] == [j.title for j in long.experience]


def test_skills_are_capped_at_seven_lines_even_when_the_resume_would_fit() -> None:
    content = _resume(roles=1, bullets=1, skill_lines=9)
    content = content.model_copy(
        update={"skills": [s.model_copy(update={"skills": "C#, SQL"}) for s in content.skills]}
    )
    assert len(pagefit.fit_resume(content).skills) == pagefit.MAX_SKILL_LINES


def test_the_bullets_kept_are_the_first_and_most_relevant_ones() -> None:
    fitted = pagefit.fit_resume(_resume())
    for original, kept in zip(_resume().experience, fitted.experience, strict=True):
        assert kept.bullets == original.bullets[: len(kept.bullets)]


def test_the_oldest_roles_lose_bullets_before_the_newest() -> None:
    counts = _bullets(pagefit.fit_resume(_resume()))
    assert counts == sorted(counts, reverse=True)  # newest first: never fewer than an older role
    assert counts[0] > counts[-1]


def test_recent_roles_never_fall_below_the_minimum() -> None:
    counts = _bullets(pagefit.fit_resume(_resume()))
    assert all(n >= pagefit.MIN_BULLETS for n in counts[: pagefit.RECENT_ROLES])
    assert all(n >= 1 for n in counts)


def test_a_self_directed_role_gives_up_bullets_before_any_employer() -> None:
    fitted = pagefit.fit_resume(_resume(own_work=True))
    counts = _bullets(fitted)
    assert fitted.experience[0].company == ""
    assert counts[0] <= min(counts[1:])


def test_a_skill_list_is_never_cut_inside_a_parenthesis() -> None:
    fitted = pagefit.fit_resume(_resume())
    for line in fitted.skills:
        assert line.skills.count("(") == line.skills.count(")")
        assert not line.skills.endswith(",")


def test_split_skills_ignores_commas_inside_parentheses() -> None:
    text = "C# (Generics, Delegates), Docker, NgRx (store, effects, entity), SQL"
    assert pagefit.split_skills(text) == [
        "C# (Generics, Delegates)",
        "Docker",
        "NgRx (store, effects, entity)",
        "SQL",
    ]


def test_estimate_grows_when_content_is_added() -> None:
    base = _resume(roles=2, bullets=2)
    more = base.model_copy(
        update={
            "experience": [
                j.model_copy(update={"bullets": j.bullets + [BULLET]}) for j in base.experience
            ]
        }
    )
    assert pagefit.estimate_height(more) > pagefit.estimate_height(base)


def test_content_that_cannot_fit_is_refused_with_a_reason() -> None:
    with pytest.raises(DocumentError, match="pages even after trimming"):
        pagefit.fit_resume(_resume(summary="A very long summary sentence. " * 400))


# --- the page-limit check -------------------------------------------------------------------


class _FakeCounter:
    def __init__(self, pages: int) -> None:
        self.pages = pages

    def count(self, path: Path) -> int:
        return self.pages


@pytest.mark.parametrize(
    ("kind", "pages"), [("resume", 1), ("resume", 2), ("cover-letter", 1), ("part-time-resume", 5)]
)
def test_a_document_inside_its_limit_passes(kind: str, pages: int, tmp_path: Path) -> None:
    assert service.check_pages(kind, tmp_path / "x.docx", _FakeCounter(pages)) == pages


@pytest.mark.parametrize(
    ("kind", "pages", "words"),
    [
        ("resume", 3, "at most 2"),
        ("cover-letter", 2, "exactly 1"),
        ("cover-letter", 0, "exactly 1"),
    ],
)
def test_a_document_outside_its_limit_is_refused(
    kind: str, pages: int, words: str, tmp_path: Path
) -> None:
    with pytest.raises(DocumentError, match=words):
        service.check_pages(kind, tmp_path / "x.docx", _FakeCounter(pages))


# --- the render command's flag ----------------------------------------------------------------


def _render_args(tmp_path: Path, kind: str) -> list[str]:
    from tests.test_documents import FIXTURES

    return [
        "render",
        kind,
        str(FIXTURES / f"{kind}.json"),
        "--out",
        str(tmp_path / f"{kind}.docx"),
        "--check-pages",
    ]


def test_render_check_pages_reports_the_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobomatic import bootstrap
    from jobomatic.interfaces.cli.main import main

    monkeypatch.setattr(bootstrap, "page_counter", lambda: _FakeCounter(2))
    assert main(_render_args(tmp_path, "resume")) == 0
    assert "Pages: 2" in capsys.readouterr().out


def test_render_check_pages_fails_loudly_and_keeps_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobomatic import bootstrap
    from jobomatic.interfaces.cli.main import main

    monkeypatch.setattr(bootstrap, "page_counter", lambda: _FakeCounter(3))
    assert main(_render_args(tmp_path, "resume")) == 1
    assert "at most 2" in capsys.readouterr().out
    assert (tmp_path / "resume.docx").is_file()


def test_render_check_pages_without_libreoffice_is_an_error_not_a_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobomatic import bootstrap
    from jobomatic.interfaces.cli.main import main

    class _Missing:
        def count(self, path: Path) -> int:
            raise PageCountUnavailable("cannot count pages: LibreOffice was not found")

    monkeypatch.setattr(bootstrap, "page_counter", lambda: _Missing())
    assert main(_render_args(tmp_path, "cover-letter")) == 1
    assert "LibreOffice was not found" in capsys.readouterr().out


def test_generate_resume_is_trimmed_to_the_budget(tmp_path: Path) -> None:
    from jobomatic.commands.resume import generate_resume

    jd = Path(__file__).parent / "fixtures" / "strong-fit-jd.md"
    out, _, _ = generate_resume(jd, out_path=tmp_path / "resume.docx")
    doc = Document(str(out))
    text_length = sum(len(p.text) for p in doc.paragraphs)
    assert text_length > 0
    # the same content the command wrote, rebuilt and measured by the estimator
    from jobomatic import bootstrap
    from jobomatic.commands.resume import _build_tagline, _resume_content
    from jobomatic.fit.parser import parse_jd

    profile = bootstrap.load_profile()
    parsed = parse_jd(jd.read_text(encoding="utf-8"))
    content = _resume_content(profile, parsed, _build_tagline(parsed, profile))
    assert pagefit.estimate_height(content) <= pagefit.budget_height()


# --- the real converter (skipped where LibreOffice is not installed) -----------------------


def _converter_or_skip(tmp_path: Path) -> LibreOfficePageCounter:
    counter = LibreOfficePageCounter()
    probe = tmp_path / "probe.docx"
    doc = Document()
    doc.add_paragraph("probe")
    doc.save(str(probe))
    try:
        counter.count(probe)
    except PageCountUnavailable as exc:
        pytest.skip(str(exc))
    return counter


def test_the_libreoffice_counter_counts_real_pages(tmp_path: Path) -> None:
    counter = _converter_or_skip(tmp_path)
    one = tmp_path / "one.docx"
    doc = Document()
    doc.add_paragraph("one page")
    doc.save(str(one))
    assert counter.count(one) == 1
    two = tmp_path / "two.docx"
    doc = Document()
    doc.add_paragraph("page one")
    doc.add_page_break()
    doc.add_paragraph("page two")
    doc.save(str(two))
    assert counter.count(two) == 2


def test_a_trimmed_resume_really_is_at_most_two_pages(tmp_path: Path) -> None:
    from jobomatic.documents.adapters.docx_tailored import DocxTailoredResume

    counter = _converter_or_skip(tmp_path)
    out = tmp_path / "resume.docx"
    DocxTailoredResume().render(pagefit.fit_resume(_resume()), out)
    assert counter.count(out) <= pagefit.RESUME_MAX_PAGES


# --- choosing which LibreOffice -----------------------------------------------------------------


@pytest.fixture
def _no_real_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the machine has ``soffice`` and ``flatpak`` (with the LibreOffice app installed)."""
    import subprocess

    from jobomatic.documents.adapters import page_count

    tools = {"soffice": "/usr/bin/soffice", "flatpak": "/usr/bin/flatpak", "mine": "/opt/mine/lo"}
    monkeypatch.setattr(page_count.shutil, "which", lambda name: tools.get(name))
    monkeypatch.setattr(
        page_count.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""),
    )
    monkeypatch.delenv("JOBOMATIC_LIBREOFFICE", raising=False)


def _names(tmp_path: Path) -> list[str]:
    from jobomatic.documents.adapters.page_count import _converters

    return [name for name, _ in _converters(tmp_path / "a.docx", tmp_path)]


@pytest.mark.usefixtures("_no_real_tools")
def test_by_default_the_path_tool_is_tried_before_the_flatpak(tmp_path: Path) -> None:
    assert _names(tmp_path) == ["soffice", "flatpak"]


@pytest.mark.usefixtures("_no_real_tools")
def test_the_flatpak_can_be_chosen_outright(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobomatic.documents.adapters.page_count import _converters

    monkeypatch.setenv("JOBOMATIC_LIBREOFFICE", "flatpak")
    [(name, command)] = _converters(tmp_path / "a.docx", tmp_path)
    assert name == "flatpak"
    assert command[:2] == ["/usr/bin/flatpak", "run"]
    assert f"--filesystem={tmp_path}" in command  # the sandbox must be told about both folders


@pytest.mark.usefixtures("_no_real_tools")
def test_another_command_can_be_chosen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOMATIC_LIBREOFFICE", "mine")
    assert _names(tmp_path) == ["mine"]


@pytest.mark.usefixtures("_no_real_tools")
def test_a_chosen_tool_that_is_missing_is_an_error_not_a_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOBOMATIC_LIBREOFFICE", "nothing-here")
    with pytest.raises(PageCountUnavailable, match="nothing-here"):
        _names(tmp_path)
