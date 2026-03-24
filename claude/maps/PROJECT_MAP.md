# PROJECT_MAP.md — panchi-bot

Bot de WhatsApp para gestión de pedidos de un restaurante en Tarancón (España). Los clientes interactúan por WhatsApp, seleccionan productos desde un menú web y pagan con Monei.

## Stack

| Paquete / Framework | Versión |
|---------------------|---------|
| Flask               | 3.1.0   |
| Pydantic            | 2.10.6  |
| Redis               | 5.2.1   |
| SQLAlchemy          | 2.0.38  |
| Sentry              | 2.54.0  |
| Tenacity            | 9.1.4   |
| Twilio              | 9.4.6   |
| aiohttp             | 3.11.13 |
| httpx               | 0.28.1  |
| requests            | 2.32.3  |

**Lenguajes:** python, javascript

## Estructura

```
panchi-bot/
├── blueprints/ → routing HTTP
├── controllers/ → lógica de negocio
├── docs/ → documentación
├── managers/ → acceso a datos (DB + caché)
├── migrations/ → migraciones DB
├── schemas/ → validación de entrada
├── scripts/ → scripts de utilidad
├── services/ → adaptadores externos / lógica de servicio
├── static/ → assets estáticos
├── templates/ → plantillas HTML
├── tests/ → tests
├── utils/ → helpers sin estado
├── main.py → entry point
├── config.py → config
├── database.py → db connection
├── models.py → model
```

## Arquitectura

CONTROLLERS → SERVICES → MANAGERS → [DB | Redis | APIs externas]

**Entry points:** `main.py`

## Módulos por capa

**Entry Point:** `main.py`
**Service:** `services/token_service.py`, `services/whatsapp_service.py`, `services/maps_service.py`, `tests/test_whatsapp_service.py`, `tests/test_token_service.py`
**Data Access:** `managers/gestor_dashboard.py`, `managers/gestor_pedidos.py`, `managers/gestor_usuarios.py`, `managers/gestor_redis.py`, `managers/gestor_productos.py`, `managers/gestor_empleado.py`, `managers/gestor_metricas.py`, `managers/dashboard/gestor_estadisticas_mixin.py`
**Model:** `models.py`
**Utility:** `managers/dashboard/_helpers.py`, `utils/text_utils.py`
**Config:** `config.py`
**State Machine:** `states.py`, `tests/test_states.py`
**Db Connection:** `database.py`, `tests/test_database.py`
**Migration:** `scripts/migrate_capacidades.py`, `scripts/run_migrations.py`

## Archivos más modificados (git)

| Archivo                         | Commits |
|---------------------------------|---------|
| managers/gestor_dashboard.py    | 48      |
| templates/dashboard/index.html  | 25      |
| templates/repartidor/index.html | 21      |
| CLAUDE.md                       | 19      |
| blueprints/webhook.py           | 17      |
| blueprints/dashboard.py         | 16      |
| main.py                         | 16      |
| templates/picker/index.html     | 15      |
| blueprints/api.py               | 15      |
| models.py                       | 14      |

## Archivos que siempre cambian juntos

- `.claude/runtime/execution-brief.json` ↔ `managers/gestor_dashboard.py`, `templates/dashboard/index.html`, `templates/repartidor/index.html`
- `.claude/runtime/execution-brief.md` ↔ `managers/gestor_dashboard.py`, `templates/dashboard/index.html`, `templates/repartidor/index.html`
- `.claude/runtime/plan.json` ↔ `managers/gestor_dashboard.py`, `templates/dashboard/index.html`, `templates/repartidor/index.html`
- `.claude/runtime/reader-context.json` ↔ `managers/gestor_dashboard.py`, `templates/dashboard/index.html`, `templates/repartidor/index.html`
- `blueprints/empleado.py` ↔ `managers/gestor_dashboard.py`, `templates/dashboard/index.html`, `templates/repartidor/index.html`

## Problemas detectados

- `models.py` — 21 clases en un archivo
- `tests/test_empleado.py` — 11 clases en un archivo
- `tests/test_gestor_metricas.py` — 14 clases en un archivo
- `tests/test_migracion_bd_dashboard.py` — 10 clases en un archivo
