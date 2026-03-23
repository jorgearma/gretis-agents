# Implement Feature

Usa este comando para ejecutar una implementacion con agentes de Claude.

## Objetivo

Transformar una solicitud aprobada en cambios concretos siguiendo el plan del plugin.

## Instrucciones

- valida primero que el plugin tenga su manifiesto cargado
- lee primero el plan
- si existe, usa `.claude/runtime/execution-brief.md` como guia principal de ejecucion
- comprueba que `.claude/runtime/operator-approval.json` tenga `status: approved`
- comprueba que `.claude/runtime/execution-dispatch.json` incluya al agente ejecutor
- identifica el agente implementador principal
- limita el cambio al alcance pedido
- lista artefactos modificados
- devuelve una salida compatible con `.claude/schemas/result.json`
