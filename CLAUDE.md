# Losgretis Claude Plugin

Plugin base para Claude con agentes especializados, comandos reutilizables y contratos JSON.

## Estructura del plugin

- `.claude/plugin.json`: manifiesto del plugin
- `.claude/maps/`: contexto del proyecto dividido por dominio
- `.claude/agents/`: agentes del flujo
- `.claude/agents/readers/`: readers agrupados por contexto
- `.claude/schemas/`: esquemas JSON compartidos
- `.claude/runtime/`: archivos de trabajo generados por el flujo
- `.claude/commands/`: comandos disponibles para Claude
- `.claude/hooks/`: hooks locales del plugin

## Instalacion

1. Copia esta carpeta al proyecto que usara Claude.
2. Verifica que exista `.claude/plugin.json`.
3. Ejecuta `python3 .claude/hooks/pre-commit.py` para validar la estructura.
4. Cuando el plan este listo, usa `python3 .claude/hooks/approve-plan.py approve --by "tu-nombre"` para aprobarlo.

## Flujo del plugin

1. `reader` recibe la peticion del usuario y clasifica el tipo de contexto necesario.
2. `reader` decide que readers debe lanzar y evita activar los que no hagan falta.
3. Los readers elegidos leen su `*_MAP.md` y devuelven un JSON con archivos a abrir y revisar.
4. `planner` usa ese JSON para construir el plan en `plan.json`.
5. `writer` transforma el plan en `.claude/runtime/execution-brief.md` y lo deja pendiente de aprobacion.
6. El operador revisa el plan y usa `.claude/hooks/approve-plan.py` para aprobarlo o rechazarlo.
7. Solo si el operador aprueba, `orchestrator` usa `.claude/hooks/execute-plan.py`.
8. El dispatcher activa de forma simple `frontend` y/o `backend` segun los pasos del plan.
9. `reviewer` participa cuando haga falta.
10. El plugin consolida la salida final en `result.json`.

## Aprobacion del plan

- Aprobar: `python3 .claude/hooks/approve-plan.py approve --by "tu-nombre"`
- Rechazar: `python3 .claude/hooks/approve-plan.py reject --by "tu-nombre" --notes "motivo"`
- Reiniciar a pendiente: `python3 .claude/hooks/approve-plan.py reset`

## Ejecucion simple

- Ejecutar despacho: `python3 .claude/hooks/execute-plan.py`
- El script revisa `.claude/runtime/plan.json` y `.claude/runtime/operator-approval.json`
- Si el plan esta aprobado, genera `.claude/runtime/execution-dispatch.json` con `frontend` y/o `backend`
