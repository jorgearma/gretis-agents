# DB_MAP.md

**ORM:** SQLAlchemy
**Infraestructura:** SQLAlchemy, Redis

## Modelos

| Modelo                | Archivo                      | Tabla / Colección         | Campos                                                                                                                         | Relaciones                                      |
|-----------------------|------------------------------|---------------------------|--------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------|
| AuditLog              | models.py                    | audit_log                 | id:Integer, pedido_id:Integer, empleado_id:Integer, accion, detalles:Text, created_at:DateTime                                 | pedido, empleado                                |
| Ausencia              | models.py                    | ausencias                 | id:Integer, empleado_id:Integer, fecha:Date, tipo, estado, aprobado_por:Integer…                                               | empleado, aprobador                             |
| Categoria             | models.py                    | categorias                | id:Integer, nombre, orden_display:Integer, activa:Boolean                                                                      | productos                                       |
| CheckIn               | models.py                    | check_ins                 | id:Integer, empleado_id:Integer, fecha:Date, inicio:DateTime, fin:DateTime, turno_id:Integer…                                  | empleado, turno, tramos                         |
| Empleado              | models.py                    | empleados                 | EmpleadoID:Integer, rol_id:Integer, Nombre, Apellido, Email, Telefono…                                                         | rol, pickings, repartos, incidencias_asignadas… |
| EmpleadoCapacidad     | models.py                    | empleado_capacidades      | id:Integer, empleado_id:Integer, rol                                                                                           | empleado                                        |
| GestorDashboard       | managers/gestor_dashboard.py | gestordashboard           | —                                                                                                                              | —                                               |
| HistorialEstadoPedido | models.py                    | historial_estados_pedido  | id:Integer, pedido_id:Integer, estado_anterior, estado_nuevo, cambiado_en:DateTime, notas…                                     | pedido                                          |
| Incidencia            | models.py                    | incidencias               | id:Integer, pedido_id:Integer, cliente_id:Integer, asignado_a:Integer, tipo, descripcion:Text…                                 | pedido, cliente, asignado                       |
| MetricaDiariaEmpleado | models.py                    | metricas_diarias_empleado | id:Integer, empleado_id:Integer, fecha:Date, rol, horas_trabajadas_min:Integer, pedidos_completados:Integer…                   | empleado                                        |
| Pago                  | models.py                    | pagos                     | id:Integer, pedido_id:Integer, proveedor, referencia_externa, estado, importe…                                                 | pedido                                          |
| Pedido                | models.py                    | pedidos                   | PedidoID:Integer, ClienteID:Integer, FechaCreacion:DateTime, FechaActualizacion:DateTime, Estado, Total…                       | cliente, detalles, pagos, historial_estados…    |
| PedidoDetalle         | models.py                    | pedido_detalles           | DetalleID:Integer, PedidoID:Integer, ProductoID:Integer, Cantidad:Integer, PrecioUnitario, NombreProducto…                     | pedido, producto, picking_item                  |
| PedidoInput           | schemas/twilio.py            | pedidoinput               | —                                                                                                                              | —                                               |
| PickingItem           | models.py                    | picking_items             | id:Integer, picking_id:Integer, pedido_detalle_id:Integer, estado, cantidad_encontrada:Integer, producto_sustituto_id:Integer… | picking, pedido_detalle, producto_sustituto     |
| PickingPedido         | models.py                    | picking_pedido            | id:Integer, pedido_id:Integer, empleado_id:Integer, estado, iniciado_en:DateTime, completado_en:DateTime…                      | pedido, empleado, items                         |
| Producto              | models.py                    | productos                 | ProductoID:Integer, categoria_id:Integer, Nombre, Precio, Categoria, Ingredientes…                                             | categoria_rel, detalles                         |
| Reparto               | models.py                    | repartos                  | id:Integer, pedido_id:Integer, repartidor_id:Integer, estado, hora_salida:DateTime, hora_estimada_entrega:DateTime…            | pedido, repartidor                              |
| Rol                   | models.py                    | roles                     | id:Integer, nombre, descripcion                                                                                                | empleados                                       |
| SolicitudCambioTurno  | models.py                    | solicitudes_cambio_turno  | id:Integer, turno_cedido_id:Integer, solicitante_id:Integer, sustituto_id:Integer, estado, aprobado_por:Integer…               | turno_cedido, solicitante, sustituto, aprobador |
| TramoTurno            | models.py                    | tramos_turno              | id:Integer, check_in_id:Integer, rol, inicio:DateTime, fin:DateTime                                                            | check_in                                        |
| Turno                 | models.py                    | turnos                    | id:Integer, empleado_id:Integer, fecha:Date, hora_inicio:Time, hora_fin:Time, notas…                                           | empleado, turno_origen                          |
| Usuario               | models.py                    | usuarios                  | id:Integer, nombre, numero_cliente, direccion                                                                                  | pedidos, incidencias                            |
| UsuarioDatos          | schemas/usuario.py           | usuariodatos              | —                                                                                                                              | —                                               |
| WebhookRequest        | schemas/twilio.py            | webhookrequest            | —                                                                                                                              | —                                               |

## Migraciones

- `scripts/migrate_capacidades.py`
- `scripts/run_migrations.py`
- `scripts/seed_pedidos_prueba.sql`
- `scripts/seed_simple.sql`
- `scripts/seed_turnos_ui.sql`

**Conexión DB:** `database.py`, `tests/test_database.py`
