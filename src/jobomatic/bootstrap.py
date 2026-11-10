"""Wires adapters to ports. The only place that knows which implementation is in use."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jobomatic import corpus, paths, yamlio
from jobomatic.documents.adapters.docx_part_time import DocxPartTimeCoverLetter, DocxPartTimeResume
from jobomatic.documents.adapters.docx_tailored import DocxTailoredCoverLetter, DocxTailoredResume
from jobomatic.documents.adapters.page_count import LibreOfficePageCounter
from jobomatic.documents.ports import DocumentRenderer, PageCounter
from jobomatic.documents.service import DocumentError
from jobomatic.learning.adapters.yaml_store import (
    FileImportArchive,
    YamlLearningStore,
    load_topic_rules,
)
from jobomatic.learning.model import TopicRules
from jobomatic.learning.service import LearningError
from jobomatic.profile import service
from jobomatic.profile.adapters.yaml_vault import YamlVaultProfile
from jobomatic.profile.model import PresenceView, Profile
from jobomatic.profile.ports import ProfileRepository
from jobomatic.retrieval.adapters.ollama import OllamaEmbedder
from jobomatic.retrieval.adapters.sqlite_index import SqliteIndex
from jobomatic.retrieval.model import Chunk


def profile_repository(root: Path | None = None) -> ProfileRepository:
    """The profile stored in the vault's ``profile/`` folder (see ``jobomatic.paths``).

    ``root`` is for tests that build a profile folder somewhere else; ``None`` means the vault.
    """
    return YamlVaultProfile(paths.profile_dir(root))


def load_presence_view(root: Path | None = None) -> PresenceView:
    """The public part of the profile, for the LinkedIn/GitHub/job-board generators."""
    return service.presence_view(load_profile(root))


def load_profile(root: Path | None = None) -> Profile:
    """Load and check the whole profile. Raises ``ProfileError`` if it cannot be used."""
    return service.load_profile(profile_repository(root))


def learning_store() -> YamlLearningStore:
    """The imported learning items, kept in the vault's ``profile/learning/items.yaml``."""
    return YamlLearningStore(paths.profile_dir())


def import_archive() -> FileImportArchive:
    """Raw exports, kept in the vault's ``imports/`` folder."""
    return FileImportArchive(paths.imports_dir())


def topic_rules() -> TopicRules:
    """Topic rules: the vault's own if it has them, else the packaged defaults."""
    return load_topic_rules(paths.profile_dir())


def mslearn_share_id() -> str:
    """The Microsoft Learn share id, from the vault's ``private/sources.yaml``.

    Anyone holding it can view the transcript, so it lives only in the vault.
    """
    path = paths.private_dir() / "sources.yaml"
    try:
        data = yamlio.load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        data = {}
    share_id = str(data.get("mslearn_share_id") or "").strip() if isinstance(data, dict) else ""
    if not share_id:
        raise LearningError(
            f"no Microsoft Learn share id: add `mslearn_share_id: <id>` to {path} "
            "(the last part of your transcript share link)"
        )
    return share_id


def document_renderer(kind: str) -> DocumentRenderer[Any]:
    """The renderer for a kind of document (see ``KINDS``)."""
    renderers: dict[str, DocumentRenderer[Any]] = {
        "resume": DocxTailoredResume(),
        "cover-letter": DocxTailoredCoverLetter(),
        "part-time-resume": DocxPartTimeResume(),
        "part-time-cover-letter": DocxPartTimeCoverLetter(),
    }
    if kind not in renderers:
        raise DocumentError(f"unknown document kind {kind!r}; expected one of {sorted(renderers)}")
    return renderers[kind]


def page_counter() -> PageCounter:
    """Measures real page counts with LibreOffice (slow; used only when asked)."""
    return LibreOfficePageCounter()


def retrieval_index() -> SqliteIndex:
    """The evidence index: one SQLite file in the vault's ``index/`` folder. Rebuildable."""
    return SqliteIndex(paths.evidence_index_path())


def retrieval_embedder(model: str | None = None) -> OllamaEmbedder:
    """The local embedding model (Ollama). Nothing else in the repo needs it running."""
    return OllamaEmbedder(model) if model else OllamaEmbedder()


def retrieval_chunks(root: Path | None = None) -> list[Chunk]:
    """Everything the evidence index should hold, from the profile and the learning history."""
    return corpus.chunks_for(load_profile(root), learning_store().load())
