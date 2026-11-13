"""The web UI offers a named part of what the MCP server offers, and a new tool must be decided on
(ADR 0025).

The gate and the file policy are meant to hold for all three ways in. A page that quietly stopped
calling a command, or a tool added to the MCP server and never considered for the web UI, would let
the three drift apart. So every MCP tool is either mapped to a page of the web UI or named in
``NOT_IN_WEB``, and the pages are checked to call the commands those tools call.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("flask")

from jobomatic.interfaces.mcp import server  # noqa: E402
from jobomatic.interfaces.web.app import create_app  # noqa: E402

WEB = Path(__file__).resolve().parents[1] / "src" / "jobomatic" / "interfaces" / "web"

# The page (its URL) -> the MCP tools it is the screen for.
WEB_TOOLS = {
    "/fit": {"fit_check", "applications_check"},
    "/profile": {"validate_profile"},
    "/applications": {"applications_list", "applications_set_status", "applications_mark_applied"},
    "/pluralsight": {"learning_import"},
    "/documents": {"generate_resume", "generate_cover_letter", "generate_application_documents"},
}

# MCP tools with no page, on purpose. Out of the first version: editing or showing the private
# salary minimums, the evidence search, the profile summary, and the generators that write a draft
# for another surface or a letter. A new MCP tool fails the test until it is added to one side.
NOT_IN_WEB = {
    "search_constraints",
    "search_evidence",
    "profile_summary",
    "gap_analysis",
    "interview_prep",
    "generate_linkedin",
    "generate_github",
    "generate_jobgether",
    "generate_job_board",
    "generate_pluralsight",
    "generate_cold_call",
    "generate_job_site_letter",
    "generate_thank_you",
    "generate_learning_plan",
}

# The page's module -> the command modules it must call, which are the ones the tools call.
CALLS = {
    "fit_page.py": ("fit_check.run", "applications.check"),
    "profile_page.py": ("profile.validate",),
    "applications_page.py": (
        "applications.list_applications",
        "applications.set_status",
        "applications.applied",
    ),
    "pluralsight_page.py": ("learning_import.run",),
    "documents_page.py": ("resume.run", "cover_letter.run"),
}


def _mcp_tools() -> set[str]:
    return {tool.name for tool in asyncio.run(server.mcp.list_tools())}


def test_every_mcp_tool_is_mapped_or_named_as_not_in_the_web_ui() -> None:
    mapped = set().union(*WEB_TOOLS.values())
    tools = _mcp_tools()
    assert not tools - mapped - NOT_IN_WEB, (
        f"MCP tools with no decision: {sorted(tools - mapped - NOT_IN_WEB)}. "
        "Give each a page in WEB_TOOLS, or name it in NOT_IN_WEB."
    )


def test_nothing_is_listed_that_the_mcp_server_does_not_have() -> None:
    mapped = set().union(*WEB_TOOLS.values())
    tools = _mcp_tools()
    assert not mapped - tools, sorted(mapped - tools)
    assert not NOT_IN_WEB - tools, sorted(NOT_IN_WEB - tools)


def test_no_tool_is_both_mapped_and_excluded() -> None:
    assert not set().union(*WEB_TOOLS.values()) & NOT_IN_WEB


def test_every_mapped_page_exists_and_is_in_the_header() -> None:
    app = create_app(launch_token="t")
    urls = {rule.rule for rule in app.url_map.iter_rules()}
    linked = {app.url_map.bind("x").build(page.endpoint) for page in app.config["PAGES"]}
    for url in WEB_TOOLS:
        assert url in urls, url
        assert url in linked, f"{url} is not linked from the header"


def test_every_page_of_the_header_is_mapped_to_tools() -> None:
    app = create_app(launch_token="t")
    linked = {app.url_map.bind("x").build(page.endpoint) for page in app.config["PAGES"]}
    assert linked == set(WEB_TOOLS)


@pytest.mark.parametrize("module", sorted(CALLS))
def test_each_page_calls_the_commands_its_tools_call(module: str) -> None:
    source = (WEB / module).read_text(encoding="utf-8")
    for call in CALLS[module]:
        assert f"{call}(" in source, f"{module} does not call {call}"


def test_the_pages_that_write_call_commands_not_the_modules_underneath() -> None:
    """The gate lives in the commands. A page that reached past them would skip it."""
    for module in ("documents_page.py", "applications_page.py", "pluralsight_page.py"):
        source = (WEB / module).read_text(encoding="utf-8")
        for below in ("from jobomatic.documents", "from jobomatic.learning", "import docx"):
            assert below not in source, f"{module} reaches past the commands: {below}"
        assert "from jobomatic.gate" not in source or module == "documents_page.py"


def test_the_documents_page_uses_the_gates_own_names_for_the_overrides() -> None:
    from jobomatic import gate
    from jobomatic.interfaces.web.documents_page import OVERRIDES

    assert set(OVERRIDES) == {gate.CONFIRM_GAPS, gate.CONFIRM_REAPPLY, gate.CONFIRM_BELOW_MINIMUM}
