# Spec: Refactor analyze-repo — Scripts por dominio + PROJECT_MAP como routing index

**Fecha:** 2026-03-25
**Estado:** aprobado por operador

---

## Problema

`analyze-repo.py` genera un `PROJECT_MAP.json` que no da suficiente información al `reader.md` para decidir qué sub-readers activar. El PROJECT_MAP.json actual mezcla routing con detalles de archivos, crece con cada dominio nuevo, y no tiene una señal clara de qué readers existen ni qué keywords los disparan.

---

## Objetivo

1. Rediseñar `PROJECT_MAP.json` como un **índice de routing ligero** que el reader puede leer en un segundo y decidir qué sub-readers activar.
2. Refactorizar `analyze-repo.py` en un orquestador + módulos por dominio, uno por MAP.
3. Añadir 3 nuevos MAPs: `API_MAP.json`, `SERVICES_MAP.json`, `JOBS_MAP.json`.

---

## Arquitectura de archivos

```
.claude/hooks/
  analyze-repo.py          ← orquestador (CLI sin cambios)
  analyzers/
    __init__.py
    core.py                ← walk, AST, git history, pathspec (lógica compartida)
    project.py             ← genera PROJECT_MAP.json
    db.py                  ← genera DB_MAP.json
    query.py               ← genera QUERY_MAP.json
    ui.py                  ← genera UI_MAP.json
    api.py                 ← genera API_MAP.json (nuevo)
    services.py            ← genera SERVICES_MAP.json (nuevo)
    jobs.py                ← genera JOBS_MAP.json (nuevo)

.claude/maps/
  PROJECT_MAP.json         ← routing index (rediseñado)
  DB_MAP.json
  QUERY_MAP.json
  UI_MAP.json
  API_MAP.json             ← nuevo
  SERVICES_MAP.json        ← nuevo
  JOBS_MAP.json            ← nuevo

.claude/schemas/
  api-map.json             ← nuevo (JSON Schema para validación)
  services-map.json        ← nuevo
  jobs-map.json            ← nuevo
```

---

## Componentes

### `analyzers/core.py`

Centraliza toda la lógica de extracción compartida. Expone:

- `walk_repo(root) → list[FileInfo]` — recorre el repo, parsea AST Python, regex JS/TS, clasifica roles
- `detect_stack(root) → dict` — extrae stack y versiones desde manifests
- `git_cochange(root) → dict` — matriz de co-cambio desde git log (devuelve `{}` si no hay historial git)
- `git_hotspots(root) → list` — archivos más modificados (devuelve `[]` si no hay historial git)

**Tipos `FileInfo` y `FunctionInfo`** — ambos viven en `core.py` y todos los analyzers los importan desde ahí:

```python
@dataclass
class FunctionInfo:
    name: str
    start_line: int
    end_line: int
    params: list[str]
    return_type: str
    decorators: list[str]
    complexity: int    # líneas de código
    is_async: bool

@dataclass
class FileInfo:
    rel_path: str           # ruta relativa al root del repo
    language: str           # "python" | "typescript" | "javascript" | etc.
    role: str               # rol inferido por heurísticas (ver ROLE_PATTERNS)
    size: int               # bytes
    classes: list[str]
    functions: list[str]
    exports: list[str]
    imports_internal: list[str]
    imports_external: list[str]
    has_db_access: bool
    docstring: str
    query_examples: list[str]
    symbols_with_lines: dict[str, int]   # nombre → nº de línea
    function_infos: list[FunctionInfo]
```

El orquestador llama `core.walk_repo()` **una sola vez** y pasa el resultado a todos los analyzers. Ningún analyzer relanza el walk.

**Interfaz que debe implementar cada analyzer:**

```python
def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera y escribe el MAP en .claude/maps/. Devuelve el dict generado."""
```

**Modo standalone:** cada `analyzers/X.py` tiene un bloque `if __name__ == "__main__"` que llama `core.walk_repo()` internamente y luego llama a su propia función `run()`. El resultado es idéntico al modo orquestado porque ambos pasan por la misma `run()`.

El argumento `--root` en modo standalone tiene el mismo default que el orquestador: el directorio que contiene `.claude/`. Si se omite, el script busca `.claude/` subiendo desde el directorio actual.

```bash
python3 .claude/hooks/analyzers/api.py --root /mi/proyecto
python3 .claude/hooks/analyzers/api.py   # usa el default
```

**Edge case — dominio sin archivos:** si un analyzer no encuentra archivos relevantes, escribe el MAP igualmente con arrays vacíos (nunca omite el archivo). Esto asegura que `pre-commit.py` no falle por archivo ausente. Ejemplo mínimo para jobs: `{"scheduler": null, "jobs": [], "queues": []}`.

---

### `analyzers/project.py` — `PROJECT_MAP.json`

Genera el routing index. **No incluye** el bloque `modules` archivo por archivo.

