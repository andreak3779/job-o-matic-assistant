"""The presence module: paste-ready copy for LinkedIn, GitHub, Jobgether, job boards and Pluralsight.

Each generator reads the public view of the profile and the matching skill file, and writes a
draft the user pastes by hand. Output passes the PII guard (``jobomatic.privacy``).

The generators are moved here as they were; splitting each into a model and a renderer is a
later pass.
"""
