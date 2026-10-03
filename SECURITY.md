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

## Reportar una vulnerabilidad

**No abras un issue público.** Usa el reporte privado de GitHub: ve a la pestaña **Security** del repositorio, elige **Report a vulnerability** e incluye:

- los pasos para reproducirlo;
- el impacto (qué datos se exponen o qué puede hacer un atacante);
- la versión o el commit afectado.

Puedes escribir en español o en inglés.
