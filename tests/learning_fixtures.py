"""Fictional Pluralsight pages and Microsoft Learn transcripts for the learning tests."""

from __future__ import annotations

import datetime as dt
from typing import Any

from jobomatic.learning.model import Kind, LearningItem, Provider, SummarySource


def row(
    title: str,
    *,
    entry_type: str = "Course",
    duration: str = "1h 30m",
    percent: str = "100.0%",
    when: str | None = "08-15-2026",
    href: str | None = None,
) -> str:
    href = href or f"/library/courses/{title.lower().replace(' ', '-')}"
    date_cell = f'<time datetime="{when}">{when}</time>' if when else "-"
    return (
        '<tr role="row">'
        '<td role="gridcell"></td>'
        f'<td role="gridcell"><a href="{href}">{title}</a></td>'
        f'<td role="gridcell"><span>{entry_type}</span></td>'
        '<td role="gridcell"><time>1h 10m</time></td>'
        '<td role="gridcell">-</td>'
        f'<td role="gridcell">{duration}</td>'
        f'<td role="gridcell">{percent}</td>'
        f'<td role="gridcell">{date_cell}</td>'
        "</tr>"
    )


def page(rows: list[str]) -> str:
    filler = [row(f"Filler course {n}") for n in range(max(0, 10 - len(rows)))]
    return f"<html><body><table>{''.join(rows + filler)}</table></body></html>"


def item(
    slug: str,
    *,
    title: str | None = None,
    provider: Provider = Provider.PLURALSIGHT,
    kind: Kind = Kind.COURSE,
    minutes: int | None = 90,
    topics: list[str] | None = None,
    summary: str | None = None,
    summary_source: SummarySource | None = None,
    completed: dt.date | None = dt.date(2026, 8, 15),
) -> LearningItem:
    return LearningItem(
        id=f"{provider.value}:{slug}",
        provider=provider,
        kind=kind,
        title=title or slug.replace("-", " ").title(),
        url=f"https://example.com/{slug}",
        completed_on=completed,
        duration_minutes=minutes,
        topics=topics or [],
        summary=summary,
        summary_source=summary_source,
        source="test",
    )


def transcript(modules: int = 2, paths: int = 1, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "userName": "Sarah Ashford",
        "contactEmail": "sarah.ashford.dev@example.com",
        "totalModulesCompleted": modules,
        "totalLearningPathsCompleted": paths,
        "totalTrainingMinutes": 30 * modules,
        "modulesCompleted": [
            {
                "uid": f"learn.example.module-{n}",
                "title": f"Example module {n}",
                "description": "Learn how to&nbsp;do a thing  with   care.",
                "durationInMinutes": 30,
                "completedOn": "2026-04-20T17:15:35.4810887+00:00",
                "url": f"/training/modules/module-{n}/",
            }
            for n in range(modules)
        ],
        "learningPathsCompleted": [
            {
                "uid": f"learn.example.path-{n}",
                "title": f"Example path {n}",
                "description": "A path.",
                "durationInMinutes": 30 * modules,
                "completedOn": "2026-05-01T10:00:00+00:00",
            }
            for n in range(paths)
        ],
        "certificationData": {
            "activeCertifications": [
                {
                    "name": "Example Certified: Fundamentals",
                    "dateEarned": "2026-04-18T15:49:03+00:00",
                }
            ],
            "passedExams": [
                {
                    "examTitle": "Example Fundamentals",
                    "examNumber": "EX-100",
                    "examDateTaken": "2026-04-18T15:49:03+00:00",
                }
            ],
        },
        "appliedSkillsData": {
            "appliedSkillsCredentials": [
                {"title": "Applied Skills: Do the thing", "awardedOn": "2026-04-20T17:57:33+00:00"}
            ]
        },
    }
    data.update(extra)
    return data
