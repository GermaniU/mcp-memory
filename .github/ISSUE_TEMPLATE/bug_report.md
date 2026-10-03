---
name: Bug report
about: Something is broken or behaving unexpectedly
title: "fix: <short description>"
labels: bug
assignees: ""
---

<!-- Security problem? Do NOT open a public issue. See SECURITY.md. -->

## Version

<!-- Output of: pip show mcp-memory | grep Version  OR  the Docker image tag you're using -->

## Installation mode

<!-- Check one -->
- [ ] Standalone Python process (`mcp-memory` CLI)
- [ ] Docker image (`ghcr.io/germaniu/mcp-memory`)
- [ ] Other (describe below)

## Environment

- OS:
- Python version (`python --version`):
- MCP client (Claude Code, Cursor, OpenCode, Continue, …):

## Configuration

<!-- Any variables you changed from .env.example. Do not paste memory contents you consider private. -->

```
DB_PATH=
MCP_HOST=
MCP_PORT=
MCP_CORS_ORIGINS=
```

## Steps to reproduce

1.
2.
3.

## Expected behavior

<!-- What should have happened -->

## Actual behavior

<!-- What actually happened — include the full error message / traceback -->

## Diagnostics

```
mcp-memory check
curl localhost:8765/health
```

<!-- Paste both outputs here -->

## Additional context

<!-- Logs, screenshots, relevant environment details -->

---

> Issues in Spanish are welcome too. / Los issues en español también son bienvenidos.
