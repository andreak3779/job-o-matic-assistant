#!/usr/bin/env bash
# A read-only health check for a job-o-matic setup. It changes nothing; run it as often as you like.
#
#   bash scripts/check-setup.sh
#
# Each line starts with OK, WARN, FAIL or info:
#   OK    working
#   WARN  works, but you probably want to fix it
#   FAIL  broken; fix the first FAIL and run this again
#   info  optional, and only said so you know
#
# The exit status is 1 if anything FAILed, otherwise 0. See docs/setup.md (ADR 0026).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START_DIR="$PWD"
cd "$ROOT" || exit 1
# shellcheck source=scripts/lib/setup-common.sh
. "$ROOT/scripts/lib/setup-common.sh"

case "${1:-}" in
    -h | --help)
        sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
    "") ;;
    *)
        printf 'check-setup.sh: unknown option: %s\n' "$1" >&2
        exit 2
        ;;
esac

VENV="$ROOT/.venv"
PY="$VENV/bin/python"

say "job-o-matic setup check"
say "$NOTICE_SHORT"
say "Folder: $ROOT"

# ── This computer ────────────────────────────────────────────────────────────
heading "This computer"
detect_distro
if [ "$DISTRO_FAMILY" = "debian" ]; then
    ok "$DISTRO_NAME, in the Debian/Ubuntu family"
else
    warn "$DISTRO_NAME is not in the Debian/Ubuntu family. This is tested only there."
fi

if command -v python3 >/dev/null 2>&1; then
    sys_ver="$(python_version python3)"
    if python_ok python3; then
        ok "system python3 is $sys_ver"
    else
        info "system python3 is $sys_ver, older than 3.11. Fine if .venv uses a newer Python."
    fi
else
    warn "python3 was not found. Install it with:  $(install_hint python3 python3-venv)"
fi
if command -v git >/dev/null 2>&1; then
    ok "git is installed"
else
    warn "git is not installed. Install it with:  $(install_hint git)"
fi

# ── The install ──────────────────────────────────────────────────────────────
heading "The install"
if [ ! -x "$PY" ]; then
    fail "There is no .venv here. Run:  bash scripts/setup.sh"
elif ! python_ok "$PY"; then
    fail ".venv uses Python $(python_version "$PY"), which is too old or broken. Run:  bash scripts/setup.sh --recreate"
else
    ok ".venv uses Python $(python_version "$PY")"
    if "$PY" -c 'import docx, bs4, yaml, jsonschema, reportlab, jobomatic' >/dev/null 2>&1; then
        ok "the packages load"
    else
        fail "a package does not load. Run:  bash scripts/setup.sh"
    fi
    if "$PY" -c 'import mcp' >/dev/null 2>&1; then
        ok "the MCP package is installed"
    else
        info "the MCP package is not installed (only needed for Claude Code or Desktop)"
    fi
fi

on_path="$(command -v jobo 2>/dev/null || true)"
if [ -z "$on_path" ]; then
    warn "'jobo' is not on your PATH in this terminal."
    line "Run:  cd \"$ROOT\" && source .venv/bin/activate"
    line "(This is needed in every new terminal. Or run .venv/bin/jobo directly.)"
elif [ "$on_path" != "$VENV/bin/jobo" ]; then
    warn "'jobo' on your PATH is $on_path, not this folder's."
    line "Run:  cd \"$ROOT\" && source .venv/bin/activate"
else
    ok "'jobo' is on your PATH and belongs to this folder"
fi

if [ "$START_DIR" != "$ROOT" ]; then
    warn "You ran this from $START_DIR."
    line "The examples in the docs assume the repository folder:  cd \"$ROOT\""
fi

# ── Your vault ───────────────────────────────────────────────────────────────
heading "Your vault (the private folder with your profile)"
vault=""
if [ -x "$PY" ]; then
    vault="$("$PY" - 2>"${TMPDIR:-/tmp}/jobomatic-check.$$" <<'PYEOF'
import sys
from jobomatic import paths

try:
    print(paths.vault_root())
except paths.VaultError as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)
PYEOF
    )"
    vault_err="$(cat "${TMPDIR:-/tmp}/jobomatic-check.$$" 2>/dev/null)"
    rm -f "${TMPDIR:-/tmp}/jobomatic-check.$$"
fi

if [ -z "$vault" ]; then
    if [ -x "$PY" ]; then
        fail "No vault is set up."
        [ -n "${vault_err:-}" ] && line "${vault_err}"
    else
        fail "Cannot look for a vault until the install works."
    fi
    line "To try the demo:  export JOBOMATIC_VAULT=\"$ROOT/demo-vault\""
    line "For your own data: see docs/setup.md, Part 2."
