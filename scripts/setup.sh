#!/usr/bin/env bash
# One-command setup for job-o-matic on Debian, Ubuntu and systems built on them.
#
#   bash scripts/setup.sh                 # install, then try the demo vault
#   bash scripts/setup.sh --help          # every option
#
# What it does: checks Python, builds .venv, installs the packages, checks the install and runs a
# short demo. What it never does: run sudo, add a package source, create a GitHub repository or
# push anything. When something is missing it prints the command for you to run.
#
# Safe to run again. The steps and the reasons for them are in docs/setup.md (ADR 0026).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START_DIR="$PWD"
cd "$ROOT" || exit 1
# shellcheck source=scripts/lib/setup-common.sh
. "$ROOT/scripts/lib/setup-common.sh"

usage() {
    cat <<'EOF'
Usage: bash scripts/setup.sh [options]

  --no-dev           skip the test and lint tools (a smaller install)
  --hooks            turn on the git commit hook (only for people changing the code)
  --recreate         delete .venv and build it again (use after upgrading Python)
  --python PATH      use this Python, which must be 3.11 or newer (for example python3.12)
  --vault-url URL    clone your private vault next to this folder (a second laptop)
  --new-vault        start a new vault, ../job-o-matic-vault, from the fictional demo vault
  -h, --help         show this help

With no options it installs everything and runs the demo. It is safe to run again.
EOF
}

usage_error() {
    printf 'setup.sh: %s\n' "$1" >&2
    printf 'Run "bash scripts/setup.sh --help" for the options.\n' >&2
    exit 2
}

WITH_DEV=1
DO_HOOKS=0
RECREATE=0
PYTHON_ARG=""
VAULT_URL=""
NEW_VAULT=0

while [ $# -gt 0 ]; do
    case "$1" in
        --no-dev) WITH_DEV=0 ;;
        --hooks) DO_HOOKS=1 ;;
        --recreate) RECREATE=1 ;;
        --python)
            [ $# -ge 2 ] || usage_error "--python needs a path, for example --python python3.12"
            PYTHON_ARG="$2"
            shift
            ;;
        --vault-url)
            [ $# -ge 2 ] || usage_error "--vault-url needs the address of your vault repository"
            VAULT_URL="$2"
            shift
            ;;
        --new-vault) NEW_VAULT=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        *) usage_error "unknown option: $1" ;;
    esac
    shift
done

if [ -n "$VAULT_URL" ] && [ "$NEW_VAULT" = 1 ]; then
    usage_error "use either --vault-url or --new-vault, not both"
fi

TOTAL=5
[ "$DO_HOOKS" = 1 ] && TOTAL=$((TOTAL + 1))
{ [ -n "$VAULT_URL" ] || [ "$NEW_VAULT" = 1 ]; } && TOTAL=$((TOTAL + 1))
STEP=0
LOG="$(mktemp "${TMPDIR:-/tmp}/jobomatic-setup.XXXXXX")"
trap 'rm -f "$LOG"' EXIT

step() {
    STEP=$((STEP + 1))
    heading "[$STEP/$TOTAL] $*"
}

# Print a failure with the lines that say what to do, then stop.
stop() {
    fail "$1"
    shift
    local text
    for text in "$@"; do line "$text"; done
    printf '\n%sSetup stopped.%s Fix the problem above and run this script again.\n' \
        "$C_RED" "$C_RESET"
    exit 1
}

say "job-o-matic setup"
say "$NOTICE_SHORT"
say "Folder: $ROOT"

# Run as root, the virtual environment would belong to root and your own account could not use it.
if [ "$(id -u)" = "0" ]; then
    stop "This script was run as root (with sudo)." \
        "Run it as your normal user:  bash scripts/setup.sh" \
        "It never needs sudo. If it needs a package, it prints the command for you to run."
fi

# ── 1. The system ────────────────────────────────────────────────────────────
step "Checking this computer"
detect_distro
if [ "$DISTRO_FAMILY" = "debian" ]; then
    ok "$DISTRO_NAME, in the Debian/Ubuntu family"
else
    warn "$DISTRO_NAME is not in the Debian/Ubuntu family. This is tested only there."
    line "Going on; where a command below says 'apt', use your own package manager."
fi

[ -f "$ROOT/pyproject.toml" ] || stop "pyproject.toml is not in $ROOT." \
    "Run this from a full clone of the repository (git clone ...)."

if [ -n "$PYTHON_ARG" ]; then
    PYBIN="$(find_python "$PYTHON_ARG")" || PYBIN=""
    [ -n "$PYBIN" ] || stop "'$PYTHON_ARG' is not Python 3.11 or newer, or does not run." \
        "Check it with:  $PYTHON_ARG --version"
else
    PYBIN="$(find_python python3 python3.12 python3.13 python3.11 python3.14)" || PYBIN=""
    if [ -z "$PYBIN" ]; then
        found=""
        command -v python3 >/dev/null 2>&1 && found="$(python_version python3)"
        if [ -n "$found" ]; then
            fail "Python $found is too old. job-o-matic needs 3.11 or newer."
        else
            fail "Python 3 was not found."
            line "Install it with:  $(install_hint python3 python3-venv)"
        fi
        python_upgrade_advice
        printf '\n%sSetup stopped.%s\n' "$C_RED" "$C_RESET"
        exit 1
    fi
