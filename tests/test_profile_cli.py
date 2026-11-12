"""The demo vault, the ``profile`` CLI commands and the generated schema."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from jobomatic import bootstrap
from jobomatic.interfaces.cli import profile_cli
from jobomatic.interfaces.cli.main import main
from jobomatic.profile.adapters.yaml_vault import YamlVaultProfile
from jobomatic.profile.service import check, load_profile, presence_view

DEMO_PROFILE = Path(__file__).resolve().parents[1] / "demo-vault" / "profile"


def test_demo_vault_loads_and_has_no_issues() -> None:
    profile = load_profile(YamlVaultProfile(DEMO_PROFILE))
    assert check(profile) == []
    assert {r.tier for r in profile.roles} == {"resume", "legacy"}


def test_demo_vault_public_view_hides_private_data() -> None:
    profile = YamlVaultProfile(DEMO_PROFILE).load()
    text = presence_view(profile).model_dump_json()
    for secret in (profile.identity.email, profile.identity.phone, profile.identity.name):
        assert secret not in text
    assert "Northwind Traders" not in text  # the legacy employer
    assert "Lakeshore" not in text  # education is private
    assert "Meridian Benefits Group" in text  # a role inside the resume window


@pytest.fixture
def demo_in_tmp_vault(tmp_vault: Path) -> Path:
    shutil.copytree(DEMO_PROFILE, tmp_vault / "profile", dirs_exist_ok=True)
    return tmp_vault


def test_validate_command_succeeds_on_the_demo_profile(
    demo_in_tmp_vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["profile", "validate"]) == 0
    assert "Profile valid: 6 roles" in capsys.readouterr().out


def test_validate_command_fails_loudly_on_a_broken_profile(
    demo_in_tmp_vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (demo_in_tmp_vault / "profile" / "roles.yaml").unlink()
    assert main(["profile", "validate"]) == 1
    assert "roles.yaml: missing" in capsys.readouterr().out


def test_validate_command_reports_check_errors(
    demo_in_tmp_vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rules = demo_in_tmp_vault / "profile" / "rules.yaml"
    text = rules.read_text(encoding="utf-8")
    rules.write_text(text.replace("Full-Stack .NET", "Quilting"), encoding="utf-8")
    assert main(["profile", "validate"]) == 1
    assert "identity.headline" in capsys.readouterr().out


def test_validate_command_rejects_a_list_cut_at_a_comma_in_brackets(
    demo_in_tmp_vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projects = demo_in_tmp_vault / "profile" / "projects.yaml"
    text = projects.read_text(encoding="utf-8")
    first = next(line for line in text.splitlines() if line.startswith("  - "))
    projects.write_text(
        text.replace(first, "  - NgRx (store\n  - effects\n  - entity)", 1), encoding="utf-8"
    )
    assert main(["profile", "validate"]) == 1
    out = capsys.readouterr().out
    assert "[ERROR]" in out and "unbalanced brackets" in out and "'NgRx (store'" in out
    assert "Profile has 2 error(s)." in out


def test_bootstrap_reads_the_configured_vault(demo_in_tmp_vault: Path) -> None:
    assert bootstrap.profile_repository().load().identity.name == "Sarah Ashford"


def test_schema_command_prints_the_generated_json_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["profile", "schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert "Identity" in schema["$defs"]
    assert profile_cli.COMMAND == "profile"


# -- hand-written counts versus imported learning data ----------------------------------------


def _learning_items():
    from jobomatic.learning.model import Kind
    from tests.learning_fixtures import item

    azure = ["Microsoft Azure"]
    return [
        item("az-1", topics=azure),
        item("az-2", topics=azure),
        item("az-lab", topics=azure, kind=Kind.LAB),
        item("copilot-1", title="GitHub Copilot Basics", topics=["Generative AI"]),
        item("lead-1", topics=["Leadership & Soft Skills"]),
        item("other"),
    ]


def test_learning_drift_is_quiet_when_the_counts_match() -> None:
    from jobomatic.commands.profile import learning_drift
    from tests.profile_fixtures import sample_profile

    profile = sample_profile(coursework_summary="2 courses + 1 labs completed")
    profile.identity.differentiators = [
        "Pace of learning: 5 courses completed + 3 in progress + 1 labs (1 completed, 0 in progress) = 9",
        "GitHub Copilot: 1 courses",
        "Communication: 1 leadership/communication Pluralsight courses",
    ]
    assert learning_drift(profile, _learning_items()) == []


def test_learning_drift_names_each_count_that_no_longer_matches() -> None:
    from jobomatic.commands.profile import learning_drift
    from tests.profile_fixtures import sample_profile

    profile = sample_profile(coursework_summary="9 courses + 1 labs completed")
    profile.identity.differentiators = [
        "Pace of learning: 7 courses completed + 3 in progress + 1 labs (4 completed, 0 in progress) = 9",
    ]
    messages = learning_drift(profile, _learning_items())
    assert len(messages) == 3
    assert any("says 9 Azure courses" in m and "has 2" in m for m in messages)
    assert any("says 7 completed Pluralsight courses" in m and "has 5" in m for m in messages)
    assert any("says 4 completed Pluralsight labs" in m and "has 1" in m for m in messages)


def test_learning_drift_has_nothing_to_say_before_anything_is_imported() -> None:
    from jobomatic.commands.profile import learning_drift
    from tests.profile_fixtures import sample_profile

    assert learning_drift(sample_profile(coursework_summary="9 courses + 9 labs"), []) == []
