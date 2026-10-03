---
name: Bug report
about: Something is broken or behaving unexpectedly
title: "fix: <short description>"
labels: bug
assignees: ""
---

## Version

<!-- Output of: pip show mcp-memory | grep Version  OR  the Docker image tag you're using -->

## Installation mode

<!-- Check one -->
- [ ] Docker Compose (default stack from README)
- [ ] Standalone Python process (`mcp-memory` CLI)
- [ ] External Qdrant (pointing `QDRANT_URL` to your own instance)
- [ ] Other (describe below)

## Embedding configuration

```
EMBEDDING_MODEL=
EMBEDDING_DIM=
```

## Steps to reproduce

1.
2.
3.

## Expected behavior

<!-- What should have happened -->

## Actual behavior

<!-- What actually happened — include the full error message / traceback -->

## Health check output

```
curl localhost:8765/health
```

<!-- Paste the response here -->

## Additional context

<!-- Logs, screenshots, relevant environment details -->

---

> Issues in Spanish are welcome too. / Los issues en español también son bienvenidos.