fi
PYVER="$(python_version "$PYBIN")"
ok "Python $PYVER ($PYBIN)"

avail_kb="$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2 {print $4}')"
if [ -n "$avail_kb" ] && [ "$avail_kb" -lt 512000 ] 2>/dev/null; then
    warn "Only $((avail_kb / 1024)) MB free here. The install needs about 250 MB."
fi

# ── 2. The virtual environment ───────────────────────────────────────────────
step "Creating the virtual environment (.venv)"
VENV="$ROOT/.venv"

# Never delete a folder that is not a virtual environment.
require_venv_dir() {
    [ -f "$VENV/pyvenv.cfg" ] ||
        stop ".venv exists but is not a virtual environment, so it was left alone." \
            "Move or delete it yourself, then run this script again."
}

if [ "$RECREATE" = 1 ] && [ -e "$VENV" ]; then
    require_venv_dir
    rm -rf "$VENV"
    info "removed the old .venv, as asked (--recreate)"
fi

if [ -x "$VENV/bin/python" ] && python_ok "$VENV/bin/python"; then
    ok "reusing the existing .venv (Python $(python_version "$VENV/bin/python"))"
else
    if [ -e "$VENV" ]; then
        require_venv_dir
        warn ".venv exists but does not work (this often follows a Python upgrade). Rebuilding it."
        rm -rf "$VENV"
    fi
    if ! "$PYBIN" -m venv "$VENV" >"$LOG" 2>&1; then
        rm -rf "$VENV"
        base="$(basename "$PYBIN")"
        case "$base" in
            python3.[0-9]*) venv_pkg="${base}-venv" ;;
            *) venv_pkg="python3-venv" ;;
        esac
        tail -n 4 "$LOG" | while IFS= read -r text; do line "$text"; done
        stop "Could not create the virtual environment." \
            "The venv module is a separate package on Debian and Ubuntu. Install it with:" \
            "    $(install_hint "$venv_pkg")" \
            "then run this script again."
    fi
    ok "created .venv"
fi

# ── 3. The packages ──────────────────────────────────────────────────────────
step "Installing the packages"
EXTRAS="mcp,parser,pdf"
[ "$WITH_DEV" = 1 ] && EXTRAS="$EXTRAS,dev,lint"
info "This downloads about 250 MB, needs the internet and usually takes a minute or two."
PIP="$VENV/bin/pip"
if "$PIP" install --disable-pip-version-check -q -c requirements-lock.txt -e ".[$EXTRAS]" \
    >"$LOG" 2>&1; then
    ok "installed with the versions the tests use (requirements-lock.txt)"
else
    warn "The install with the tested versions failed. Trying again without the lock file."
    tail -n 4 "$LOG" | while IFS= read -r text; do line "$text"; done
    if "$PIP" install --disable-pip-version-check -q -e ".[$EXTRAS]" >"$LOG" 2>&1; then
        warn "installed, but with newer versions than the tests use. Report anything that breaks."
    else
        tail -n 12 "$LOG" | while IFS= read -r text; do line "$text"; done
        stop "The install failed." \
            "Check that you are online. If the message above mentions a package with no" \
            "version for Python $PYVER, try an older Python:  --python python3.12 --recreate"
    fi
fi

# ── 4. Check the install ─────────────────────────────────────────────────────
step "Checking the install"
if "$VENV/bin/python" -c 'import docx, bs4, yaml, jsonschema, reportlab, mcp, jobomatic' \
    >"$LOG" 2>&1 && [ -x "$VENV/bin/jobo" ]; then
    ok "every package imports, and the jobo command exists"
else
    tail -n 6 "$LOG" | while IFS= read -r text; do line "$text"; done
    stop "The install finished but a package does not load." \
        "Try:  bash scripts/setup.sh --recreate"
fi

# ── 5. The demo ──────────────────────────────────────────────────────────────
step "Trying the demo vault (a fictional candidate, no personal data)"
demo() {
    env -u CLAUDE_JOBS_PRIVATE_DIR -u CLAUDE_JOBS_APPLICATIONS_LOG \
        JOBOMATIC_VAULT="$ROOT/demo-vault" "$VENV/bin/jobo" "$@"
}

out="$(demo profile validate 2>&1)"
rc=$?
if [ "$rc" = 0 ]; then
    ok "jobo profile validate"
    case "$out" in
        *"[WARNING]"*) info "A few [WARNING] lines are normal here; they are about the fictional text." ;;
    esac
else
    printf '%s\n' "$out" | tail -n 6 | while IFS= read -r text; do line "$text"; done
    stop "jobo profile validate failed on the demo vault."
fi