**Schema de salida:**
```json
{
  "name": "string",
  "description": "string",
  "architecture": "string (una línea: LAYER → LAYER → ...)",
  "stack": { "NombreTech": "versión" },
  "entry_points": ["archivo.py"],
  "domains": {
    "<nombre_dominio>": {
      "map": "NOMBRE_MAP.json",
      "reader": "nombre-reader",
      "summary": "descripción breve del contenido del MAP",
      "trigger_keywords": ["keyword1", "keyword2"]
    }
  },
  "cochange": {},
  "hotspots": []
}
```

**Validez del MAP:** el MAP se considera válido (no vacío) si `domains` tiene al menos una clave. El check anterior sobre `modules` y `structure` en `reader.md` paso 2 se reemplaza por este criterio.

---

### `analyzers/api.py` — `API_MAP.json`

Detecta y extrae blueprints Flask / routers Express/FastAPI, endpoints HTTP, webhooks y middleware de auth.

**Detección de `auth_required`:** se marca `true` si el endpoint tiene alguno de estos decoradores o patrones: `@login_required`, `@jwt_required`, `@token_required`, `@require_auth`, `@permission_required`, o si está envuelto en un blueprint registrado con `before_request` que contiene la palabra `auth`.

**Detección de webhooks vs endpoints normales:** un endpoint se clasifica como `webhook` si su ruta contiene `/webhook` o `/callback`, o si el nombre de la función contiene `webhook` o `callback`. El resto son endpoints normales dentro de `blueprints`.

**`route`:** siempre es la ruta del decorador tal como aparece en el código (relativa al blueprint prefix). El `prefix` del blueprint se incluye por separado para que el lector pueda reconstruir la ruta absoluta si necesita.

**Schema de salida:**
```json
{
  "framework": "Flask | FastAPI | Express | null",
  "blueprints": [
    {
      "name": "string",
      "file": "string",
      "prefix": "string",
      "endpoints": [
        {
          "function": "string",
          "line": 0,
          "methods": ["GET"],
          "route": "string",
          "auth_required": false
        }
      ]
    }
  ],
  "webhooks": [
    {
      "file": "string",
      "function": "string",
      "line": 0,
      "route": "string",
      "methods": ["POST"]
    }
  ],
  "middleware_files": ["string"]
}
```

**Edge case — framework no detectado:** `"framework": null`, `blueprints: []`, `webhooks: []`.

---

### `analyzers/services.py` — `SERVICES_MAP.json`

Detecta integraciones externas por imports de SDKs conocidos y patrones de env vars.

**Schema de salida:**
```json
{
  "integrations": [
    {
      "name": "string",
      "type": "sms | email | payments | storage | cache | queue | monitoring | other",
      "files": ["string"],
      "functions": ["string"],
      "env_vars": ["string"]
    }
  ]
}
```

**Tipos de integración mapeados:**
- `sms`: twilio, vonage, sinch
- `email`: sendgrid, mailgun, ses
- `payments`: stripe, monei, paypal, braintree
- `storage`: boto3/s3, gcs, azure-storage
- `cache`: redis, memcached
- `queue`: celery, rq, sqs, rabbitmq
- `monitoring`: sentry-sdk, datadog, newrelic

**Edge case — ninguna integración detectada:** `{"integrations": []}`.

---

### `analyzers/jobs.py` — `JOBS_MAP.json`

Detecta scheduler y tareas programadas.

**Schema de salida:**
```json
{
  "scheduler": "celery | rq | apscheduler | cron | null",
  "jobs": [
    {
      "file": "string",
      "function": "string",
      "trigger": "manual | cron | interval | event | startup",
      "schedule": "string | null",
      "description": "string"
    }
  ],
  "queues": ["string"]
}
```

- `schedule`: expresión cron o intervalo en texto legible (`"*/5 * * * *"`, `"every 10 minutes"`). `null` si es manual o no determinable.
- `trigger` desconocido → usar `"manual"`.
- **Edge case — ningún scheduler:** `{"scheduler": null, "jobs": [], "queues": []}`.

---

### `analyze-repo.py` (orquestador)

CLI sin cambios: `--root`, `--maps project,db,query,ui,api,services,jobs`, `--force`.

Flujo interno:
1. Valida aprobación (`map-scan-approval.json`) salvo `--force`
2. Llama `core.walk_repo()` y `core.detect_stack()` una vez
3. Para cada MAP solicitado, importa el analyzer correspondiente y llama su `run(root, files, stack)`
4. Cada analyzer escribe su MAP en `.claude/maps/`

---

## Cambios en `reader.md`

### Paso 2 — check de MAP vacío (reemplazar completo)

Reemplazar la condición actual que comprueba `modules` y `structure` por:

> El MAP es **válido** si `domains` existe y tiene al menos una clave. Si el archivo no existe, `domains` está ausente, o `domains` es `{}`, devolver `status: "blocked_no_maps"`.
>
> Si el MAP es válido, extraer:
> - `tech_stack` desde `project_map.stack`
> - `architecture` desde `project_map.architecture`
> - `entry_points` desde `project_map.entry_points`
> - `domains` completo para el routing del paso 4

