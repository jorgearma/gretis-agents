# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Plugin base para Claude con agentes especializados, comandos reutilizables y contratos JSON. Diseñado para orquestar planes de operacion a traves de un flujo multi-agente con gate de aprobacion del operador.

## Comandos operativos

```bash
# Validar estructura del plugin
python3 .claude/hooks/pre-commit.py

# Gestion de aprobacion del plan
python3 .claude/hooks/approve-plan.py approve --by "nombre"
python3 .claude/hooks/approve-plan.py reject --by "nombre" --notes "motivo"
python3 .claude/hooks/approve-plan.py reset

# Ejecutar despacho (solo si el plan esta aprobado)
python3 .claude/hooks/execute-plan.py
```

## Arquitectura del flujo

El plugin implementa un pipeline secuencial con gate de aprobacion obligatorio:

```
Usuario → Reader → [readers especializados] → Planner → Writer → Plan Reviewer → [Aprobacion operador] → execute-plan.py → Frontend/Backend → Reviewer
```

### Agentes y sus roles

| Agente | Entrada | Salida |
|--------|---------|--------|
| `reader` (entry point) | Peticion del usuario | `reader-context.json` |
| `planner` | reader-context.json | `plan.json` |
| `writer` | plan.json | `execution-brief.json` + `execution-brief.md` |
| `plan-reviewer` | reader-context.json + plan.json + execution-brief.json | `plan-review.json` |
| `frontend` / `backend` | execution-dispatch.json | `result.json` |
| `reviewer` | result.json + plan.json | `review.json` |

### Readers especializados

El `reader` principal activa solo los readers necesarios segun el dominio de la peticion:

- `project-reader` → arquitectura, modulos, flujo general (`PROJECT_MAP.md`)
- `db-reader` → tablas, modelos, migraciones (`DB_MAP.md`)
- `query-reader` → queries, acceso a datos, performance (`QUERY_MAP.md`)
- `ui-reader` → vistas, componentes, estados UI (`UI_MAP.md`)

Cada reader lee su `*_MAP.md` y devuelve un JSON con `files_to_open` y `files_to_review`. Para requests que cruzan dominios, el reader elige un `primary_reader` de todas formas.

### Gate de aprobacion

Ningun agente ejecutor (frontend/backend) puede actuar sin `operator-approval.json` con `status: "approved"`. El script `execute-plan.py` valida esto antes de generar `execution-dispatch.json`. Los agentes ejecutores verifican `selected_agents` en el dispatch para saber si deben actuar.

### Contratos JSON

Todos los artefactos del flujo tienen schema en `.claude/schemas/`. Los archivos de runtime en `.claude/runtime/` son generados y sobreescritos en cada ciclo — no editar manualmente salvo `operator-approval.json` via hooks.

## Instalacion en un proyecto nuevo

1. Copia esta carpeta al proyecto que usara Claude.
2. Verifica que exista `.claude/plugin.json`.
3. Rellena los `*_MAP.md` en `.claude/maps/` con el contexto real del proyecto.
4. Ejecuta `python3 .claude/hooks/pre-commit.py` para validar la estructura.
