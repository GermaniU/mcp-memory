"""faithfulness/gate.py — pre-persist faithfulness gate (TKT-1291).

Intercepts fact writes to the memory store BEFORE persistence and runs them
through an engine-neutral LLM judge, so hallucinated/contradicted facts never
reach the store. Origin: the `hermes reload-mcp` incident (2026-07-18) — a
nonexistent command got consolidated as a fact and poisoned recall for every
downstream session. See ADR (Mnemo) + `~/.claude/skills/eval-corpus-faithfulness/`.

VENDORING NOTICE: `call_provider()` and `extract_json()` below are a deliberate
COPY of the same-named functions in
`~/.claude/skills/eval-corpus-faithfulness/run_judge.py` — NOT an import.
mcp-memory is a separate repo that can be deployed to a host that never sees
`~/.claude/`, so the judge plumbing is vendored in. If you change the
semantics of the judge call in run_judge.py, port the change here too (and
vice versa) — there is no shared package enforcing parity.

RÚBRICA / DRIFT RISK: the canonical rubric lives at
`~/.claude/skills/eval-corpus-faithfulness/rubric.md`. The copy vendored next
to this file (`faithfulness/rubric.md`) can drift from the canonical one over
time. If this repo runs co-located with `~/.claude/` (same device as the
Hermes Framework), point `FAITHFULNESS_RUBRIC_PATH` at the canonical path
instead of relying on the vendored default — that avoids maintaining two
copies. On a host without `~/.claude/` (e.g. a remote deploy), the vendored
copy is the only option and must be refreshed by hand when the rubric changes.

ENGINE-NEUTRAL: the judge never runs on Claude in production. Default
provider is `gemini` (`HERMES_JUDGE_PROVIDER` env overrides it); the `claude`
branch of `call_provider()` is dev-only and always raises.

One deliberate deviation from run_judge.py: an unknown `provider` here raises
`ValueError` instead of calling `SystemExit`. run_judge.py is a one-shot CLI
where killing the process on a bad `--provider` flag is fine; mcp-memory is a
long-running server — `SystemExit` there would take the whole process down
over what should be a per-call error.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Path del wrapper Gemini — override por env para portar al lado Hermes Agent
# o a un host sin ~/.claude/ (ver riesgo de deploy en el docstring del módulo).
GEMINI_WRAPPER = os.environ.get(
    "GEMINI_WRAPPER", os.path.expanduser("~/.claude/hooks/gemini-run.sh")
)

_VENDORED_RUBRIC_PATH = Path(__file__).parent / "rubric.md"

_DEFAULT_REVIEW_QUEUE_PATH = os.path.expanduser("~/.mcp-memory/faithfulness-review-queue.jsonl")

# Namespaces gateados en el path interactivo de `memory_save` (ver is_gated_namespace).
# Default: solo "decisions" — es la Decision Memory que alimenta el recall del
# gate de despacho (paso 0, CLAUDE.md global) en TODAS las sesiones; el mismo
# radio de propagación que motivó este gate. Namespaces fuera de la lista
# (p.ej. "default") pasan directo: un save interactivo no puede esperar hasta
# 180s de Gemini en cada llamada.
_DEFAULT_GATE_NAMESPACES = "decisions"


class FaithfulnessGateError(Exception):
    """El fact fue retenido por el gate de faithfulness (rejected u held_judge_error).

    Nunca se persiste cuando se levanta esta excepción — el caller del tool MCP
    la ve como un error de tool (no un éxito silencioso, no un crash del server).
    """


# ── Vendorizado de run_judge.py — ver VENDORING NOTICE arriba ──────────────


def _read_rubric(path: str | Path) -> str:
    # System prompt = primer bloque ``` … ``` del rubric.md (o el archivo entero).
    txt = Path(path).read_text()
    m = re.search(r"```\n(.*?)```", txt, re.S)
    return (m.group(1) if m else txt).strip()


def extract_json(s: str | None) -> dict | None:
    """Primer objeto {...} balanceado — ignora fences ```json y el trailer del wrapper."""
    if not s:
        return None
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def call_provider(prompt: str, provider: str, *, timeout: int = 180) -> str:
    """Único punto acoplado al motor. Engine-neutral por diseño: cualquier modelo
    fuerte CON GROUNDING (acceso read-only a --help/filesystem) sirve de juez."""
    if provider == "gemini":
        # Wrapper obligatorio (gemini-run.sh): escanea quota — el exit 0 de gemini
        # NO es confiable (TKT-654). El trailer ⟦gemini-run⟧ lo descarta extract_json.
        # gemini-cli es AGENTICO: en -p sin --approval-mode se CUELGA esperando aprobar
        # los tools que el juez corre para grounding (--help/ls). yolo + --skip-trust lo
        # destraban; timeout evita el cuelgue indefinido (fallback a PARSE_ERROR en gate_fact).
        flags = os.environ.get(
            "GEMINI_JUDGE_FLAGS", "--approval-mode yolo --skip-trust -o text"
        ).split()
        try:
            r = subprocess.run(
                [GEMINI_WRAPPER, "-p", prompt, *flags],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return r.stdout
        except subprocess.TimeoutExpired:
            return ""  # nunca cuelga indefinido → gate_fact mapea a verdict "error"
        except OSError:
            # Wrapper ausente/no ejecutable en este host (deploy sin ~/.claude/, ver
            # riesgo en el docstring del módulo) — mismo fail-closed que un timeout.
            return ""
    if provider == "zai":
        raise NotImplementedError(
            "zai: POST al endpoint …/api/coding/paas/v4 "
            "(memoria project-hermes-gateway-zai-coding-endpoint)"
        )
    if provider == "ollama":
        raise NotImplementedError(
            "ollama: POST /api/chat con modelo :cloud o local (ojo SPOF 429, TKT-1279)"
        )
    if provider == "claude":
        raise NotImplementedError(
            "claude: `claude -p` headless — SOLO dev. "
            "NO es el juez de prod: no casar con Claude CLI."
        )
    raise ValueError(f"proveedor desconocido: {provider}")


# ── Superficie propia de mcp-memory ─────────────────────────────────────────


def _resolve_rubric_path() -> Path:
    override = os.environ.get("FAITHFULNESS_RUBRIC_PATH")
    return Path(override) if override else _VENDORED_RUBRIC_PATH


def gate_fact(content: str, *, provider: str | None = None, timeout: int = 180) -> dict[str, Any]:
    """Corre el juez de faithfulness sobre `content` antes de persistirlo.

    Returns:
        {"verdict": "accept"|"reject"|"error", "severity": str|None,
         "reason": str, "claims": list}

    Mapeo de verdict (rubric.md — regla de decisión):
      - juez pass=true                                  -> accept
      - juez pass=false (>=1 claim CONTRADICTED)         -> reject
      - pass=None / PARSE_ERROR / timeout / stdout vacío -> error

    "error" es fail-closed a propósito: NUNCA accept, NUNCA se trata como
    reject silencioso. El caller decide qué hacer con "error" (mcp-memory lo
    manda a la cola de revisión con motivo held_judge_error — ver
    append_to_review_queue), nunca lo persiste directo.
    """
    resolved_provider = provider or os.environ.get("HERMES_JUDGE_PROVIDER", "gemini")
    system = _read_rubric(_resolve_rubric_path())
    prompt = (
        f"{system}\n\n--- FACT A EVALUAR ---\n{content}\n\n"
        "Devolvé SOLO el JSON, con el formato de salida definido en la rúbrica."
    )
    raw = call_provider(prompt, resolved_provider, timeout=timeout)
    verdict_json = extract_json(raw)

    if verdict_json is None or verdict_json.get("pass") is None:
        reason = (
            "PARSE_ERROR"
            if verdict_json is None
            else str(verdict_json.get("reasoning") or "PARSE_ERROR")
        )
        return {"verdict": "error", "severity": None, "reason": reason, "claims": []}

    passed = bool(verdict_json["pass"])
    return {
        "verdict": "accept" if passed else "reject",
        "severity": verdict_json.get("severity"),
        "reason": str(verdict_json.get("reasoning") or ""),
        "claims": verdict_json.get("claims") or [],
    }


def is_gated_namespace(namespace: str) -> bool:
    """True si `namespace` debe pasar por gate_fact() en el path interactivo de save.

    Scope configurable vía FAITHFULNESS_GATE_NAMESPACES (CSV, default "decisions").
    Leído en cada llamada (no cacheado a nivel de módulo) para que los tests
    puedan overridear el env sin reimportar el módulo.
    """
    raw = os.environ.get("FAITHFULNESS_GATE_NAMESPACES", _DEFAULT_GATE_NAMESPACES)
    gated = {ns.strip() for ns in raw.split(",") if ns.strip()}
    return namespace in gated


def append_to_review_queue(
    *,
    namespace: str,
    content: str,
    verdict: str,
    severity: str | None,
    reason: str,
    source: str,
    queue_path: str | Path | None = None,
) -> None:
    """Appendea un fact rechazado/retenido a la cola de revisión (JSONL, 1 línea/entry).

    `verdict` distingue "rejected" (el juez contradijo el fact) de
    "held_judge_error" (el juez no pudo decidir — timeout/parse-error/wrapper
    ausente). `source` es "save" o "import" — de qué tool vino el intento.

    Ruta configurable vía FAITHFULNESS_REVIEW_QUEUE (default
    ~/.mcp-memory/faithfulness-review-queue.jsonl, mismo patrón "carpeta de
    datos en el home" que el resto de la config de mcp-memory por env vars).
    """
    path = (
        Path(queue_path)
        if queue_path is not None
        else Path(os.environ.get("FAITHFULNESS_REVIEW_QUEUE", _DEFAULT_REVIEW_QUEUE_PATH))
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "namespace": namespace,
        "content": content,
        "verdict": verdict,
        "severity": severity,
        "reason": reason,
        "source": source,
    }
    with path.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
