#!/usr/bin/env bash
# One-time setup: points git at this repo's tracked hooks directory.
#
# Hooks under .git/hooks/ are not version controlled, so a copied hook silently
# goes stale. Pointing core.hooksPath at scripts/hooks means the tracked hook IS
# the active hook — no re-install needed when it changes.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

chmod +x scripts/hooks/*
git config core.hooksPath scripts/hooks

echo "core.hooksPath -> scripts/hooks (active hooks: $(ls scripts/hooks | tr '\n' ' '))"