### Paso 3 — construir `context_summary` (reemplazar completo)

Reemplazar la instrucción que usa `project_map.modules` y `project_map.structure` por:

> Con `improved_prompt` y los datos de `PROJECT_MAP.json`, construye `context_summary`: párrafo conciso (3-6 líneas) que describe:
> - tipo de proyecto, propósito y stack principal (desde `description` + `stack`)
> - capa o flujo arquitectónico general (desde `architecture`)
> - dominios activos en el proyecto (desde las claves de `domains`)
> - cualquier restricción arquitectónica importante que pueda inferirse del stack

### Paso 4 — routing dinámico desde `domains` (reemplazar completo)

Eliminar las condiciones hardcodeadas ("Si la petición afecta persistencia → lee DB_MAP..."). Reemplazar por:

> Para cada dominio en `PROJECT_MAP.domains`, extrae sus `trigger_keywords`. Haz match **case-insensitive** (substring match) contra los tokens del `improved_prompt`. Si al menos **1 keyword** de un dominio tiene coincidencia, incluye ese dominio en `selected_readers`. Si ningún dominio hace match, activa solo `project-reader` como fallback.
>
> Para cada dominio seleccionado, lee el archivo indicado en `domains[nombre].map`. Si el archivo existe y no está vacío, úsalo. Si está vacío o no existe, continúa sin él.

### Reglas de enrutado — añadir los 3 nuevos readers

```
- api-reader      → endpoints HTTP, rutas, blueprints, webhooks, contratos de API
- services-reader → integraciones externas, SDKs de terceros, env vars de credenciales
- jobs-reader     → tareas programadas, queues, workers, crons
```

### Paso 5 — reglas de filtrado para los nuevos MAPs

**Para API_MAP.json:**
- Conserva en `blueprints` solo los que tienen endpoints cuya `route` o `function` coincide con los conceptos de la petición.
- Conserva siempre: `framework`, `middleware_files`.
- Incluye `webhooks` solo si la petición menciona webhooks o integraciones entrantes.

**Para SERVICES_MAP.json:**
- Conserva en `integrations` solo las que coinciden con el servicio o `type` mencionado en la petición.

**Para JOBS_MAP.json:**
- Conserva en `jobs` solo los que coinciden con la función o trigger mencionado.
- Conserva siempre: `scheduler`.

---

## Nuevos archivos de agentes reader

Crear los 3 nuevos reader agents en `.claude/agents/readers/`:

- `api-reader.md` — instrucciones para leer `API_MAP.json` y devolver `files_to_open`/`files_to_review` enfocados en endpoints, blueprints y middleware
- `services-reader.md` — instrucciones para leer `SERVICES_MAP.json` y devolver archivos de integración relevantes
- `jobs-reader.md` — instrucciones para leer `JOBS_MAP.json` y devolver archivos de jobs/queues relevantes

El contenido de cada uno sigue el mismo patrón que los readers existentes (`db-reader.md`, `ui-reader.md`): recibe `improved_prompt`, `context_summary` y el MAP filtrado; devuelve `files_to_open` y `files_to_review` con `hint`, `key_symbols` y `estimated_relevance`.

---

## Cambios en `pre-commit.py`

Actualizar cuatro elementos:

1. **`REQUIRED_PATHS`** — añadir los 3 nuevos MAPs (`API_MAP.json`, `SERVICES_MAP.json`, `JOBS_MAP.json`) y los 3 nuevos readers (`.claude/agents/readers/api-reader.md`, `services-reader.md`, `jobs-reader.md`)
2. **`JSON_FILES`** — añadir los 3 nuevos MAPs
3. **`MAP_ARTIFACTS`** — añadir entradas para `api-map`, `services-map`, `jobs-map` con sus schemas
4. **`schemas/project-map.json`** — actualizar para reflejar el nuevo schema de `PROJECT_MAP.json`: reemplazar las propiedades `modules` y `structure` por `domains`

---

## Criterios de éxito

1. `python3 analyze-repo.py` genera los 7 MAPs sin errores
2. `python3 analyzers/api.py --root /proyecto` corre de forma independiente y produce output idéntico al orquestado
3. `PROJECT_MAP.json` tiene sección `domains` con los 7 dominios y sus `trigger_keywords`
4. El reader activa los readers correctos basándose solo en `trigger_keywords` de `domains` (match case-insensitive, mínimo 1 keyword)
5. `API_MAP.json` captura todos los blueprints y endpoints del proyecto analizado
6. `SERVICES_MAP.json` detecta todas las integraciones externas con sus `type` y `env_vars`
7. `JOBS_MAP.json` detecta scheduler y jobs; si no hay scheduler, escribe `{"scheduler": null, "jobs": [], "queues": []}`
8. `pre-commit.py` pasa con los 7 MAPs presentes
9. El reader devuelve `status: "blocked_no_maps"` si `domains` está vacío o ausente
10. El reader activa `project-reader` como fallback si ningún dominio hace match con la petición
