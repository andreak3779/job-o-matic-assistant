"""What the evidence index contains: the candidate's record, turned into retrievable chunks.

This is the only place that knows both the profile and the learning history, so the retrieval
module itself needs neither (ADR 0016, 0019). Private prose (resume bullets, interview stories)
is marked ``local_only``, so it can be searched on this machine but never goes into a prompt
sent to a cloud model.
"""

from __future__ import annotations

from collections.abc import Sequence

from jobomatic.learning.model import LearningItem
from jobomatic.profile.model import Profile
from jobomatic.retrieval.model import Chunk


def learning_chunks(items: Sequence[LearningItem]) -> list[Chunk]:
    """One chunk per completed course, lab, module or path: its title and summary."""
    chunks: list[Chunk] = []
    for item in items:
        summary = (item.summary or "").strip()
        chunks.append(
            Chunk(
                id=item.id,
                kind=item.kind.value,
                title=item.title,
                text=f"{item.title}. {summary}" if summary else item.title,
                status="complete",
                url=item.url or "",
            )
        )
    return chunks


def project_chunks(profile: Profile) -> list[Chunk]:
    chunks: list[Chunk] = []
    for project in profile.projects:
        parts = [project.name, project.description, "Stack: " + ", ".join(project.stack)]
        if project.skills_evidence:
            parts.append("Skills evidenced: " + ", ".join(project.skills_evidence))
        chunks.append(
            Chunk(
                id=f"project:{project.name}",
                kind="project",
                title=project.name,
                text=". ".join(p for p in parts if p),
            )
        )
    return chunks


def experience_chunks(profile: Profile) -> list[Chunk]:
    """Resume bullets, one chunk each. Self-directed study (no employer) is left out: its long
    summary repeats the course and project chunks and outranks them for almost any query."""
    chunks: list[Chunk] = []
    seen: dict[str, int] = {}  # one employer can hold several roles, and ids must stay unique
    for role in profile.resume_roles:
        if not role.company:
            continue
        label = f"{role.company}:{role.title}"
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = f"{label}:{seen[label]}"
        for number, bullet in enumerate(role.bullets):
            chunks.append(
                Chunk(
                    id=f"experience:{label}:{number}",
                    kind="experience",
                    title=f"{role.company} — {role.title}",
                    text=bullet,
                    local_only=True,
                )
            )
    return chunks


def story_chunks(profile: Profile) -> list[Chunk]:
    """Interview stories: situation, task, action and result as one chunk each."""
    chunks: list[Chunk] = []
    for story in profile.stories:
        parts = [story.title, story.situation, story.task, story.action, story.result]
        chunks.append(
            Chunk(
                id=f"story:{story.title}",
                kind="story",
                title=story.title,
                text=". ".join(p.strip().rstrip(".") for p in parts if p and p.strip()),
                local_only=True,
            )
        )
    return chunks


def chunks_for(profile: Profile, items: Sequence[LearningItem]) -> list[Chunk]:
    """Everything the index holds, in a stable order."""
    return [
        *learning_chunks(items),
        *project_chunks(profile),
        *experience_chunks(profile),
        *story_chunks(profile),
    ]
