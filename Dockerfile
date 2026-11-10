FROM python:3.11-slim

WORKDIR /app

# Copy dependency metadata first so the pip install layer only invalidates
# when pyproject.toml actually changes, not on every source edit.
COPY pyproject.toml requirements-lock.txt ./
COPY src ./src
COPY skills ./skills
COPY reference ./reference
COPY templates ./templates
COPY tests ./tests
# The skills that src/jobomatic/interfaces/mcp/skill_prompts.py serves to Claude Desktop as prompts.
COPY .claude/skills ./.claude/skills
COPY README.md ./README.md

# This image only ever runs the MCP server (src/jobomatic/interfaces/mcp/server.py -> src/jobomatic/interfaces/cli/main.py).
# Every document is generated in Python (python-docx, installed by the `docx` extra below);
# nothing in the project needs Node.js.
# Versions are pinned by requirements-lock.txt (pip constraints). Dev tooling
# (pytest, coverage) is opt-in: `podman build --build-arg INSTALL_DEV=true .`
ARG INSTALL_DEV=false
RUN pip install --no-cache-dir -c requirements-lock.txt -e ".[mcp,parser,pdf]" \
    && if [ "$INSTALL_DEV" = "true" ]; then \
        pip install --no-cache-dir -c requirements-lock.txt -e ".[dev]"; \
    fi

# The vault (personal data) is never copied in: it is bind-mounted at /vault when the container
# runs, and found through this variable (ADR 0005, updated for the two-repo layout).
ENV JOBOMATIC_VAULT=/vault

# Deliberately still root inside the container: this image is run with rootless
# Podman over a bind-mounted vault (ADR 0005), where container root maps to the
# host user. A non-root container user would map to a sub-uid and be unable to
# read or write the host-owned files, so adding USER here would break that setup.
CMD ["python3", "-m", "jobomatic.interfaces.mcp.server"]
