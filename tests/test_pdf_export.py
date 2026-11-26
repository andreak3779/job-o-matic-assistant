"""``--pdf``: a PDF saved beside the DOCX (``PdfExporter``), on every command and server tool
that offers it.

The commands are tested with a fake exporter, so they run without LibreOffice. The tests that
really convert a document skip themselves when no working converter is installed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from docx import Document

from jobomatic import bootstrap
from jobomatic.documents.adapters.page_count import (
    LibreOfficePageCounter,
    LibreOfficePdfExporter,
)
from jobomatic.documents.service import PdfExportUnavailable
from jobomatic.interfaces.cli.main import main
from jobomatic.interfaces.mcp import server
from tests.test_documents import FIXTURES

JD = Path(__file__).parent / "fixtures" / "strong-fit-jd.md"


class _FakeExporter:
    def __init__(self) -> None:
        self.exported: list[Path] = []

    def export(self, path: Path) -> Path:
        self.exported.append(path)
        pdf = path.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF-fake")
        return pdf


class _RecordingCounter:
    def __init__(self) -> None:
        self.counted: list[Path] = []

    def count(self, path: Path) -> int:
        self.counted.append(path)
        return 1


@pytest.fixture
def exporter(monkeypatch: pytest.MonkeyPatch) -> _FakeExporter:
    fake = _FakeExporter()
    monkeypatch.setattr(bootstrap, "pdf_exporter", lambda: fake)
    return fake


def _render(kind: str, out: Path, *flags: str) -> int:
    return main(["render", kind, str(FIXTURES / f"{kind}.json"), "--out", str(out), *flags])


@pytest.mark.parametrize(
    "kind", ["resume", "cover-letter", "part-time-resume", "part-time-cover-letter"]
)
def test_render_pdf_saves_a_pdf_beside_the_document(
    kind: str, tmp_path: Path, exporter: _FakeExporter, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "document.docx"

    assert _render(kind, out, "--pdf") == 0

    assert out.is_file()
    assert out.with_suffix(".pdf").is_file()
    assert f"Wrote {out.with_suffix('.pdf')}" in capsys.readouterr().out


def test_no_pdf_is_made_unless_asked(tmp_path: Path, exporter: _FakeExporter) -> None:
    assert _render("resume", tmp_path / "resume.docx") == 0

    assert exporter.exported == []
    assert not (tmp_path / "resume.pdf").exists()


def test_an_older_pdf_is_kept_and_reported(
    tmp_path: Path, exporter: _FakeExporter, capsys: pytest.CaptureFixture[str]
) -> None:
    old = tmp_path / "resume.pdf"
    old.write_bytes(b"%PDF-old")

    assert _render("resume", tmp_path / "resume.docx") == 0

    printed = capsys.readouterr()
    assert "from an earlier run" in printed.out + printed.err
    assert old.read_bytes() == b"%PDF-old"


def test_check_pages_counts_the_pdf_that_was_made(
    tmp_path: Path, exporter: _FakeExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    counter = _RecordingCounter()
    monkeypatch.setattr(bootstrap, "page_counter", lambda: counter)

    assert _render("cover-letter", tmp_path / "letter.docx", "--pdf", "--check-pages") == 0

    assert counter.counted == [tmp_path / "letter.pdf"]
    assert len(exporter.exported) == 1


def test_a_failed_export_is_an_error_and_keeps_the_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _Missing:
        def export(self, path: Path) -> Path:
            raise PdfExportUnavailable("cannot make a PDF: LibreOffice was not found")

    monkeypatch.setattr(bootstrap, "pdf_exporter", lambda: _Missing())

    assert _render("resume", tmp_path / "resume.docx", "--pdf") == 1

    printed = capsys.readouterr()
    assert "cannot make a PDF" in printed.out + printed.err
    assert (tmp_path / "resume.docx").is_file()


@pytest.mark.parametrize(
    "command",
    [
        ["generate-resume", str(JD)],
        ["generate-cover-letter", str(JD)],
        ["generate-profile-resume"],
        ["generate-profile-cover-letter"],
        ["generate-cold-call"],
    ],
)
def test_the_generators_save_and_name_the_pdf(
    command: list[str],
    tmp_path: Path,
    exporter: _FakeExporter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "document.docx"

    assert main([*command, "--out", str(out), "--pdf"]) == 0

    assert exporter.exported == [out]
    assert f"Wrote {out.with_suffix('.pdf')}" in capsys.readouterr().out


# --- the Claude Desktop tools ----------------------------------------------------------------


def _attached(blocks: list) -> list[str]:
    return [
        str(block.resource.uri).rsplit("/", 1)[-1]
        for block in blocks
        if getattr(block, "type", "") == "resource"
    ]


def _content(kind: str) -> str:
    return (FIXTURES / f"{kind}.json").read_text(encoding="utf-8")


@pytest.fixture
def desktop_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A folder the server may write to."""
    monkeypatch.setenv("JOBOMATIC_ALLOWED_DIRS", os.pathsep.join([str(JD.parent), str(tmp_path)]))
    return tmp_path


@pytest.mark.parametrize(
    "tool,kind",
    [(server.render_resume, "resume"), (server.render_cover_letter, "cover-letter")],
)
def test_a_render_tool_attaches_the_pdf_when_asked(
    tool, kind: str, desktop_out: Path, exporter: _FakeExporter
) -> None:
    out = desktop_out / "document.docx"

    blocks = tool(_content(kind), str(JD), out=str(out), pdf=True)

    assert {"document.docx", "document.pdf"} <= set(_attached(blocks))


@pytest.mark.parametrize(
    "tool",
    [server.generate_resume, server.generate_cover_letter, server.generate_cold_call],
)
def test_a_generator_tool_attaches_the_pdf_when_asked(
    tool, desktop_out: Path, exporter: _FakeExporter
) -> None:
    out = desktop_out / "document.docx"

    blocks = tool(str(JD), out=str(out), pdf=True)

    assert "document.pdf" in _attached(blocks)


def test_the_two_document_tool_makes_both_pdfs(desktop_out: Path, exporter: _FakeExporter) -> None:
    blocks = server.generate_application_documents(str(JD), pdf=True)

    assert {"resume.pdf", "cover-letter.pdf"} <= set(_attached(blocks))


def test_the_server_makes_no_pdf_unless_asked(desktop_out: Path, exporter: _FakeExporter) -> None:
    server.generate_resume(str(JD), out=str(desktop_out / "document.docx"))

    assert exporter.exported == []


# --- the real converter (skipped where LibreOffice is not installed) -----------------------


def _document(path: Path) -> Path:
    doc = Document()
    doc.add_paragraph("one page")
    doc.save(str(path))
    return path


def test_libreoffice_saves_a_pdf_that_can_be_counted(tmp_path: Path) -> None:
    source = _document(tmp_path / "letter.docx")
    (tmp_path / "letter.pdf").write_bytes(b"stale")
    try:
        pdf = LibreOfficePdfExporter().export(source)
    except PdfExportUnavailable as exc:
        pytest.skip(str(exc))

    assert pdf == tmp_path / "letter.pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
    assert LibreOfficePageCounter().count(pdf) == 1


def test_a_document_named_pdf_is_not_overwritten(tmp_path: Path) -> None:
    source = _document(tmp_path / "letter.pdf")
    before = source.read_bytes()

    with pytest.raises(PdfExportUnavailable, match="overwrite itself"):
        LibreOfficePdfExporter().export(source)

    assert source.read_bytes() == before
