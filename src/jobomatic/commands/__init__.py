"""The commands: what ``jobo`` and the MCP server run to produce a result.

Each one composes the modules (profile, fit, applications, documents) for a single task: a fit
check, a gap analysis, a resume, a cover letter. They are moved here as they were, so they still
mix content logic, layout and file access; splitting each into a model and a renderer is a later
pass. The modules themselves stay free of this glue, and the architecture contracts keep it so.
"""
