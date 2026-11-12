"""``profile`` subcommands: check the vault's profile, print it, and print its JSON Schema.

A thin driving adapter: the commands are in ``jobomatic.commands.profile``; this parses and prints.
"""

from __future__ import annotations

import argparse
import json

from jobomatic.commands import profile as profile_commands
from jobomatic.profile.model import Profile
from jobomatic.results import emit

COMMAND = "profile"


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    profile = subparsers.add_parser("profile", help="The typed profile stored in the vault")
    sub = profile.add_subparsers(dest="profile_command", required=True)
    sub.add_parser("validate", help="Load the profile and run its consistency checks")
    sub.add_parser("schema", help="Print the JSON Schema generated from the profile models")
    show = sub.add_parser("show", help="Print the profile as markdown, whole or in slices")
    show.add_argument(
        "--public",
        action="store_true",
        help="Only what may appear on LinkedIn, GitHub and job boards (no contact details)",
    )
    show.add_argument("part", choices=profile_commands.PARTS)
    show.add_argument("names", nargs="*", help="Section names, for 'section'")


def run(args: argparse.Namespace) -> int:
    if args.profile_command == "schema":
        print(json.dumps(Profile.model_json_schema(), indent=2))
        return 0
    if args.profile_command == "show":
        result = profile_commands.show(args.part, tuple(args.names), public=args.public)
        return emit(result, profile_commands.render_show)
    return emit(profile_commands.validate(), profile_commands.render_validate)