out="$(demo fit-check tests/fixtures/strong-fit-jd.md 2>&1)"
case "$out" in
    *"Fit Rating: Strong"*) ok "jobo fit-check gives Strong for a matching posting" ;;
    *)
        printf '%s\n' "$out" | tail -n 6 | while IFS= read -r text; do line "$text"; done
        stop "jobo fit-check did not give the expected rating."
        ;;
esac

out="$(demo generate-resume tests/fixtures/data-engineer-jd.md 2>&1)"
rc=$?
if [ "$rc" = 2 ] && [[ "$out" == *"REFUSED"* ]]; then
    ok "jobo generate-resume refuses a posting that does not match (exit 2). That is the tool working."
else
    printf '%s\n' "$out" | tail -n 6 | while IFS= read -r text; do line "$text"; done
    stop "jobo generate-resume should have been refused (exit 2) but returned $rc."
fi

# ── Optional: the commit hook ────────────────────────────────────────────────
if [ "$DO_HOOKS" = 1 ]; then
    step "Turning on the git commit hook"
    if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        if bash "$ROOT/scripts/install-hooks.sh" >"$LOG" 2>&1; then
            ok "hook on. It checks every commit, and takes about a minute."
        else
            tail -n 4 "$LOG" | while IFS= read -r text; do line "$text"; done
            warn "Could not turn the hook on."
        fi
    else
        warn "This folder is not a git clone (was it downloaded as a zip?), so there is nothing to hook."
    fi
fi

# ── Optional: a vault ────────────────────────────────────────────────────────
VAULT_DIR="$(dirname "$ROOT")/job-o-matic-vault"
if [ -n "$VAULT_URL" ]; then
    step "Cloning your vault"
    command -v git >/dev/null 2>&1 ||
        stop "git is not installed." "Install it with:  $(install_hint git)"
    if [ -e "$VAULT_DIR" ]; then
        ok "$VAULT_DIR already exists, so it was left alone"
    elif git clone -q "$VAULT_URL" "$VAULT_DIR" >"$LOG" 2>&1; then
        ok "cloned to $VAULT_DIR"
    else
        tail -n 4 "$LOG" | while IFS= read -r text; do line "$text"; done
        stop "Could not clone $VAULT_URL" \
            "A private repository needs you to be signed in. Install the GitHub tool with:" \
            "    $(install_hint gh)" \
            "then run:  gh auth login   and run this script again."
    fi
    [ -f "$VAULT_DIR/.jobomatic.toml" ] ||
        warn "$VAULT_DIR has no .jobomatic.toml, so it is not recognised as a vault."
fi

if [ "$NEW_VAULT" = 1 ]; then
    step "Starting a new vault from the demo vault"
    command -v git >/dev/null 2>&1 ||
        stop "git is not installed." "Install it with:  $(install_hint git)"
    [ ! -e "$VAULT_DIR" ] || stop "$VAULT_DIR already exists, so nothing was copied." \
        "Pick another place, or move that folder away first."
    if [ -z "$(git config --global user.name 2>/dev/null)" ] ||
        [ -z "$(git config --global user.email 2>/dev/null)" ]; then
        stop "git does not know who you are yet, so it cannot make the first commit." \
            "Run these two lines with your own details, then run this script again:" \
            '    git config --global user.name  "Your Name"' \
            '    git config --global user.email "you@example.com"' \
            "(GitHub shows a private 'noreply' address under Settings, Emails. Use that one" \
            "if you do not want your real address in your commits.)"
    fi
    cp -r "$ROOT/demo-vault" "$VAULT_DIR" || stop "Could not copy the demo vault."
    {
        git -C "$VAULT_DIR" init -q -b main &&
            git -C "$VAULT_DIR" add -A &&
            git -C "$VAULT_DIR" commit -q -m "Start my vault from the demo vault"
    } >"$LOG" 2>&1 || {
        tail -n 4 "$LOG" | while IFS= read -r text; do line "$text"; done
        stop "Copied the demo vault but could not start a git repository in it."
    }
    ok "created $VAULT_DIR (a git repository on this computer only)"
    warn "It still holds the FICTIONAL candidate. Replace it with your own details before use."
    line "Keep it private. When you want a copy on GitHub, run this yourself:"
    line "    cd \"$VAULT_DIR\" && gh repo create job-o-matic-vault --private --source=. --push"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
printf '\n%sDone.%s job-o-matic is installed. %s warning(s).\n' "$C_GREEN" "$C_RESET" "$N_WARN"
say ""
say "Next, to try the demo:"
say "    cd \"$ROOT\""
say "    source .venv/bin/activate"
say "    export JOBOMATIC_VAULT=\"\$PWD/demo-vault\""
say "    jobo fit-check tests/fixtures/strong-fit-jd.md"
say ""
say "Every NEW terminal needs the 'source' line again, and the 'export' line if you use the demo."
say "Check your setup any time:  bash scripts/check-setup.sh"
say "Full guide:  docs/setup.md"
if [ "$START_DIR" != "$ROOT" ]; then
    say ""
    say "(You ran this from $START_DIR. The examples above start with cd to the right folder.)"
fi
exit 0
