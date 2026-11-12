"""The gap analysis and the five profile-update generators as commands that return results."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from jobomatic import paths
from jobomatic.commands import gap_analysis
from jobomatic.presence import github, job_board, jobgether, linkedin, pluralsight
from jobomatic.presence.draft import DraftData
from tests.command_cases import STRONG

POSTING = STRONG.read_text(encoding="utf-8")

GENERATORS = [
    pytest.param(linkedin, "linkedin", id="linkedin"),
    pytest.param(github, "github", id="github"),
    pytest.param(jobgether, "jobgether", id="jobgether"),
    pytest.param(job_board, "job-board", id="job-board"),
    pytest.param(pluralsight, "pluralsight", id="pluralsight"),
]


@pytest.mark.parametrize("module, platform", GENERATORS)
def test_a_generator_returns_the_draft_and_what_it_wrote(
    module, platform: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "draft.md"
    result = module.run(out)
    assert result.status == "ok"
    assert isinstance(result.data, DraftData)
    assert (result.data.platform, result.data.draft) == (platform, out)
    assert out in result.written
    assert Path(f"{out}.meta.json") in result.written
    assert all(path.exists() for path in result.written)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("module, platform", GENERATORS)
def test_a_generator_defaults_to_the_vaults_profile_folder(module, platform: str) -> None:
    result = module.run()
    expected = paths.output_dir("profiles", platform=platform) / f"{date.today().isoformat()}.md"
    assert result.data is not None and result.data.draft == expected


def test_linkedin_writes_its_raw_inputs_first(tmp_path: Path) -> None:
    out = tmp_path / "li.md"
    written = linkedin.run(out).written
    assert [p.name for p in written] == ["li.raw-inputs.json", "li.md", "li.md.meta.json"]


def test_a_raw_inputs_file_that_cannot_be_written_is_a_warning_not_a_failure(
    tmp_path: Path,
) -> None:
    out = tmp_path / "li.md"
    (tmp_path / "li.raw-inputs.json").mkdir()  # a folder where the file would go
    result = linkedin.run(out)
    assert result.status == "ok"
    assert [m.level for m in result.messages] == ["warning"]
    assert "could not write raw inputs file" in result.messages[0].text
    assert [p.name for p in result.written] == ["li.md", "li.md.meta.json"]


@pytest.mark.parametrize("module, platform", GENERATORS)
def test_a_missing_skill_file_is_an_error_result(
    module, platform: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(module, "SKILL_PATH", tmp_path / "nope" / "SKILL.md")
    result = module.run(tmp_path / "x.md")
    assert result.status == "error"
    assert result.messages[0].text.startswith("SKILL.md not found:")


@pytest.mark.parametrize("module, platform", GENERATORS)
def test_a_broken_profile_is_an_error_result_not_a_traceback(
    module, platform: str, tmp_vault: Path, tmp_path: Path
) -> None:
    result = module.run(tmp_path / "x.md")
    assert result.status == "error" and result.written == ()


def test_an_output_folder_that_cannot_be_made_is_an_error_result(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder", encoding="utf-8")
    result = pluralsight.run(blocker / "inside" / "x.md")
    assert result.status == "error"
    assert result.messages[0].text.startswith("cannot create output directory")


# -- gap analysis ------------------------------------------------------------------------------


def test_the_gap_analysis_returns_the_rating_and_the_report_it_wrote(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "gap.md"
    result = gap_analysis.run(POSTING, out)
    assert result.status == "ok"
    assert result.data is not None and result.data.fit.rating == "Strong"
    assert result.written == (out,)
    assert out.read_text(encoding="utf-8").startswith("# Gap Analysis:")
    assert capsys.readouterr() == ("", "")


def test_the_gap_analysis_defaults_to_the_postings_own_folder() -> None:
    result = gap_analysis.run(POSTING)
    (report,) = result.written
    assert report.name == "gap-analysis.md"
    assert report.parent.parent == paths.outputs_dir() / "applications"


def test_a_report_that_cannot_be_written_is_an_error_result(tmp_path: Path) -> None:
    out = tmp_path / "gap.md"
    out.mkdir()  # a folder where the report would go
    result = gap_analysis.run(POSTING, out)
    assert result.status == "error"
    assert result.messages[-1].text.startswith(f"failed to write {out}")
