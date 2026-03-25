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
```

---

## Componentes

### `analyzers/core.py`

Centraliza toda la lógica de extracción compartida. Expone:

- `walk_repo(root) → list[FileInfo]` — recorre el repo, parsea AST Python, regex JS/TS, clasifica roles
- `detect_stack(root) → dict` — extrae stack y versiones desde manifests
- `git_cochange(root) → dict` — matriz de co-cambio desde git log
- `git_hotspots(root) → list` — archivos más modificados

El orquestador llama `core.walk_repo()` **una sola vez** y pasa el resultado a todos los analyzers. Ningún analyzer relanza el walk.

### `analyzers/project.py`

Genera `PROJECT_MAP.json` como routing index. **No incluye** el bloque `modules` archivo por archivo — ese detalle vive en los MAPs de dominio.

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

La sección `domains` es el corazón del routing: el reader hace match de keywords del prompt contra `trigger_keywords` de cada dominio para decidir qué readers activar.

### `analyzers/api.py` — `API_MAP.json`

Detecta y extrae:
- Blueprints Flask / routers Express/FastAPI con su prefix y archivo
- Endpoints: función, línea, métodos HTTP, ruta, si requiere auth
- Webhooks identificados por nombre/patrón
- Archivos de middleware y decoradores de auth

**Schema de salida:**
```json
{
  "framework": "string",
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
    { "file": "string", "function": "string", "line": 0 }
  ],
  "middleware_files": ["string"]
}
```

### `analyzers/services.py` — `SERVICES_MAP.json`

Detecta integraciones externas por:
- Imports de SDKs conocidos (twilio, stripe, boto3, httpx con URLs externas)
- Variables de entorno de credenciales (patrones `_KEY`, `_SECRET`, `_TOKEN`, `_URL`)
- Archivos en carpetas `services/`, `adapters/`, `providers/`

**Schema de salida:**
```json
{
  "integrations": [
    {
      "name": "string",
      "files": ["string"],
      "functions": ["string"],
      "env_vars": ["string"]
    }
  ]
}
```

### `analyzers/jobs.py` — `JOBS_MAP.json`

Detecta:
- Scheduler presente (Celery, RQ, APScheduler, cron, none)
- Jobs: archivo, función, tipo de trigger (manual, cron, event), descripción desde docstring
- Queues definidas

**Schema de salida:**
```json
{
  "scheduler": "string | none",
  "jobs": [
    {
      "file": "string",
      "function": "string",
      "trigger": "manual | cron | event",
      "description": "string"
    }
  ],
  "queues": ["string"]
}
```

### `analyze-repo.py` (orquestador)

CLI sin cambios: `--root`, `--maps project,db,query,ui,api,services,jobs`, `--force`.

Flujo interno:
1. Valida aprobación (`map-scan-approval.json`) salvo `--force`
2. Llama `core.walk_repo()` y `core.detect_stack()` una vez
3. Para cada MAP solicitado, importa el analyzer correspondiente y llama su `run(root, files, stack)`
4. Cada analyzer escribe su MAP en `.claude/maps/`

Cada archivo `analyzers/X.py` tiene `if __name__ == "__main__"` con argparse para correrlo solo:
```bash
python3 .claude/hooks/analyzers/api.py --root /mi/proyecto
```

---

## Cambios en `reader.md`

El paso 2 ya no extrae `modules` de PROJECT_MAP.json. En su lugar:

- Lee `domains` para obtener la lista de MAPs disponibles y sus `trigger_keywords`
- Hace match de keywords del `improved_prompt` contra cada dominio
- Activa los readers cuyos `trigger_keywords` tienen coincidencia

El paso 4 desaparece como lista hardcodeada — el routing es dinámico desde `domains`.

---

## Compatibilidad

- CLI de `analyze-repo.py` no cambia — el operador no nota diferencia
- Los MAPs existentes (DB, QUERY, UI) mantienen su schema interno actual
- El `pre-commit.py` necesita actualizar la lista de MAPs válidos para incluir los 3 nuevos

---

## Criterios de éxito

1. `python3 analyze-repo.py` genera los 7 MAPs sin errores
2. `python3 analyzers/api.py --root /proyecto` corre de forma independiente
3. `PROJECT_MAP.json` tiene sección `domains` con los 7 dominios y sus `trigger_keywords`
4. El reader activa los readers correctos basándose solo en `trigger_keywords` de `domains`
5. `API_MAP.json` captura todos los blueprints y endpoints del proyecto analizado
6. `SERVICES_MAP.json` detecta todas las integraciones externas con sus env_vars
