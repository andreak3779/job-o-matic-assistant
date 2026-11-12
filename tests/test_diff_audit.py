"""jobomatic.privacy.diff_audit: personal identifiers in the lines a push would publish (ADR 0032).

Fictional values only: this file is tracked.
"""

from __future__ import annotations

from jobomatic.privacy.diff_audit import (
    AddedLine,
    PushedUpdate,
    added_lines,
    audit_added_lines,
    commit_texts,
    pushed_updates,
)

TERMS = {
    "names": ["Jordan Example", "Sam"],
    "emails": ["jordan@example.com"],
    "phones": ["204-555-0100"],
    "employers": ["Acme Widgets"],
    "identifiers": ["share0123abc"],
}

DIFF = """\
diff --git a/docs/a.md b/docs/a.md
index 111..222 100644
--- a/docs/a.md
+++ b/docs/a.md
@@ -3,0 +4,2 @@ context
+first added
+second added
@@ -10 +12 @@
-old
+replaced
diff --git a/gone.txt b/gone.txt
deleted file mode 100644
--- a/gone.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-x
-y
diff --git a/new file.txt b/new file.txt
new file mode 100644
--- /dev/null
+++ b/new file.txt
@@ -0,0 +1,2 @@
+one
+two
diff --git a/pic.png b/pic.png
Binary files a/pic.png and b/pic.png differ
"""


def test_added_lines_carry_the_line_number_in_the_new_file() -> None:
    assert added_lines(DIFF) == [
        AddedLine("docs/a.md", 4, "first added"),
        AddedLine("docs/a.md", 5, "second added"),
        AddedLine("docs/a.md", 12, "replaced"),
        AddedLine("new file.txt", 1, "one"),
        AddedLine("new file.txt", 2, "two"),
    ]


def test_a_deleted_file_and_a_binary_file_add_nothing() -> None:
    assert [a for a in added_lines(DIFF) if a.path in ("gone.txt", "pic.png")] == []


def test_a_path_git_had_to_quote_is_unquoted() -> None:
    diff = '+++ b/"caf\\303\\251.md"\n@@ -0,0 +1 @@\n+x\n'
    assert added_lines(diff)[0].path == "caf\\303\\251.md"


def _lines(*texts: str) -> list[AddedLine]:
    return [AddedLine("f.md", n, t) for n, t in enumerate(texts, start=1)]


def test_every_category_is_found_and_only_path_and_line_are_reported() -> None:
    added = _lines(
        "by Jordan Example",
        "mail jordan@example.com",
        "call (204) 555-0100",
        "worked at Acme Widgets",
        "?id=share0123abc",
        "nothing here",
    )
    assert audit_added_lines(TERMS, added) == [
        "f.md:1 (names)",
        "f.md:2 (emails)",
        "f.md:3 (phones)",
        "f.md:4 (employers)",
        "f.md:5 (identifiers)",
    ]


def test_every_term_is_matched_without_regard_to_case_unlike_the_commit_scan() -> None:
    # The commit-time scan matches employers and identifiers case-sensitively.
    added = _lines("ACME WIDGETS", "acme widgets", "SHARE0123ABC")
    assert [f.split(" ")[1] for f in audit_added_lines(TERMS, added)] == [
        "(employers)",
        "(employers)",
        "(identifiers)",
    ]


def test_a_long_term_is_found_inside_a_longer_word_a_short_one_is_not() -> None:
    assert audit_added_lines(TERMS, _lines("xAcme Widgetsx")) == ["f.md:1 (employers)"]
    assert audit_added_lines(TERMS, _lines("Samuel and Examples")) == []
    assert audit_added_lines(TERMS, _lines("said Sam.")) == ["f.md:1 (names)"]


def test_a_term_that_ends_in_a_symbol_still_matches_when_short() -> None:
    assert (
        audit_added_lines({"employers": ["C#"], "names": ["Joe"]}, _lines("I like C# a lot")) == []
    )
    assert audit_added_lines({"employers": ["Ab#"]}, _lines("an Ab# thing")) == [
        "f.md:1 (employers)"
    ]


