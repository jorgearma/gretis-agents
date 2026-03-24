# QUERY_MAP.md

**Patrón:** Repository / Manager

## Archivos de acceso a datos

| Archivo                                         | Rol         | Funciones clave                                                                                    |
|-------------------------------------------------|-------------|----------------------------------------------------------------------------------------------------|
| main.py                                         | entry point | create_app, health, manejar_errores_globales                                                       |
| managers/dashboard/gestor_empleados_mixin.py    | data access | empleados_disponibles, monitor_empleados, rendimiento_resumen, rendimiento_empleado                |
| managers/dashboard/gestor_estadisticas_mixin.py | data access | estadisticas                                                                                       |
| managers/dashboard/gestor_pedidos_mixin.py      | data access | metricas, pedidos_activos, alertas, eventos, historial_pedidos                                     |
| managers/dashboard/gestor_picking_mixin.py      | data access | picking_activo, buscar_productos, asignar_picker, reasignar_picker, completar_picking              |
| managers/dashboard/gestor_reparto_mixin.py      | data access | repartidores, mapa, asignar_repartidor, marcar_salida_reparto, marcar_no_entregado                 |
| managers/dashboard/gestor_turnos_mixin.py       | data access | turnos_hoy, turnos_historial, turnos_planificacion, crear_turno, editar_turno                      |
| managers/estado_usuario.py                      | other       | obtener_estado, actualizar_estado                                                                  |
| managers/gestor_dashboard.py                    | data access | —                                                                                                  |
| managers/gestor_empleado.py                     | data access | session, perfil, cambiar_estado, turno_hoy, turnos_proximos                                        |
| managers/gestor_metricas.py                     | data access | session, resumen_operacion, asistencia_hoy, colas_detalle, pedidos_por_estado                      |
| managers/gestor_pedidos.py                      | data access | session, iniciar_pedido, guardar_enlace, hay_pedido_pendiente, obtener_pedido_mas_reciente         |
| managers/gestor_productos.py                    | data access | session, obtener_productos, obtener_producto_por_codigo, productos_admin, actualizar_stock         |
| managers/gestor_redis.py                        | data access | get, set, delete, esta_bloqueado, bloquear_usuario                                                 |
| managers/gestor_usuarios.py                     | data access | session, obtener_usuario, guardar_usuario, obtener_usuario_completo, verificar_usuario             |
| scripts/crear_pedidos_demo.py                   | other       | utc_now, build_run_tag, ensure_role, ensure_categoria, ensure_producto                             |
| scripts/crear_pedidos_demo_pagados.py           | other       | utc_now, build_run_tag, ensure_categoria, ensure_producto, create_demo_user                        |
| scripts/migrar_categorias.py                    | other       | columna_existe, añadir_columnas, migrar_categorias                                                 |
| scripts/migrar_empleado.py                      | other       | run                                                                                                |
| scripts/migrar_sprint2.py                       | other       | columna_existe, tabla_existe, paso1_columnas_empleados, paso2_tablas_nuevas, paso3_roles_iniciales |

## Dependencias query ↔ modelo (git)

- `main.py` siempre cambia con: `managers/gestor_dashboard.py`
- `managers/dashboard/gestor_empleados_mixin.py` siempre cambia con: `managers/gestor_dashboard.py`
- `managers/dashboard/gestor_estadisticas_mixin.py` siempre cambia con: `managers/gestor_dashboard.py`
- `managers/dashboard/gestor_pedidos_mixin.py` siempre cambia con: `managers/gestor_dashboard.py`
- `managers/dashboard/gestor_picking_mixin.py` siempre cambia con: `managers/gestor_dashboard.py`
- `managers/dashboard/gestor_reparto_mixin.py` siempre cambia con: `managers/gestor_dashboard.py`
- `managers/dashboard/gestor_turnos_mixin.py` siempre cambia con: `managers/gestor_dashboard.py`
- `managers/estado_usuario.py` siempre cambia con: `managers/gestor_dashboard.py`
