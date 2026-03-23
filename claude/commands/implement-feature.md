# Implement Feature

Usa este comando para ejecutar una implementacion con agentes de Claude.

## Objetivo

Transformar una solicitud aprobada en cambios concretos siguiendo el plan del plugin.

## Instrucciones

- valida primero que el plugin tenga su manifiesto cargado
- lee primero `.claude/runtime/execution-dispatch.json`
- comprueba que `.claude/runtime/operator-approval.json` tenga `status: approved`
- usa `.claude/runtime/execution-brief.json` como guia principal de ejecucion
- usa `.claude/runtime/execution-brief.md` solo como apoyo humano si existe
- comprueba que `.claude/runtime/execution-dispatch.json` tenga `status: ready`
- comprueba que `.claude/runtime/execution-dispatch.json` incluya al agente ejecutor
- identifica el agente implementador principal
- limita el cambio al alcance pedido
- lista artefactos modificados
- devuelve una salida compatible con `.claude/schemas/result.json`