def test_a_phone_matches_any_separator_style() -> None:
    for text in ("204-555-0100", "204.555.0100", "(204) 555-0100", "2045550100"):
        assert audit_added_lines(TERMS, _lines(text)) == ["f.md:1 (phones)"], text


def test_allowlisted_paths_are_skipped() -> None:
    added = [AddedLine("old.md", 1, "Jordan Example"), AddedLine("new.md", 1, "Jordan Example")]
    assert audit_added_lines(TERMS, added, allow={"old.md"}) == ["new.md:1 (names)"]


def test_findings_never_contain_the_matching_text() -> None:
    for finding in audit_added_lines(
        TERMS, _lines("Jordan Example jordan@example.com Acme Widgets")
    ):
        assert "jordan" not in finding.lower() and "acme" not in finding.lower()


def test_short_and_empty_terms_are_ignored() -> None:
    assert audit_added_lines({"names": ["ab", "", "  "]}, _lines("ab ab ab")) == []


# -- what git sends to a pre-push hook ---------------------------------------------------------

LOCAL = "a" * 40
REMOTE = "b" * 40
NULL = "0" * 40


def test_an_update_has_both_commits() -> None:
    line = f"refs/heads/feat {LOCAL} refs/heads/feat {REMOTE}"
    assert pushed_updates([line]) == [PushedUpdate("refs/heads/feat", LOCAL, REMOTE)]


def test_a_branch_new_to_the_remote_has_no_remote_commit() -> None:
    line = f"refs/heads/feat {LOCAL} refs/heads/feat {NULL}"
    assert pushed_updates([line]) == [PushedUpdate("refs/heads/feat", LOCAL, None)]


def test_a_deletion_publishes_nothing() -> None:
    assert pushed_updates([f"(delete) {NULL} refs/heads/feat {REMOTE}"]) == []


def test_a_tag_and_a_branch_in_one_push_are_both_kept() -> None:
    lines = [
        f"refs/tags/v1 {LOCAL} refs/tags/v1 {NULL}\n",
        f"refs/heads/main {LOCAL} refs/heads/main {REMOTE}\n",
    ]
    assert [u.ref for u in pushed_updates(lines)] == ["refs/tags/v1", "refs/heads/main"]


def test_blank_and_malformed_lines_are_ignored() -> None:
    assert pushed_updates(["", "\n", "garbage", "a b c"]) == []


def test_a_sha256_repository_null_sha_is_recognised() -> None:
    null = "0" * 64
    line = f"refs/heads/feat {'c' * 64} refs/heads/feat {null}"
    assert pushed_updates([line])[0].remote_sha is None
    assert pushed_updates([f"(delete) {null} refs/heads/feat {'c' * 64}"]) == []


# -- what a commit publishes besides its patch -------------------------------------------------

LOG = (
    "\x1e" + "a" * 40 + "\nAndrea Q <noreply@example.com>\nAndrea Q <noreply@example.com>\n"
    "Subject line\n\nBody mentions Jordan Example\n"
    "\x1e" + "b" * 40 + "\nSomeone <jordan@example.com>\nSomeone <noreply@example.com>\nOther\n"
)


def test_commit_texts_number_author_committer_then_message() -> None:
    items = commit_texts(LOG)
    first = [i for i in items if i.path == "commit " + "a" * 10]
    assert [(i.number, i.text) for i in first][:3] == [
        (1, "Andrea Q <noreply@example.com>"),
        (2, "Andrea Q <noreply@example.com>"),
        (3, "Subject line"),
    ]
    assert {i.path for i in items} == {"commit " + "a" * 10, "commit " + "b" * 10}


def test_a_private_value_in_a_message_or_an_author_is_found() -> None:
    assert audit_added_lines(TERMS, commit_texts(LOG)) == [
        "commit " + "a" * 10 + ":5 (names)",
        "commit " + "b" * 10 + ":1 (emails)",
    ]


def test_commit_texts_of_nothing_is_nothing() -> None:
    assert commit_texts("") == []
