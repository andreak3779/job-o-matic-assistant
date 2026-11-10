"""What goes into the index, and what is kept off cloud prompts."""

from __future__ import annotations

import datetime as dt

from jobomatic import bootstrap, corpus
from jobomatic.learning.model import Kind, LearningItem, Provider
from jobomatic.retrieval.model import Hit
from jobomatic.retrieval.service import cloud_safe_hits


def _item(item_id: str, title: str, summary: str | None, kind: Kind = Kind.COURSE) -> LearningItem:
    return LearningItem(
        id=item_id,
        provider=Provider.PLURALSIGHT,
        kind=kind,
        title=title,
        url=f"https://example.com/{item_id}",
        completed_on=dt.date(2026, 1, 1),
        summary=summary,
    )


def test_learning_chunks_use_title_and_summary_and_keep_summaryless_items():
    chunks = corpus.learning_chunks(
        [
            _item("p:a", "A", "about a"),
            _item("p:b", "B", None, Kind.LAB),
            _item("p:c", "C", "  "),
        ]
    )
    assert [(c.id, c.kind, c.text) for c in chunks] == [
        ("p:a", "course", "A. about a"),
        ("p:b", "lab", "B"),
        ("p:c", "course", "C"),
    ]
    assert all(c.status == "complete" and not c.local_only for c in chunks)
    assert chunks[0].url == "https://example.com/p:a"


def test_the_demo_profile_chunks_have_unique_ids_and_the_right_privacy():
    chunks = bootstrap.retrieval_chunks()
    assert len({c.id for c in chunks}) == len(chunks)
    kinds = {c.kind for c in chunks}
    assert {"course", "lab", "module", "learning_path", "project", "experience", "story"} <= kinds
    for chunk in chunks:
        assert chunk.local_only == (chunk.kind in {"experience", "story"})


def test_employer_less_self_study_is_not_indexed_as_experience():
    profile = bootstrap.load_profile()
    companies = {r.company for r in profile.resume_roles}
    chunks = corpus.experience_chunks(profile)
    assert chunks and all(not c.id.startswith("experience::") for c in chunks)
    assert "" not in companies or all(c.title.split(" — ")[0] for c in chunks)


def test_stories_and_resume_bullets_never_reach_a_cloud_prompt():
    chunks = bootstrap.retrieval_chunks()
    hits = [Hit(c, 0.9, 0.9, 0.0) for c in chunks]
    safe = cloud_safe_hits(hits)
    assert safe and all(h.chunk.kind not in {"experience", "story"} for h in safe)


def test_two_roles_at_one_employer_get_distinct_chunk_ids():
    profile = bootstrap.load_profile()
    first = next(r for r in profile.resume_roles if r.company and r.bullets)
    twin = first.model_copy()  # same employer, same title: the worst case for id clashes
    profile = profile.model_copy(update={"roles": [first, twin]})
    ids = [c.id for c in corpus.experience_chunks(profile)]
    assert len(ids) == len(set(ids)) == 2 * len(first.bullets)
