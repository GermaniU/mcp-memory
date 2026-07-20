from __future__ import annotations

import json

import pytest

from mcp_memory.faithfulness import gate as gate_module
from mcp_memory.faithfulness.gate import extract_json, gate_fact, is_gated_namespace

# Referencia capturada en import-time, ANTES de que el autouse fixture de
# conftest.py (_faithfulness_gate_accepts_by_default) parchee
# gate_module.call_provider para el resto de la suite. Este test ejercita el
# call_provider REAL (no mockeado) — necesita el objeto función original.
_REAL_CALL_PROVIDER = gate_module.call_provider


def _judge_json(payload: dict) -> str:
    return json.dumps(payload)


class TestExtractJson:
    def test_extracts_balanced_object(self):
        raw = '```json\n{"pass": true, "id": "x"}\n```\n⟦gemini-run⟧ trailer'
        assert extract_json(raw) == {"pass": True, "id": "x"}

    def test_returns_none_on_empty_string(self):
        assert extract_json("") is None

    def test_returns_none_on_no_json(self):
        assert extract_json("no json here") is None

    def test_returns_none_on_invalid_json(self):
        assert extract_json("{not valid json}") is None


class TestGateFact:
    def test_poisoned_fact_pass_false_maps_to_reject(self, monkeypatch):
        # Simula el juez detectando el incidente sintético `hermes reload-mcp`.
        verdict = {
            "id": "ex01",
            "pass": False,
            "severity": "critical",
            "reasoning": "El comando 'hermes reload-mcp' no existe (hermes --help no lo lista).",
            "claims": [
                {
                    "claim": "El comando `hermes reload-mcp` recarga los MCPs.",
                    "verdict": "CONTRADICTED",
                    "check": "hermes --help",
                    "evidence": "hermes --help no lista ningún subcomando reload-mcp.",
                }
            ],
        }
        monkeypatch.setattr(
            gate_module, "call_provider", lambda prompt, provider, **kw: _judge_json(verdict)
        )

        result = gate_fact("Para recargar los MCPs corré `hermes reload-mcp`.")

        assert result["verdict"] == "reject"
        assert result["severity"] == "critical"
        assert result["claims"][0]["verdict"] == "CONTRADICTED"

    def test_clean_fact_pass_true_maps_to_accept(self, monkeypatch):
        verdict = {
            "id": "ex02",
            "pass": True,
            "severity": "low",
            "reasoning": "Todas las afirmaciones checkeables verifican contra la realidad.",
            "claims": [],
        }
        monkeypatch.setattr(
            gate_module, "call_provider", lambda prompt, provider, **kw: _judge_json(verdict)
        )

        result = gate_fact("El repo mcp-memory expone memory_save vía MCP.")

        assert result["verdict"] == "accept"

    def test_empty_stdout_maps_to_error(self, monkeypatch):
        # Simula timeout o wrapper ausente: call_provider vendorizado devuelve "".
        monkeypatch.setattr(gate_module, "call_provider", lambda prompt, provider, **kw: "")

        result = gate_fact("cualquier fact")

        assert result["verdict"] == "error"
        assert result["reason"] == "PARSE_ERROR"

    def test_invalid_json_maps_to_error(self, monkeypatch):
        monkeypatch.setattr(
            gate_module, "call_provider", lambda prompt, provider, **kw: "esto no es JSON"
        )

        result = gate_fact("cualquier fact")

        assert result["verdict"] == "error"

    def test_pass_none_maps_to_error(self, monkeypatch):
        # El juez respondió JSON válido pero sin decisión clara (imita el
        # fallback PARSE_ERROR de run_judge.py cuando extract_json ya falló antes).
        verdict = {"id": "ex03", "pass": None, "severity": None, "reasoning": "PARSE_ERROR"}
        monkeypatch.setattr(
            gate_module, "call_provider", lambda prompt, provider, **kw: _judge_json(verdict)
        )

        result = gate_fact("cualquier fact")

        assert result["verdict"] == "error"

    def test_threads_provider_and_timeout_to_call_provider(self, monkeypatch):
        seen = {}

        def fake_call_provider(prompt, provider, **kw):
            seen["provider"] = provider
            seen["timeout"] = kw.get("timeout")
            return _judge_json({"pass": True, "severity": "low", "reasoning": "ok", "claims": []})

        monkeypatch.setattr(gate_module, "call_provider", fake_call_provider)

        gate_fact("fact", provider="zai-mock", timeout=42)

        assert seen["provider"] == "zai-mock"
        assert seen["timeout"] == 42


class TestIsGatedNamespace:
    def test_default_gates_only_decisions(self, monkeypatch):
        monkeypatch.delenv("FAITHFULNESS_GATE_NAMESPACES", raising=False)
        assert is_gated_namespace("decisions") is True
        assert is_gated_namespace("default") is False

    def test_respects_csv_override(self, monkeypatch):
        monkeypatch.setenv("FAITHFULNESS_GATE_NAMESPACES", "decisions,ops,flowordr")
        assert is_gated_namespace("ops") is True
        assert is_gated_namespace("flowordr") is True
        assert is_gated_namespace("default") is False


class TestCallProviderUnknownProvider:
    def test_unknown_provider_raises_value_error_not_system_exit(self):
        with pytest.raises(ValueError):
            _REAL_CALL_PROVIDER("prompt", "totally-unknown-provider")