else
    if [ -n "${JOBOMATIC_VAULT:-}" ]; then
        source_of="the JOBOMATIC_VAULT setting"
    elif [ -f "${JOBOMATIC_CONFIG:-$HOME/.config/job-o-matic/config.toml}" ]; then
        source_of="the config file"
    else
        source_of="the job-o-matic-vault folder next to this one"
    fi
    if [ "$vault" = "$ROOT/demo-vault" ]; then
        ok "using the demo vault (a fictional candidate). Fine for trying it out."
        line "found through $source_of"
        info "To generate documents with it, use a copy so this folder stays clean:"
        line "    cp -r demo-vault ~/job-o-matic-demo && export JOBOMATIC_VAULT=\"\$HOME/job-o-matic-demo\""
    else
        ok "using $vault"
        line "found through $source_of"
        if cmp -s "$vault/profile/identity.yaml" "$ROOT/demo-vault/profile/identity.yaml" 2>/dev/null; then
            warn "This vault still holds the FICTIONAL demo candidate."
            line "Replace the files in $vault/profile with your own details before generating anything."
        fi
        case "$vault" in
            "$ROOT"/*)
                warn "This vault is inside the code folder. Personal data belongs in its own private folder."
                ;;
        esac
        if [ -f "$vault/private/search-constraints.json" ]; then
            ok "salary minimums are set (private/search-constraints.json)"
        else
            info "no private/search-constraints.json, so the salary screen is off (optional)"
        fi
    fi
    if [ -x "$VENV/bin/jobo" ]; then
        out="$(env -u CLAUDE_JOBS_PRIVATE_DIR -u CLAUDE_JOBS_APPLICATIONS_LOG \
            "$VENV/bin/jobo" profile validate 2>&1)"
        rc=$?
        summary="$(printf '%s\n' "$out" | tail -n 1)"
        if [ "$rc" = 0 ]; then
            ok "profile validate: ${summary#\[OK\] }"
        else
            fail "profile validate found errors:"
            printf '%s\n' "$out" | grep -v '^\[WARNING\]' | tail -n 8 | while IFS= read -r text; do line "$text"; done
        fi
    fi
fi

# ── Optional extras ──────────────────────────────────────────────────────────
heading "Optional extras (none of these are needed to start)"
if command -v pdfinfo >/dev/null 2>&1; then
    ok "pdfinfo is installed (page counts with --check-pages)"
else
    info "pdfinfo is not installed (needed for --check-pages):  $(install_hint poppler-utils)"
fi
if command -v dpkg >/dev/null 2>&1 && dpkg -s libreoffice-writer >/dev/null 2>&1; then
    ok "LibreOffice Writer is installed (page counts with --check-pages)"
elif command -v flatpak >/dev/null 2>&1 && flatpak info org.libreoffice.LibreOffice >/dev/null 2>&1; then
    ok "LibreOffice is installed as a Flatpak (set JOBOMATIC_LIBREOFFICE=flatpak for --check-pages)"
else
    info "LibreOffice Writer is not installed (needed for --check-pages):  $(install_hint libreoffice-writer)"
fi
if command -v ollama >/dev/null 2>&1; then
    ok "ollama is installed (evidence search)"
else
    info "ollama is not installed (only for 'jobo evidence'; 'jobo search --keyword-only' works without it)"
fi
if [ -x "$VENV/bin/python3" ]; then
    ok ".mcp.json can start the MCP server (.venv/bin/python3 exists). Open Claude Code from this folder."
else
    info ".mcp.json points at .venv/bin/python3, which does not exist yet (Claude Code only)"
fi

# ── For people changing the code ─────────────────────────────────────────────
heading "Only if you change the code"
if [ "$(git -C "$ROOT" config core.hooksPath 2>/dev/null)" = "scripts/hooks" ]; then
    info "the commit hook is on (it checks every commit and takes about a minute)"
else
    info "the commit hook is off. Turn it on with:  bash scripts/install-hooks.sh"
fi

# ── Result ───────────────────────────────────────────────────────────────────
heading "Result"
printf '  %s OK, %s warning(s), %s failure(s)\n' "$N_OK" "$N_WARN" "$N_FAIL"
if [ "$N_FAIL" -gt 0 ]; then
    printf '  %sFix the first FAIL above, then run this again.%s\n' "$C_RED" "$C_RESET"
    exit 1
elif [ "$N_WARN" -gt 0 ]; then
    printf '  Working. Look at the WARN lines when you have a moment.\n'
else
    printf '  %sEverything checks out.%s\n' "$C_GREEN" "$C_RESET"
fi
exit 0
