# Contribuir a MCP Memory

¡Gracias por interesarte! Este documento define **cómo se construye** y **cómo se contribuye** al proyecto. Léelo antes de mandar un PR — los detalles aquí son la diferencia entre un PR que se mergea rápido y uno que pide cambios.

---

## 🎯 Filosofía

> **Software pequeño, bien hecho, fácil de mantener.**

MCP Memory es deliberadamente reducido. Hace **una cosa** (memoria léxica de texto plano vía MCP, con SQLite + FTS5) y la hace bien. No vamos a añadir features especulativas. Cada línea de código que entra al repo tiene que justificar su mantenimiento.

---

## 📐 Disciplinas (no negociables)

### Clean Code
- Nombres claros en inglés. Si necesitas un comentario para explicar qué hace una función, primero intenta renombrar la función.
- Funciones cortas, una responsabilidad. Una función no debe pedir más de 4-5 parámetros — si los necesita, probablemente debería ser una clase.
- Sin código muerto. Si está comentado o no se usa, se borra.

### SOLID (sin sobreingeniería)
- **SRP**: cada handler hace una cosa. `MemoryStore` solo persiste y busca.
- **DIP**: los handlers dependen del `Protocol` `MemoryStore` (`shared/types.py`), no de `SqliteFtsStore`. Esto permite tests con un `FakeStore` en memoria. `tests/unit/test_architecture.py` lo hace cumplir.
- **OCP**: añadir una tool nueva = una carpeta nueva. **No se modifican slices existentes** salvo bug fix.
- **No** factories, **no** builders, **no** registries dinámicos. Wiring explícito en `server.build_app`.

### KISS · YAGNI
- Si solo hay una implementación, **no hay interfaz**. La interfaz aparece cuando aparece la segunda implementación o cuando la necesita un test.
- No se añaden features "por si acaso". Tres líneas similares es mejor que una abstracción prematura.
- No se añade error handling para escenarios que no pueden pasar. Confía en el framework. Valida solo en los bordes (entrada del usuario, APIs externas).

### Vertical slice architecture
```
server/src/mcp_memory/
├── server.py                 # composition root: wiring FastMCP + dependencias
├── shared/                   # solo lo verdaderamente compartido entre slices
│   ├── config.py · store.py · types.py
└── tools/                    # 1 carpeta = 1 slice MCP
    ├── save/handler.py · search/handler.py · …
```
**Cada slice es independiente.** Si tocas `save/`, no tocas `search/`. Tests de cada slice viven aparte. Una tool nunca importa otra tool ni el store concreto: lo verifica `tests/unit/test_architecture.py`.

### Tests primero (TDD bienvenido)
- **Lógica con reglas** → escribe el test antes que el handler.
- **Wiring/glue** (server.py, factories) → tests de integración cubren esto, no hace falta TDD.
- Cada PR con código nuevo trae sus tests. **No se acepta lógica sin tests.**
- Los tests unitarios usan `FakeStore` (in-memory, determinista). Los de integración usan un `SqliteFtsStore` real sobre `:memory:`. Ninguno necesita servicios externos.

### Comentarios
- **Por defecto, no escribas comentarios.** Un nombre bien elegido y una función pequeña ya cuentan el "qué".
- Solo añade comentarios cuando expliquen el **WHY** (decisión, restricción no obvia, workaround). Nunca el "what" (eso lo dice el código).
- Sin comentarios tipo `# bug fix de issue #42` o `# usado por X` — eso pertenece al PR, no al código.

---

## 📝 Convenciones

### Idioma
- **Identifiers (clases, funciones, variables, files)**: inglés.
- **Comentarios y docstrings**: español si aportan, inglés si más natural — el criterio es claridad.
- **Commits, PRs, issues**: español.
- **Documentación (`docs/`, README)**: español.

### Conventional Commits (en español)
```
feat: añadir tool memory_export
fix: corregir filtro de namespace en search
docs: aclarar cómo mover DB_PATH a otra máquina
refactor: extraer payload mapping a helpers
test: cubrir caso de namespace vacío en list
chore: actualizar dependencias
```

Mensaje en imperativo, primera línea ≤ 72 chars, cuerpo opcional explicando el **WHY**.

### Pull Request
- **1 PR = 1 propósito.** No mezclar feature + refactor + bumps de deps.
- Título en formato Conventional Commit.
- Cuerpo del PR responde: **qué cambia, por qué, cómo lo probaste**.
- CI verde (ruff, tests, pip-audit y build Docker). Local: `ruff check src tests scripts && pytest tests -q`.

---

## 🛠 Setup de desarrollo

