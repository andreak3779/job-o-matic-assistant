"""What the profile use cases need from the outside world. Adapters implement these."""

from __future__ import annotations

from typing import Protocol

from jobomatic.profile.model import Profile, Story


class ProfileRepository(Protocol):
    """Where the profile is stored. The vault's YAML files are one implementation."""

    def load(self) -> Profile:
        """Read and validate the whole profile; raise ``ProfileError`` if it cannot be read."""
        ...

    def save(self, profile: Profile) -> None:
        """Write the whole profile, replacing what was stored."""
        ...

    def save_stories(self, stories: list[Story]) -> None:
        """Write only the STAR stories (interview prep records which ones it used)."""
        ...
