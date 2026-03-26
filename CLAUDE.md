# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Plugin base para Claude con agentes especializados, comandos reutilizables y contratos JSON. Diseñado para orquestar planes de operacion a traves de un flujo multi-agente con gate de aprobacion del operador.

## Comandos operativos

```bash
# Validar estructura del plugin
python3 .claude/hooks/pre-commit.py

# Analizar repositorio y generar MAPs (requiere aprobacion previa)
python3 .claude/hooks/approve-map-scan.py approve --by "nombre"
python3 .claude/hooks/analyze-repo.py                        # analiza todo
python3 .claude/hooks/analyze-repo.py --maps project,db      # solo esos MAPs
python3 .claude/hooks/analyze-repo.py --root /otro/repo      # repo externo
python3 .claude/hooks/analyze-repo.py --force                # sin gate (testing)

# Gestion de aprobacion del plan
python3 .claude/hooks/approve-plan.py approve --by "nombre"
python3 .claude/hooks/approve-plan.py reject --by "nombre" --notes "motivo"
python3 .claude/hooks/approve-plan.py replanning             # devuelve al planner con warnings
python3 .claude/hooks/approve-plan.py reset

# Ejecutar despacho (solo si el plan esta aprobado)
python3 .claude/hooks/execute-plan.py

# Ruta rapida para tareas simples (no necesita planner/writer/plan-reviewer)
python3 .claude/hooks/quick-execute.py

# Despachar reviewer tras ejecucion
python3 .claude/hooks/dispatch-reviewer.py

# Recuperar ciclo interrumpido
python3 .claude/hooks/recover-cycle.py
```

## Arquitectura del flujo

Pipeline secuencial con gate de aprobacion obligatorio:

```
Usuario → Reader → Planner → Writer → Plan-Reviewer → [Aprobacion operador] → execute-plan.py → Frontend/Backend → Reviewer
```

Path rapido para tareas simples (sin overhead de planner):
```
Usuario → Quick-Agent → [Aprobacion operador] → quick-execute.py → ejecucion directa
```

### Agentes y sus roles

| Agente | Entrada | Salida |
|--------|---------|--------|
| `reader` (entry point) | Peticion del usuario | `reader-context.json` |
| `project-reader` | reader-context.json + PROJECT_MAP.json | Partial JSON (files_to_open/review) |
| `db-reader` | reader-context.json + DB_MAP.json | Partial JSON |
| `query-reader` | reader-context.json + QUERY_MAP.json | Partial JSON |
| `ui-reader` | reader-context.json + UI_MAP.json | Partial JSON |
| `planner` | reader-context.json | `plan.json` + `files-read.json` |
| `writer` | plan.json + files-read.json | `execution-brief.json` + `execution-brief.md` |
| `plan-reviewer` | reader-context.json + plan.json + execution-brief.json | `plan-review.json` |
| `frontend` / `backend` | execution-dispatch.json | `result.json` |
| `reviewer` | result.json + plan.json + execution-brief.json | `review.json` |
| `quick-agent` | Peticion simple | `quick-dispatch.json` |

### Readers especializados

El `reader` activa solo los readers necesarios segun dominio. Para requests multi-dominio elige un `primary_reader` de todas formas.

- `project-reader` → arquitectura, modulos, flujo general (`PROJECT_MAP.md`)
- `db-reader` → tablas, modelos, migraciones (`DB_MAP.md`)
- `query-reader` → queries, acceso a datos, performance (`QUERY_MAP.md`)
- `ui-reader` → vistas, componentes, estados UI (`UI_MAP.md`)

### Clarifications (flujo de bloqueo por ambiguedad)

Si el reader detecta ambiguedad de alto riesgo escribe `.claude/runtime/clarifications.json` con `status: "pending"` y bloquea con `status: "blocked_pending_clarification"`. El operador completa las respuestas en el JSON y re-invoca el reader.

### Gate de aprobacion

Ningun agente ejecutor (frontend/backend) puede actuar sin `operator-approval.json` con `status: "approved"`. `execute-plan.py` valida esto antes de generar `execution-dispatch.json`. Los agentes ejecutores verifican `selected_agents` en el dispatch para saber si deben actuar.

### Contratos JSON

Todos los artefactos tienen schema en `.claude/schemas/`. Los archivos en `.claude/runtime/` son generados y sobreescritos en cada ciclo — no editar manualmente salvo `operator-approval.json` via hooks.

El planner cachea el contenido leido en `files-read.json` para que los agentes downstream no relean los mismos archivos.

## Instalacion en un proyecto nuevo

1. Copia esta carpeta al proyecto destino.
2. Verifica que exista `.claude/plugin.json`.
3. Rellena los `*_MAP.md` en `.claude/maps/` con el contexto real del proyecto (o usa `analyze-repo.py`).
4. Ejecuta `python3 .claude/hooks/pre-commit.py` para validar la estructura.
