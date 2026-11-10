"""The landing page's copies of the branding files must match the originals.

``site/assets/`` holds copies so ``site/index.html`` works when opened straight from the repo
and the Pages workflow can deploy ``site/`` as it is. This keeps the copies from drifting.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ORIGINALS = (ROOT / "src" / "jobomatic" / "branding", ROOT / "docs" / "assets")


def _original(name: str) -> Path:
    for folder in ORIGINALS:
        if (folder / name).is_file():
            return folder / name
    raise AssertionError(f"{name} is in site/assets but has no original")


def test_site_assets_match_their_originals() -> None:
    copies = sorted((SITE / "assets").iterdir())
    assert copies, "site/assets is empty"
    for copy in copies:
        assert copy.read_bytes() == _original(copy.name).read_bytes(), copy.name


def test_every_asset_the_page_references_exists() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    local = re.findall(r'(?:src|href)="(assets/[^"]+)"', html)
    assert local, "the page references no local assets"
    for ref in local:
        assert (SITE / ref).is_file(), ref
