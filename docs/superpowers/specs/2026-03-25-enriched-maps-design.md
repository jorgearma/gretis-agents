# Enriched MAP JSONs — Design Spec

**Date:** 2026-03-25
**Status:** Approved
**Goal:** Enriquecer los MAP JSONs generados por `analyze-repo.py` para que los readers entreguen al planner rutas de archivo precisas, símbolos greppables, test files asociados y señales de riesgo — sin tokens innecesarios.

---

## Problema

`PROJECT_MAP.json` actual es solo un routing index (`domains` + `trigger_keywords`). `project-reader.md` espera un campo `modules` con info por archivo (role, search_keywords, symbols, related_to) que no existe. Los MAPs especializados (API, DB, SERVICES) no incluyen `test_file` ni `env_vars`. El resultado: el planner no sabe exactamente qué archivos abrir ni qué tests tocar sin explorar el repo.

---

## Decisión de arquitectura

**Opción B — Centralizar helpers en `core.py` + extender analyzers.**

`core.py` recibe tres helpers nuevos compartidos por todos los analyzers. Cada analyzer sigue siendo dueño de su MAP. Sin post-processors separados.

---

## Sección 1: Helpers nuevos en `core.py`

### `extract_symbols(fi: FileInfo) -> list[dict]`

Wrapper slim sobre el `FileInfo` ya parseado. Devuelve máx 10 símbolos ordenados por línea:

```json
[
  {"name": "AuthManager",  "line": 12, "kind": "class"},
  {"name": "verify_token", "line": 42, "kind": "function"}
]
```

- Usa `fi.symbols_with_lines` (ya disponible en FileInfo) para extraer nombre y línea
- `kind`: `"class"` si el nombre está en `fi.classes`, `"function"` si está en `fi.functions`
- Solo nombres públicos (excluye `_privados` y `__dunder__`)
- Cap en 10 para no inflar el MAP
- Nota: `core.py` ya tiene `build_symbols(fi)` con lógica similar — `extract_symbols` reemplaza o unifica esa función con la interfaz aquí definida

### `find_test_file(rel_path: str, all_files: list[FileInfo]) -> str | None`

Heurística en cascada contra `all_files` (sin tocar disco extra):

1. `tests/test_<stem>.py`
2. `tests/<stem>_test.py`
3. `<dir>/tests/test_<stem>.py`
4. Cualquier archivo cuyo stem contiene `test` + stem del archivo buscado

Devuelve `null` si no hay match. Nunca inventa rutas.

### `detect_problems(files: list[FileInfo]) -> list[dict]`

Escanea todos los archivos y devuelve señales de riesgo:

```json
[
  {"file": "managers/gestor_dashboard.py", "type": "god_object",
   "description": "858 líneas, 23 funciones"},
  {"file": "controllers/payments.py",      "type": "no_tests",
   "description": "sin test asociado"}
]
```

Tipos detectados:
- `god_object`: archivo de lógica con >400 líneas **o** >15 funciones
- `no_tests`: archivo con rol `controller`, `service`, o `data_access` sin `test_file` asociado

---

## Sección 2: PROJECT_MAP — campos nuevos

### Campo `modules`

Índice de archivos por rol. Generado por `project.py` usando los tres helpers de `core.py`.

Claves de `modules` son un **enum fijo**: `controller`, `service`, `data_access`, `model`, `middleware`, `utility`, `entry_point`. Un archivo solo aparece en un rol (el asignado por `FileInfo.role` del walker).

```json
"modules": {
  "controller": [
    {
      "path": "blueprints/auth.py",
      "purpose": "Endpoints de autenticación y gestión de sesión",
      "search_keywords": ["AuthBlueprint", "login", "logout", "verify_token"],
      "symbols": [
        {"name": "AuthBlueprint", "line": 8,  "kind": "class"},
        {"name": "login",         "line": 24, "kind": "function"},
        {"name": "verify_token",  "line": 42, "kind": "function"}
      ],
      "test_file": "tests/test_auth.py",
      "related_to": ["services/auth_service.py", "models/user.py"]
    }
  ],
  "service":     [...],
  "data_access": [...],
  "model":       [...],
  "middleware":  [...],
  "utility":     [...],
  "entry_point": [...]
}
```

- `purpose`: primera línea del docstring del archivo, o inferido del nombre si no hay docstring
- `search_keywords`: stem del archivo + nombres completos de clases + nombres completos de funciones públicas. Sin fragmentos de snake_case ni CamelCase splits. Máx 8.
- `symbols`: via `extract_symbols()`, máx 10
- `test_file`: via `find_test_file()`, `null` si no existe
- `related_to`: imports directos detectados con AST, máx 3 archivos del mismo repo

### Campo `problems`

```json
"problems": [
  {"file": "managers/gestor_dashboard.py", "type": "god_object",
   "description": "858 líneas, 23 funciones"},
  {"file": "controllers/payments.py",      "type": "no_tests",
   "description": "sin test asociado"}
]
```

Generado por `detect_problems()`. Lista vacía `[]` si no hay problemas.

### Campos sin cambios

`domains`, `architecture`, `stack`, `entry_points`, `hotspots`, `cochange` — intactos.

---

## Sección 3: MAPs especializados — campos nuevos

### API_MAP

Agrega `schema_files` al raíz y `test_file` por blueprint:

```json
{
  "framework": "Flask",
  "schema_files": ["schemas/auth.py", "schemas/pedidos.py"],
  "middleware_files": [...],
  "blueprints": [
    {
      "name": "auth",
      "file": "blueprints/auth.py",
      "prefix": "/api/auth",
      "test_file": "tests/test_auth.py",
      "endpoints": [...]
    }
  ],
  "webhooks": [...]
}
```

