"""What the documents use cases need from the outside world. Adapters implement these."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeVar

from jobomatic.documents.model import PartTimeCoverLetter, PartTimeResume

T_contra = TypeVar("T_contra", contravariant=True)


class DocumentRenderer(Protocol[T_contra]):
    """Turns content into a file. The DOCX renderers are one implementation."""

    def render(self, content: T_contra, out_path: Path) -> Path: ...


class PageCounter(Protocol):
    """Measures how many pages a rendered document really has."""

    def count(self, path: Path) -> int: ...


PartTimeResumeRenderer = DocumentRenderer[PartTimeResume]
PartTimeCoverLetterRenderer = DocumentRenderer[PartTimeCoverLetter]
