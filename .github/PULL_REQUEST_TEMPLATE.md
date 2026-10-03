## ¿Qué cambia y por qué?

<!-- Conventional Commit en el título del PR (feat:/fix:/refactor:/test:/docs:/chore:)
     Primera línea ≤ 72 chars.
     Aquí: explicá el WHY, no el what — el diff ya muestra el what. -->

## ¿Cómo lo probaste?

<!-- Pasos concretos. Si aplica, incluye el comando exacto que corriste. -->

---

## Checklist

- [ ] Tests para toda lógica nueva (sin tests = sin merge)
- [ ] `ruff check src tests scripts` pasa sin errores (corrido desde `server/`)
- [ ] Título del PR en formato Conventional Commit
- [ ] Identifiers (clases, funciones, variables, archivos) en **inglés**
- [ ] Comentarios y mensajes de commit en **español** (o inglés si es más claro)
- [ ] Una tool nueva = una carpeta nueva en `tools/` — no se modificaron slices existentes
