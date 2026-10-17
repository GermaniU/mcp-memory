import os
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "~/.agent-memory/memory.db"

    # "stdio": el cliente MCP lanza el proceso y habla por stdin/stdout (sin
    # puerto ni server de fondo). "http": Streamable HTTP en MCP_HOST:MCP_PORT.
    mcp_transport: Literal["http", "stdio"] = "http"

    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765

    default_namespace: str = "default"

    # Orígenes de navegador autorizados a llamar al endpoint HTTP, separados por
    # comas (ej. "http://localhost:3000,https://mi-gateway.local"). Vacío = sin
    # CORS: ninguna página web puede leer ni modificar tus memorias desde el
    # navegador. Nunca uses "*": cualquier sitio que visites podría hacerlo.
    mcp_cors_origins: str = ""

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.mcp_cors_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    settings = Settings()
    if settings.db_path != ":memory:":
        settings.db_path = os.path.expanduser(settings.db_path)
    return settings
