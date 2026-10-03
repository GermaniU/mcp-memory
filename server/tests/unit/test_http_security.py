"""Seguridad del transporte HTTP: CORS cerrado por defecto.

Regresión: antes se servía `Access-Control-Allow-Origin: *`, lo que permitía a
cualquier página web abierta en el navegador leer, exportar o borrar memorias
vía `fetch("http://127.0.0.1:8765/mcp")`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from mcp_memory.server import build_app, build_http_app
from mcp_memory.shared.config import Settings

EVIL = "https://sitio-malicioso.example"
TRUSTED = "http://localhost:3000"


class _NoopStore:
    """build_app solo cablea; el preflight CORS nunca llega al store."""


def _preflight(origin: str, *, cors_origins: str = ""):
    settings = Settings(db_path=":memory:", mcp_cors_origins=cors_origins)
    app = build_app(settings=settings, store=_NoopStore())
    # `with` ejecuta el lifespan de la app (lo necesita la ruta MCP).
    with TestClient(build_http_app(app, settings)) as client:
        return client.options(
            "/mcp",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )


def test_cors_is_closed_by_default():
    response = _preflight(EVIL)
    assert "access-control-allow-origin" not in response.headers


def test_configured_origin_is_allowed():
    response = _preflight(TRUSTED, cors_origins=TRUSTED)
    assert response.headers.get("access-control-allow-origin") == TRUSTED


def test_unlisted_origin_is_rejected_even_when_cors_is_enabled():
    response = _preflight(EVIL, cors_origins=TRUSTED)
    assert response.headers.get("access-control-allow-origin") != EVIL
    assert response.headers.get("access-control-allow-origin") != "*"


def test_cors_origin_list_parsing():
    settings = Settings(mcp_cors_origins=" http://a.local , ,https://b.local ")
    assert settings.cors_origin_list() == ["http://a.local", "https://b.local"]
    assert Settings().cors_origin_list() == []


def test_cors_origins_read_from_mcp_cors_origins_env(monkeypatch):
    monkeypatch.setenv("MCP_CORS_ORIGINS", TRUSTED)
    assert Settings().cors_origin_list() == [TRUSTED]