`schema_files`: archivos con `from pydantic`, `class.*Schema`, o `@dataclass` bajo `schemas/`, `serializers/`, `validators/`. Detectado con regex por `api.py`.

### DB_MAP

Agrega `test_file` por modelo:

```json
"models": [
  {
    "name": "User",
    "table": "users",
    "file": "models/user.py",
    "test_file": "tests/test_user_model.py",
    "fields": [...],
    "relationships": [...]
  }
]
```

### SERVICES_MAP

Agrega `env_vars` y `test_file` por integración:

```json
"integrations": [
  {
    "name": "stripe",
    "type": "payment",
    "file": "services/stripe_service.py",
    "test_file": "tests/test_stripe.py",
    "env_vars": ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"]
  }
]
```

`env_vars`: detectado con regex `os.getenv\(["'](\w+)["']` y `os.environ\[["'](\w+)["']\]` en el archivo. Solo nombres, nunca valores.

### JOBS_MAP y QUERY_MAP

Solo agregan `test_file` por entry. Sin cambios estructurales.

---

## Sección 4: Flujo de información entre agentes

```
analyze-repo.py
│
├── core.py
│     extract_symbols()    → símbolos con línea y kind
│     find_test_file()     → ruta del test asociado
│     detect_problems()    → señales de riesgo
│
├── project.py  → PROJECT_MAP.json
│                   domains, architecture, stack, entry_points
│                   hotspots, cochange
│                   modules: {role → [{path, purpose, search_keywords,
│                                      symbols, test_file, related_to}]}
│                   problems: [{file, type, description}]
│
├── api.py      → API_MAP.json
│                   framework, schema_files, middleware_files
│                   blueprints: [{…, test_file, endpoints}]
│
├── db.py       → DB_MAP.json
│                   models: [{…, test_file}]
│
├── services.py → SERVICES_MAP.json
│                   integrations: [{…, test_file, env_vars}]
│
└── jobs/query  → JOBS_MAP, QUERY_MAP (+ test_file por entry)


reader.md (Haiku)
  1. Lee PROJECT_MAP.json completo
  2. Match trigger_keywords → selecciona sub-readers
  3. Filtra cada MAP (paso 5 ya implementado)
  4. Pasa MAP filtrado + improved_prompt + context_summary


Sub-readers (Haiku)
  Reciben MAP filtrado
  Devuelven files_to_open + files_to_review con:
    path, hint, key_symbols (desde symbols[]), estimated_relevance, test_file


reader-context.json (consolidado)
  files_to_open:      [{path, hint, key_symbols, estimated_relevance, test_file}]
  files_to_review:    [{path, hint, key_symbols, estimated_relevance}]
  problems_in_scope:  [{file, type, description}]
  env_vars_needed:    ["STRIPE_SECRET_KEY", ...]
  schema_files:       ["schemas/auth.py", ...]


planner
  Abre exactamente los archivos listados
  Grep-ea key_symbols directamente (sin leer archivo completo)
  Incluye test_file en el plan automáticamente
  Recibe problems_in_scope antes de planear


writer
  Recibe plan + problems_in_scope
  Advierte en execution-brief sobre archivos problemáticos


agentes especializados (frontend/backend)
  Reciben en execution-dispatch.json:
    env_vars_needed → validan config antes de ejecutar
    test_file por archivo → saben qué tests correr al finalizar
```

---

## Cambios en schemas JSON

| Schema | Cambio |
|---|---|
| `project-map.json` | Agregar `modules` (object con claves enum fijo de rol) y `problems` (array) a `properties` |
| `api-map.json` | Agregar `schema_files` (array, raíz), `test_file` (string, nullable) en blueprint items |
| `db-map.json` | Agregar `test_file` (string, nullable) en model items |
| `services-map.json` | Agregar `test_file` (string, nullable) y `env_vars` (array) en integration items |
| `jobs-map.json` | Agregar `test_file` (string, nullable) en job items |
| `query-map.json` | Agregar `test_file` (string, nullable) en file items |
| `reader-context.json` | Agregar `test_file` en `files_to_open[]` items; agregar campos raíz `problems_in_scope`, `env_vars_needed`, `schema_files` |

---

## Restricciones

- `extract_symbols`: nunca falla — si AST lanza excepción, devuelve `[]`
- `find_test_file`: nunca inventa rutas — solo rutas presentes en `all_files`
- `env_vars`: solo nombres de variables, nunca valores
- `related_to`: solo rutas del mismo repo presentes en `all_files`
- `symbols` cap: 10 por archivo
- `search_keywords` cap: 8 por archivo
- `problems` filtra archivos de test, migrations, seeds — solo archivos de lógica

---

## Archivos a modificar

| Acción | Archivo |
|---|---|
| Modify | `claude/hooks/analyzers/core.py` |
| Modify | `claude/hooks/analyzers/project.py` |
| Modify | `claude/hooks/analyzers/api.py` |
| Modify | `claude/hooks/analyzers/db.py` |
| Modify | `claude/hooks/analyzers/services.py` |
| Modify | `claude/hooks/analyzers/jobs.py` |
| Modify | `claude/hooks/analyzers/query.py` |
| Modify | `claude/schemas/project-map.json` |
| Modify | `claude/schemas/api-map.json` |
| Modify | `claude/schemas/db-map.json` |
| Modify | `claude/schemas/services-map.json` |
| Modify | `claude/schemas/jobs-map.json` |
| Modify | `claude/schemas/query-map.json` |
