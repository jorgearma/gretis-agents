# Start Cycle

Usa este comando para iniciar un nuevo ciclo de planificacion desde una peticion del usuario.

## Objetivo

Orquestar el flujo completo desde la peticion del usuario hasta dejar el plan listo para aprobacion del operador.

## Instrucciones

1. Valida que el plugin tenga su manifiesto en `.claude/plugin.json`.

2. Si hay un ciclo anterior en curso, ejecuta primero:
   ```
   python3 .claude/hooks/recover-cycle.py
   ```
   Confirma con el usuario antes de resetear si `.claude/runtime/operator-approval.json` tiene `status: approved` o si `.claude/runtime/result.json` existe.

3. Recibe la peticion del usuario e invoca al agente `reader` con la herramienta **Agent** (general-purpose).
   - El prompt al reader debe ser **exactamente** este texto (reemplaza solo `[petición textual del usuario]`):

     ```
     RESTRICCIONES: PROHIBIDO Bash, Glob, Grep, Search, ls. Solo Read y Write. NO planifiques, NO propongas soluciones, NO escribas texto — solo escribe el JSON.

     Lee estos archivos en este orden:
     1. .claude/maps/PROJECT_MAP.md
     2. .claude/maps/PROJECT_MAP.json
     3. Solo los domain MAPs relevantes para la petición:
        - .claude/maps/DB_MAP.json (si toca modelos/tablas)
        - .claude/maps/API_MAP.json (si toca endpoints)
        - .claude/maps/UI_MAP.json (si toca vistas)
        - .claude/maps/QUERY_MAP.json (si toca queries)
        - .claude/maps/SERVICES_MAP.json (si toca integraciones)
        - .claude/maps/JOBS_MAP.json (si toca tareas)

     Después escribe .claude/runtime/reader-context.json con EXACTAMENTE este formato:
     {
       "improved_prompt": "Petición reformulada técnicamente",
       "tech_stack": ["Python", "Flask"],
       "context_summary": "Resumen breve del proyecto y capas afectadas",
       "primary_reader": "ui-reader",
       "selected_readers": ["ui-reader", "db-reader"],
       "maps_used": ["PROJECT_MAP.json", "UI_MAP.json"],
       "files_to_open": [
         {"path": "ruta/archivo.py", "hint": "Por qué es relevante", "key_symbols": ["funcion"], "estimated_relevance": "high", "test_file": null}
       ],
       "files_to_review": [
         {"path": "ruta/otro.py", "hint": "Referencia", "key_symbols": ["otra"], "estimated_relevance": "medium", "test_file": null}
       ],
       "reason": "Por qué estos archivos y dominios",
       "notes": "",
       "status": "ready",
       "dependency_graph": {},
       "problems_in_scope": [],
       "env_vars_needed": [],
       "schema_files": []
     }

     REGLAS: Solo paths que existan en los MAPs. Nunca inventes rutas. key_symbols extraídos de search_keywords o functions del MAP cuando existan. problems_in_scope: array de objetos {"file": "ruta", "type": "God Object", "description": "..."} extraídos de problems del PROJECT_MAP. primary_reader: uno de project-reader, db-reader, query-reader, ui-reader, api-reader, services-reader, jobs-reader.

     Petición del operador: [petición textual del usuario]
     ```

   - **NO agregues ni quites nada** del prompt de arriba. Solo reemplaza la petición.
   - Si el reader devuelve `status: "blocked_no_maps"`, informa al usuario que ejecute `python3 .claude/hooks/analyze-repo.py` y detente.

4. Invoca al agente `planner` con el contenido de `.claude/runtime/reader-context.json`:
   - El planner descompone el trabajo en pasos concretos.
   - Devuelve un JSON compatible con `.claude/schemas/plan.json`.
   - Guarda el resultado en `.claude/runtime/plan.json`.

5. Invoca al agente `writer` con el contenido de `.claude/runtime/plan.json`:
   - El writer transforma el plan en una guia de ejecucion.
   - Devuelve un JSON compatible con `.claude/schemas/execution-brief.json`.
   - Guarda el resultado en `.claude/runtime/execution-brief.json`.
   - Si genera vista humana, guardala en `.claude/runtime/execution-brief.md`.

6. Informa al operador:
   - Muestra un resumen del plan generado.
   - Indica los agentes seleccionados y los pasos principales.
   - Indica que debe aprobar o rechazar antes de ejecutar:
     ```
     python3 .claude/hooks/approve-plan.py approve --by "nombre"
     python3 .claude/hooks/approve-plan.py reject --by "nombre" --notes "motivo"
     ```

## Reglas

- No ejecutes agentes implementadores (frontend/backend) en este comando.
- No avances al paso siguiente si el anterior devuelve un error o JSON invalido.
- Si el reader no puede clasificar la peticion, informa al usuario y detente.
- Si el plan no tiene pasos ejecutables, indica al operador antes de llegar al writer.
