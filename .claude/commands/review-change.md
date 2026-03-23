# Review Change

Usa este comando para revisar una implementacion finalizada.

## Objetivo

Encontrar errores, regresiones y riesgos antes de dar por bueno el cambio.

## Instrucciones

- valida primero que el plugin tenga su manifiesto cargado
- lee `.claude/runtime/plan.json` y `.claude/runtime/execution-brief.json`
- compara el cambio con el plan
- prioriza problemas funcionales sobre detalles cosmeticos
- identifica pruebas faltantes
- devuelve una salida compatible con `.claude/schemas/review.json`
