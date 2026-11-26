"""Convert a DOCX to PDF with LibreOffice: to count its real pages, or to keep the PDF.

Uses ``soffice`` or ``libreoffice`` when it is on the PATH, else the Flatpak build
(``org.libreoffice.LibreOffice``), which is how it is installed on the author's machine. Set
``JOBOMATIC_LIBREOFFICE=flatpak`` (or a command or path) to choose one and skip the others. The page count of the PDF comes from
``pdfinfo``. Slow (a few seconds) and not available everywhere, so callers ask for it explicitly
and a missing tool is reported, never guessed around.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from jobomatic.documents.service import PageCountUnavailable, PdfExportUnavailable

_FLATPAK_APP = "org.libreoffice.LibreOffice"
# Which LibreOffice to use. Unset: try ``soffice`` / ``libreoffice`` on the PATH, then the Flatpak.
# "flatpak": only the Flatpak. Anything else: that command or path, only.
LIBREOFFICE_ENV = "JOBOMATIC_LIBREOFFICE"
_TIMEOUT_SECONDS = 180
_PAGES_RE = re.compile(r"^Pages:\s+(\d+)", re.MULTILINE)


class _ConversionFailed(Exception):
    """No converter made a PDF; the message says why, for the caller to say what it was doing."""


def _flatpak_command(docx: Path, out_dir: Path, args: list[str]) -> tuple[str, list[str]] | None:
    flatpak = shutil.which("flatpak")
    if not flatpak:
        return None
    if subprocess.run([flatpak, "info", _FLATPAK_APP], capture_output=True, check=False).returncode:
        return None
    # The sandbox only sees folders it is told about, and resolves relative paths elsewhere.
    return (
        "flatpak",
        [
            flatpak,
            "run",
            f"--filesystem={docx.parent}",
            f"--filesystem={out_dir}",
            _FLATPAK_APP,
            *args,
        ],
    )


def _converters(docx: Path, out_dir: Path) -> list[tuple[str, list[str]]]:
    """Every way this machine might convert ``docx`` into ``out_dir``/<name>.pdf, in order.

    ``JOBOMATIC_LIBREOFFICE`` chooses: ``flatpak`` uses only the Flatpak, any other value is the
    one command or path to use. Unset, a tool on the PATH is tried first and then the Flatpak. A
    tool on the PATH is not necessarily a working one (a distro's ``libreoffice-common`` alone
    ships ``soffice`` without the Writer module and fails with "source file could not be
    loaded"), so the caller tries each until one produces a PDF.
    """
    args = ["--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx)]
    chosen = os.environ.get(LIBREOFFICE_ENV, "").strip()
    found: list[tuple[str, list[str]]] = []
    if chosen.lower() == "flatpak":
        flatpak = _flatpak_command(docx, out_dir, args)
        if flatpak is None:
            raise _ConversionFailed(
                f"{LIBREOFFICE_ENV}=flatpak but the Flatpak {_FLATPAK_APP} is not installed"
            )
        return [flatpak]
    if chosen:
        binary = shutil.which(chosen)
        if binary is None:
            raise _ConversionFailed(f"{LIBREOFFICE_ENV}={chosen!r} not found")
        return [(chosen, [binary, *args])]
    for name in ("soffice", "libreoffice"):
        binary = shutil.which(name)
        if binary:
            found.append((name, [binary, *args]))
    flatpak = _flatpak_command(docx, out_dir, args)
    if flatpak:
        found.append(flatpak)
    if not found:
        raise _ConversionFailed(
            "LibreOffice was not found (neither 'soffice' nor 'libreoffice' on the PATH nor the "
            f"Flatpak {_FLATPAK_APP}); see {LIBREOFFICE_ENV}"
        )
    return found


def _convert(docx: Path, out_dir: Path) -> Path:
    """Convert with the first tool that works; raise with every failure if none does."""
    failures: list[str] = []
    for name, command in _converters(docx, out_dir):
        try:
            done = subprocess.run(
                command, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, check=False
            )
        except subprocess.TimeoutExpired:
            failures.append(f"{name}: timed out")
            continue
        pdf = out_dir / f"{docx.stem}.pdf"
        if done.returncode == 0 and pdf.is_file():
            return pdf
        last = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        failures.append(f"{name}: {last[0]}")
    raise _ConversionFailed("LibreOffice failed (" + "; ".join(failures) + ")")


class LibreOfficePageCounter:
    """``PageCounter`` that asks ``pdfinfo``, converting with LibreOffice first unless the file is
    already a PDF."""

    def count(self, path: Path) -> int:
        document = path.resolve()
        if not document.is_file():
            raise PageCountUnavailable(f"cannot count pages: {document} does not exist")
        pdfinfo = shutil.which("pdfinfo")
        if not pdfinfo:
            raise PageCountUnavailable(
                "cannot count pages: 'pdfinfo' (poppler-utils) was not found"
            )
        with tempfile.TemporaryDirectory() as scratch:
            if document.suffix.lower() == ".pdf":
                pdf = document
            else:
                try:
                    pdf = _convert(document, Path(scratch).resolve())
                except _ConversionFailed as exc:
                    raise PageCountUnavailable(f"cannot count pages: {exc}") from exc
            info = subprocess.run([pdfinfo, str(pdf)], capture_output=True, text=True, check=False)
            match = _PAGES_RE.search(info.stdout)
            if not match:
                raise PageCountUnavailable("cannot count pages: 'pdfinfo' gave no page count")
            return int(match.group(1))


class LibreOfficePdfExporter:
    """``PdfExporter`` that saves LibreOffice's PDF of a DOCX beside it, replacing an earlier one.
    A failed conversion writes nothing."""

    def export(self, path: Path) -> Path:
        document = path.resolve()
        if not document.is_file():
            raise PdfExportUnavailable(f"cannot make a PDF: {document} does not exist")
        target = path.with_suffix(".pdf")
        if path.suffix.lower() == ".pdf":
            raise PdfExportUnavailable(
                f"cannot make a PDF: {path.name} would overwrite itself; name the document .docx"
            )
        with tempfile.TemporaryDirectory() as scratch:
            try:
                made = _convert(document, Path(scratch).resolve())
            except _ConversionFailed as exc:
                raise PdfExportUnavailable(f"cannot make a PDF: {exc}") from exc
            shutil.move(made, target)
        return target
