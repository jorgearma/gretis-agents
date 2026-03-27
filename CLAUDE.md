# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Plugin base para Claude con agentes especializados, comandos reutilizables y contratos JSON. Diseñado para orquestar planes de operacion a traves de un flujo multi-agente con gate de aprobacion del operador.

> **Nota de rutas:** En este repositorio el plugin vive en `claude/`. Al instalarlo en un proyecto destino se copia como `.claude/`, que es el path que usan los agentes y hooks en runtime.

## Comandos operativos

```bash
# Validar estructura del plugin
python3 claude/hooks/pre-commit.py

# Validar un artefacto JSON contra su schema
python3 claude/hooks/validate.py <nombre-artefacto>   # ej: plan, reader-context, result

# Analizar repositorio y generar MAPs (requiere aprobacion previa)
python3 claude/hooks/approve-map-scan.py approve --by "nombre"
python3 claude/hooks/analyze-repo.py                        # analiza todo
python3 claude/hooks/analyze-repo.py --maps project,db      # solo esos MAPs
python3 claude/hooks/analyze-repo.py --root /otro/repo      # repo externo
python3 claude/hooks/analyze-repo.py --force                # sin gate (testing)

# Ciclo de planificacion (dos opciones, mismos JSONs de salida)
# Opcion A — desde terminal (eficiente, cero tokens de orquestacion)
python3 claude/hooks/run-cycle.py "descripcion de la tarea"
python3 claude/hooks/run-cycle.py -v "tarea"              # verbose: comandos, JSONs, tiempos
python3 claude/hooks/run-cycle.py --skip-reader "tarea"   # si reader-context.json ya existe
python3 claude/hooks/run-cycle.py --dry-run "tarea"       # ver comandos sin ejecutar
# Opcion B — desde Claude Code (conveniente, todo integrado)
/start-cycle "descripcion de la tarea"

# Ruta rapida para tareas simples (no necesita planner/writer)
python3 claude/hooks/quick-execute.py "descripcion"       # evalua complejidad y despacha
python3 claude/hooks/quick-execute.py "tarea" --force     # forzar aunque score >= 8
python3 claude/hooks/quick-execute.py "tarea" --full-plan # derivar al flujo completo
python3 claude/hooks/quick-execute.py --status            # ver quick-dispatch.json actual
python3 claude/hooks/quick-execute.py "tarea" --dry-run

# Gestion de aprobacion del plan
python3 claude/hooks/approve-plan.py approve --by "nombre"
python3 claude/hooks/approve-plan.py reject --by "nombre" --notes "motivo"
python3 claude/hooks/approve-plan.py replanning             # devuelve al planner con warnings
python3 claude/hooks/approve-plan.py reset

# Ejecutar despacho (solo si el plan esta aprobado)
python3 claude/hooks/execute-plan.py

# Recuperar ciclo interrumpido
python3 claude/hooks/recover-cycle.py status               # ver estado runtime sin modificar
python3 claude/hooks/recover-cycle.py rollback --by "nombre"  # activar rollback_plan
python3 claude/hooks/recover-cycle.py reset --by "nombre"     # limpiar ejecucion, conservar plan
python3 claude/hooks/recover-cycle.py full-reset --by "nombre" # limpiar todo el runtime

# Analisis de consumo de tokens por agente
python3 claude/hooks/token-usage.py                        # resumen ultimas sesiones
python3 claude/hooks/token-usage.py --days 7
python3 claude/hooks/token-usage.py --session <uuid-prefix>
python3 claude/hooks/token-usage.py --json
python3 claude/hooks/token-usage.py --all                  # incluir sesiones sin agente identificado
```

## Arquitectura del flujo

Pipeline secuencial con gate de aprobacion obligatorio:

```
Usuario → Reader → Planner → Writer → [Aprobacion operador] → execute-plan.py → Frontend/Backend
```

Path rapido para tareas simples (sin overhead de planner):
```
Usuario → quick-execute.py → [auto-aprobacion] → Quick-Agent → (opcional) Reviewer
```

### Agentes, modelos y contratos

| Agente | Modelo | Entrada | Salida |
|--------|--------|---------|--------|
| `reader` | claude-sonnet-4-6 | Peticion + MAPs | datos contextuales |
| `planner` | claude-opus-4-6 | reader-context.json + codigo fuente (lectura quirurgica) | `plan.json` |
| `writer` | claude-sonnet-4-6 | plan.json | `execution-brief.json` + `execution-brief.md` |
| `frontend` | — | execution-dispatch.json | `result.json["frontend"]` |
| `backend` | — | execution-dispatch.json | `result.json["backend"]` |
| `quick-agent` | — | quick-dispatch.json | cambios directos |

### Lectura quirurgica del planner

El `planner` (opus) no lee archivos completos. Estrategia para minimizar tokens:
1. Usa `Grep` para localizar simbolos clave y obtener numeros de linea exactos.
2. Lee solo las secciones relevantes (3 lineas antes/despues de cada bloque, fusionando secciones cercanas).
3. Nunca lee archivos completos de >80 lineas salvo que sea el unico archivo del task.

### Gate de aprobacion

Ningun agente ejecutor (frontend/backend) puede actuar sin `operator-approval.json` con `status: "approved"`. `execute-plan.py` valida esto antes de generar `execution-dispatch.json`. Los agentes ejecutores verifican `selected_agents` en el dispatch para saber si deben actuar.

`quick-execute.py` auto-aprueba el gate marcando `approved_by: "quick-execute (auto)"`.

### Complejidad en quick-execute

Score 0–10 calculado con factores aditivos (longitud de descripcion, keywords complejos como "implement/refactor/auth", multiples acciones, alcance masivo "all/every"). Umbrales:

- **0–4:** Simple → fast track OK
- **5–7:** Borderline → advierte pero ejecuta
- **8+:** Complejo → bloquea y recomienda flujo completo (`--force` para saltarse el bloqueo)

### Contratos JSON

Todos los artefactos tienen schema en `claude/schemas/`. Los archivos en `claude/runtime/` son generados y sobreescritos en cada ciclo — no editar manualmente salvo `operator-approval.json` via hooks.

### Generacion de MAPs

`analyze-repo.py` llama a `analyzers/core.py` una sola vez para escanear el repo y luego delega a 7 analizadores especializados (`project`, `db`, `query`, `ui`, `api`, `services`, `jobs`). Cada analizador escribe su `*_MAP.json` y `*_MAP.md` en `claude/maps/`. Para añadir un nuevo analizador: crear `claude/hooks/analyzers/<nombre>.py` con la interfaz `analyze(summary: ProjectSummary) -> dict` y registrarlo en `analyze-repo.py`.

## Instalacion en un proyecto nuevo

1. Copia la carpeta `claude/` al proyecto destino como `.claude/`.
2. Verifica que exista `.claude/plugin.json`.
3. Rellena los `*_MAP.md` en `.claude/maps/` con el contexto real del proyecto (o usa `analyze-repo.py`).
4. Ejecuta `python3 .claude/hooks/pre-commit.py` para validar la estructura.
