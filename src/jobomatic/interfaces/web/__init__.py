"""The local web UI (ADR 0025): a third way in beside the command line and the MCP server.

It is another thin adapter. It holds no rules: it calls the commands (ADR 0028), renders their
results, and is independent of the other two interfaces. It listens on loopback only and is started
by ``jobo web``.
"""
