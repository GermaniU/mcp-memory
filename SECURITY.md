# Seguridad

Este documento explica qué protege `mcp-memory`, qué **no** protege y cómo reportar una vulnerabilidad.

*English summary: report vulnerabilities privately via the repository's **Security → Report a vulnerability** tab. Do not open public issues for security problems.*

---

## Modelo de amenazas

`mcp-memory` es un servidor **local y de un solo usuario**: guarda texto en un archivo SQLite de tu máquina y lo expone por MCP en `http://127.0.0.1:8765/mcp`. **No tiene autenticación.** La seguridad se basa en que solo tu máquina, y solo tus programas, puedan alcanzarlo.

### Lo que protege

| Riesgo | Cómo se mitiga |
|---|---|
| Otro equipo de tu red lee o borra tus memorias | Por defecto escucha solo en `127.0.0.1` (`MCP_HOST`). |
| **Una página web que visitas lee, exporta o borra tus memorias** con `fetch("http://127.0.0.1:8765/mcp")` | **CORS cerrado por defecto.** Sin `MCP_CORS_ORIGINS`, el navegador no deja que ninguna web lea las respuestas. Si lo activas, solo se permiten los orígenes exactos que listes. Hay un test de regresión (`tests/unit/test_http_security.py`). |
| Inyección SQL / FTS5 desde una query | Todas las consultas usan parámetros y el `MATCH` de FTS5 se construye escapando cada token. |
| El contenedor compromete el host | La imagen Docker corre como usuario sin privilegios (`uid 10001`) y solo escribe en `/data`. |
| Dependencias vulnerables | La CI ejecuta `pip-audit` y Dependabot propone actualizaciones semanales. |

### Lo que NO protege

- **Otros procesos de tu propio usuario.** Cualquier programa que corra en tu máquina puede llamar al endpoint local. Si eso te preocupa, ejecuta el server en un usuario o contenedor aparte.
- **La exposición a internet.** Si cambias `MCP_HOST` a `0.0.0.0` o publicas el puerto en todas las interfaces, **cualquiera** que llegue al puerto puede leer y borrar todo. Pon delante un proxy con autenticación y TLS.
- **Los datos en reposo.** El archivo SQLite no está cifrado. Protégelo con los permisos de tu sistema o con cifrado de disco.
- **El contenido que guardas.** Una memoria puede contener instrucciones dirigidas al agente (prompt injection). Trátalas como entrada no confiable, igual que cualquier texto externo.
- **`MCP_CORS_ORIGINS=*`.** Es técnicamente posible, pero equivale a abrir tus memorias a cualquier web que visites. **No lo uses.**

---

## Configuración recomendada

| Ajuste | Recomendación |
|---|---|
| `MCP_HOST` | `127.0.0.1` (default). En Docker usa `-p 127.0.0.1:8765:8765`. |
| `MCP_CORS_ORIGINS` | Vacío (default). Solo lístalo si tienes un cliente **web** propio, con los orígenes exactos. |
| `DB_PATH` | Un directorio solo accesible por tu usuario (`chmod 700 ~/.agent-memory`). |

---

## Cadena de suministro: incidente eMudhra

En octubre de 2026 se publicaron las claves privadas de intermediarios de eMudhra emitidos por `emSign ECC Root CA - G3`: con ellas se pueden fabricar certificados TLS válidos para cualquier dominio, incluidos python.org y pypi.org. Los bundles de CA embebidos se corrigieron en estas versiones mínimas ([GHSA-6q48-6c7w-9gw2](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2), [GHSA-hq85-5cpj-mr62](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62)):

| Herramienta | Mínimo | Qué hace este repo |
|---|---|---|
| `pip` | 26.2.2 | La imagen Docker y la CI reemplazan el pip de base por un wheel fijado por hash antes de instalar nada; la CI verifica la versión dentro de la imagen. |
| `certifi` | 2026.10.19 | El server no lo importa: `httpx2` valida TLS con `truststore` (almacén del sistema). `fastmcp` actual (4.1.3) lo arrastra con ese piso y la CI comprueba la versión dentro de la imagen; `pip-audit` lo usa en CI y lo pide explícitamente. |
| `uv` | 0.13.4 | `server/pyproject.toml` declara `required-version = ">=0.13.4"`: un uv anterior se niega a operar sobre el proyecto. |

Si ya tienes un venv creado, actualiza pip con el wheel fijado por hash (un `pip install --upgrade pip` normal descargaría la actualización con el almacén vulnerable):

```bash
python -m pip install --no-deps "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
```

Las imágenes publicadas se construyen sin caché de capas y sobre la imagen base actual, para heredar el almacén de CA corregido del sistema.

---

## Reportar una vulnerabilidad

**No abras un issue público.** Usa el reporte privado de GitHub: ve a la pestaña **Security** del repositorio, elige **Report a vulnerability** e incluye:

- los pasos para reproducirlo;
- el impacto (qué datos se exponen o qué puede hacer un atacante);
- la versión o el commit afectado.

Puedes escribir en español o en inglés.
