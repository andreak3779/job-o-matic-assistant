# shellcheck shell=bash
# shellcheck disable=SC1090,SC2034
# (SC2034: the variables set here are read by the scripts that source this file.
#  SC1090: detect_distro sources an os-release file whose path is only known at run time.)
# Shared by scripts/setup.sh and scripts/check-setup.sh. Sourced, never run on its own.
# It only defines things; it changes nothing on your machine.

NOTICE_SHORT="Pre-1.0, in active development."

# ── Output ───────────────────────────────────────────────────────────────────
# The words OK, WARN, FAIL and info always print, so the output reads the same without colour
# (piped to a file, NO_COLOR set, or a plain terminal).
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then
    C_RESET=$'\033[0m'
    C_BOLD=$'\033[1m'
    C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'
    C_RED=$'\033[31m'
    C_DIM=$'\033[2m'
else
    C_RESET="" C_BOLD="" C_GREEN="" C_YELLOW="" C_RED="" C_DIM=""
fi

N_OK=0
N_WARN=0
N_FAIL=0

say() { printf '%s\n' "$*"; }
heading() { printf '\n%s%s%s\n' "$C_BOLD" "$*" "$C_RESET"; }
line() { printf '        %s\n' "$*"; }

ok() {
    N_OK=$((N_OK + 1))
    printf '  %sOK%s    %s\n' "$C_GREEN" "$C_RESET" "$*"
}
warn() {
    N_WARN=$((N_WARN + 1))
    printf '  %sWARN%s  %s\n' "$C_YELLOW" "$C_RESET" "$*"
}
fail() {
    N_FAIL=$((N_FAIL + 1))
    printf '  %sFAIL%s  %s\n' "$C_RED" "$C_RESET" "$*"
}
info() { printf '  %sinfo%s  %s\n' "$C_DIM" "$C_RESET" "$*"; }

# ── Which system is this? ────────────────────────────────────────────────────
# Sets DISTRO_NAME, DISTRO_FAMILY (debian or other) and DISTRO_UBUNTU_BASED (yes or no) from
# /etc/os-release. ID and ID_LIKE are what identify a derivative: Zorin OS, for example, has
# ID=zorin and ID_LIKE="ubuntu debian". JOBOMATIC_OS_RELEASE points at another file, for tests.
detect_distro() {
    local file="${JOBOMATIC_OS_RELEASE:-/etc/os-release}"
    local id="" id_like="" pretty=""
    DISTRO_NAME="unknown"
    DISTRO_FAMILY="other"
    DISTRO_UBUNTU_BASED="no"
    [ -r "$file" ] || return 0
    id=$(. "$file" 2>/dev/null && printf '%s' "${ID:-}")
    id_like=$(. "$file" 2>/dev/null && printf '%s' "${ID_LIKE:-}")
    pretty=$(. "$file" 2>/dev/null && printf '%s' "${PRETTY_NAME:-}")
    [ -n "$pretty" ] && DISTRO_NAME="$pretty"
    case " $id $id_like " in
        *" debian "* | *" ubuntu "*) DISTRO_FAMILY="debian" ;;
    esac
    case " $id $id_like " in
        *" ubuntu "*) DISTRO_UBUNTU_BASED="yes" ;;
    esac
    return 0
}

# The command to run to install packages. This script prints it; it never runs it.
install_hint() {
    if [ "$DISTRO_FAMILY" = "debian" ]; then
        printf 'sudo apt update && sudo apt install -y %s' "$*"
    else
        printf 'install these with your package manager: %s' "$*"
    fi
}

# ── Python ───────────────────────────────────────────────────────────────────
python_ok() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

python_version() {
    "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null
}

# Prints the first interpreter among the arguments that runs and is 3.11 or newer.
find_python() {
    local candidate
    for candidate in "$@"; do
        if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

# What to do when the system Python is too old. Advice only; nothing here changes the system.
python_upgrade_advice() {
    if [ "$DISTRO_UBUNTU_BASED" = "yes" ]; then
        line "On Ubuntu and systems built on it (Linux Mint, Pop!_OS, Zorin OS) you can add the"
        line "deadsnakes package source, which has newer Pythons:"
        line "    sudo apt install -y software-properties-common"
        line "    sudo add-apt-repository ppa:deadsnakes/ppa"
        line "    sudo apt update && sudo apt install -y python3.12 python3.12-venv"
        line "then run this script again with:  --python python3.12"
        line "Or move to a release that ships Python 3.11 or newer (Ubuntu 24.04, Linux Mint 22)."
    elif [ "$DISTRO_FAMILY" = "debian" ]; then
        line "Debian 11 and older ship a Python that is too old, and that package source does not"
        line "reach plain Debian. Upgrade to Debian 12 or newer, which ships Python 3.11 or newer."
    else
        line "Install Python 3.11 or newer with your system's package manager, then run this script"
        line "again with:  --python /path/to/that/python3"
    fi
}
