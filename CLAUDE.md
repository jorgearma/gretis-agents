# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Plugin base para Claude con agentes especializados, comandos reutilizables y contratos JSON. Diseñado para orquestar planes de operacion a traves de un flujo multi-agente con gate de aprobacion del operador.

> **Nota de rutas:** En este repositorio el plugin vive en `claude/`. Al instalarlo en un proyecto destino se copia como `.claude/`, que es el path que usan los agentes y hooks en runtime.

## Comandos operativos

```bash
# Validar estructura del plugin
python3 claude/hooks/pre-commit.py

# Validar un artefacto JSON contra su schema
python3 claude/hooks/validate.py <nombre-artefacto>   # ej: plan, reader-context

# Analizar repositorio y generar MAPs
python3 claude/hooks/analyze-repo.py                         # todos los MAPs
python3 claude/hooks/analyze-repo.py --maps routing,api,data # solo esos MAPs
python3 claude/hooks/analyze-repo.py --root /otro/repo       # repo externo

# Enriquecer reader-context.json con dependencias reales
python3 claude/hooks/build-subgraph.py

# Correr tests (requiere pytest y jsonschema)
python3 -m pytest claude/hooks/tests/
python3 -m pytest claude/hooks/tests/test_analyzer_api.py   # un solo test file

# Ciclo manual desde Claude Code
/start-cycle "descripcion de la tarea"
```

## Arquitectura del flujo

Pipeline manual recomendado:

```
Usuario → Reader → build-subgraph.py (opcional) → Planner → Writer → Ejecución manual
```

### Agentes, modelos y contratos

| Agente | Modelo | Entrada | Salida |
|--------|--------|---------|--------|
| `reader` | claude-sonnet-4-6 | Peticion + MAPs | `reader-context.json` |
| `planner` | claude-opus-4-6 | reader-context.json + código fuente (lectura quirúrgica) | `plan.json` |
| `writer` | claude-sonnet-4-6 | plan.json | `execution-brief.json` + `execution-brief.md` |
| `frontend` | — | execution-dispatch.json | `result.json["frontend"]` |
| `backend` | — | execution-dispatch.json | `result.json["backend"]` |

Cada agente tiene su prompt en `claude/agents/<nombre>.md` con frontmatter `model:` y reglas estrictas de qué puede leer/escribir.

### Contratos JSON y runtime

- Todos los artefactos tienen schema en `claude/schemas/`.
- Los archivos en `claude/runtime/` se generan y sobreescriben durante el flujo — edítalos a mano solo si estás depurando.
- `plugin.json` en la raíz del plugin es el manifiesto; lista agentes, MAPs, schemas y rutas de runtime.

### Generacion de MAPs

`analyze-repo.py` llama a `analyzers/core.py` una sola vez para escanear el repo y luego delega en los analizadores activos. Cada analizador escribe su mapa en `claude/maps/`. El orden importa: `routing` siempre primero, `dependency` siempre al final.

Analizadores disponibles: `routing`, `api`, `data`, `ui`, `services`, `jobs`, `contract`, `test`, `data_model`, `dependency`.

Para añadir un analizador nuevo: crea `claude/hooks/analyzers/<nombre>.py` con una función `run(files, plugin_dir)` y regístralo en `ANALYZER_MAP` de `analyze-repo.py`.

### Lectura quirurgica del planner

El planner (opus) usa una estrategia para minimizar tokens:
1. Usa `Grep` para localizar símbolos clave y obtener números de línea exactos.
2. Lee solo las secciones relevantes (3 líneas antes/después de cada bloque, fusionando secciones cercanas).
3. Lee archivos completos solo si son `<= 2000` líneas; para los mayores, localiza primero con Grep.
4. Nunca lee el mismo archivo dos veces.

### Guards y hooks de agente

Los archivos `guard-reader.py`, `guard-planner.py`, `guard-writer.py` y los `*-only.py` son hooks que refuerzan las restricciones de cada agente (qué puede leer, qué puede escribir). Son parte del contrato de seguridad del plugin.

## Instalacion en un proyecto nuevo

1. Copia la carpeta `claude/` al proyecto destino como `.claude/`.
2. Verifica que exista `.claude/plugin.json`.
3. Genera o actualiza los mapas con `python3 .claude/hooks/analyze-repo.py`.
4. Usa `python3 .claude/hooks/validate.py <artefacto>` para validar JSONs manualmente.