```bash
git clone https://github.com/GermaniU/mcp-memory.git
cd mcp-memory/server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Tests unitarios (75, sin servicios externos, ~1s)
pytest tests/unit -q

# Tests de integración (14, SQLite + FTS5 real sobre :memory:, ~2s)
pytest tests/integration -q

# Lint + format
ruff check src tests scripts
ruff format src tests scripts
```

> Los tests de integración usan una base `:memory:` efímera por test: nunca tocan
> tu `DB_PATH` real.

---

## 🆕 Cómo añadir una tool MCP

Pongamos que quieres añadir `memory_tags` (listar los tags usados). Sigue este flujo y tu PR pasa rápido:

### 1. Crea la slice

```
server/src/mcp_memory/tools/tags/
├── __init__.py    # vacío
└── handler.py     # TagsInput + async tags(...)
```

`handler.py`:

```python
from __future__ import annotations
from pydantic import BaseModel, Field
from mcp_memory.shared.types import MemoryStore


class TagsInput(BaseModel):
    namespace: str | None = Field(None)


async def tags(inp: TagsInput, *, store: MemoryStore) -> list[str]:
    items = await store.list_(namespace=inp.namespace, limit=10_000, offset=0)
    return sorted({tag for item in items for tag in item.tags})
```

### 2. Escribe tests (antes que la implementación si haces TDD)

```
server/tests/unit/tools/test_tags.py
```

Con `FakeStore` ya disponible en `conftest.py`. Cubre:
- Happy path.
- Filtro por namespace.
- 1-2 edge cases (namespace vacío, memorias sin tags).

### 3. Cablea en `server.py`

Añade el decorator junto a las otras tools — **no toques las existentes**. La
función wrapper recibe los campos **aplanados** (un parámetro por campo) para que
el schema MCP que ven los clientes no quede anidado; el `Input` del handler se
reconstruye internamente:

```python
from mcp_memory.tools.tags.handler import TagsInput, tags

@mcp.tool(name="memory_tags", description="Listar los tags usados en las memorias.")
async def _tags(namespace: str | None = None) -> list[str]:
    inp = TagsInput(namespace=namespace)
    return await tags(inp, store=store)
```

> ⚠️ No declares el parámetro como `inp: TagsInput`. Eso anida el schema bajo
> `inp` y obliga a los clientes a llamar con `{"inp": {...}}` (regresión del
> breaking corregido en 0.2.0).

### 4. Actualiza docs

Regla anti-drift (ver `CLAUDE.md`), en el mismo PR:
- `README.md` y `README.en.md`: fila en la tabla de tools y el conteo de tools.
- `docs/CLIENTS.md`: ejemplo de invocación si tiene argumentos no obvios.
- `CHANGELOG.md`: entrada en `[Unreleased]`.

### 5. PR

Conventional commit, descripción clara, tests pasando.

---

## 🧪 Cómo añadir otro backend de almacenamiento

Solo si hay un caso de uso real (por ejemplo, búsqueda semántica opcional). La implementación nueva debe cumplir el `Protocol` `MemoryStore` de `shared/types.py`, vivir en `shared/` y elegirse en `server.py` según la configuración. **No toques `SqliteFtsStore`**: añade la nueva en paralelo, con sus propios tests.

---

## 🚫 Lo que NO va a entrar (sin issue + caso de uso real previo)

- Multi-tenant / multi-usuario.
- UI web propia.
- Sync entre máquinas.
- Auth / ACL (si lo expones a internet, pon un proxy).
- Soporte multimodal (imágenes, PDFs binarios, audio, gráficas).
- Plugins, marketplace, registries dinámicos.

Si crees que tu caso justifica una excepción, abre un issue **antes** del PR con el caso real (no especulativo).

---

## 🤔 Preguntas frecuentes

**¿Por qué SQLite + FTS5 y no una base vectorial (sqlite-vec, ChromaDB…)?**
- Cero infra externa: un único archivo local, sin Docker ni modelos que descargar. BM25 cubre bien el caso real (buscar por términos, nombres e identificadores).

**¿Por qué Python y no Go/Rust/Node?**
- SDK MCP maduro en Python (FastMCP) y `sqlite3` con FTS5 en la librería estándar. Si en el futuro queremos un binario único, se reescribirá.

**¿Por qué no hay UI?**
- KISS. Tu agente es la UI. Para inspección manual, abre el archivo de `DB_PATH` con cualquier cliente SQLite (`sqlite3`, DB Browser for SQLite).

**¿Puedo guardar PDFs / imágenes?**
- No directamente. Extrae el texto antes (OCR / parser) y guarda el texto. La memoria es **texto plano por diseño**.

---

## 📜 Código de conducta

Trato profesional, en cualquier idioma. Críticas a código, no a personas. Si algo del repo te molesta, abre un issue con propuesta concreta.

---

¡Gracias por contribuir! 🙏 Cada PR que hace este proyecto más útil para alguien más es la razón por la que es open source.
