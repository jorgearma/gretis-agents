# PROJECT_MAP.md — panchi-bot

Sistema de gestión de pedidos para restaurante: clientes piden por WhatsApp, navegan el menú en web y pagan via Monei. Personal gestiona pedidos desde dashboard con roles diferenciados.

## Stack

| Capa | Tecnología |
|------|------------|
| Backend | Python 3.12 + Flask 3.1 |
| DB | SQL Server (SQLAlchemy 2.0 + pyodbc) |
| Caché / Sesiones | Redis 5.2 (FakeRedis en tests) |
| WhatsApp | Twilio o Meta Cloud API (configurable por env) |
| Pagos | Monei 2.5 |
| Geolocalización | Google Maps API + Shapely 2.1 |
| NLP | spaCy 3.8 (`es_core_news_sm`) |
| Frontend | Jinja2 + HTML/CSS/JS |
| Infra | gunicorn + Nginx + Docker Compose |
| Monitoreo | Sentry SDK 2.54 |

## Estructura

```
panchi-bot/
├── blueprints/     → routing HTTP; solo serialización, sin lógica de negocio
├── controllers/    → lógica de negocio, máquinas de estado
├── managers/       → acceso a datos (DB + Redis)
├── services/       → adaptadores externos (WhatsApp, Maps, tokens)
├── schemas/        → validación de entrada con Pydantic
├── utils/          → helpers sin estado
├── templates/      → Jinja2 por feature (auth/dashboard/empleado/picker/repartidor/productos/macros)
├── static/         → CSS, JS, imágenes
├── tests/          → 395 funciones de test en 31 archivos (pytest + FakeRedis)
├── migrations/     → scripts SQL manuales
├── main.py         → app factory + registra 11 blueprints
├── models.py       → 21 modelos ORM
├── states.py       → enums y reglas de transición de estado
├── database.py     → sesión SQLAlchemy
└── config.py       → carga de variables de entorno
```

## Arquitectura

Dependencias unidireccionales de arriba a abajo. Los blueprints nunca llaman a services directamente.

`BLUEPRINTS → CONTROLLERS → MANAGERS → SERVICES → [SQL Server | Redis | Twilio/Meta | Monei | Google Maps]`

**Redis — 4 usos en la misma instancia:**

| Uso | Clave | Gestor |
|-----|-------|--------|
| Estado de registro | `<telefono>` | gestor_redis |
| Bloqueo anti-spam | `bloqueo:<telefono>` | gestor_redis |
| Token de menú | `<uuid-token>` | token_service |
| Carrito (sesión) | `pedido:<uuid>` | controllers/pago |

**Dos flujos independientes** que comparten managers y DB:
- Bot: `WhatsApp → /webhook → controllers → managers → respuesta WA`
- Dashboard: `Navegador → /dashboard* /picker* /repartidor* → managers → HTML`

## Blueprints registrados

| Blueprint | Prefijo de rutas | Propósito |
|-----------|-----------------|-----------|
| `auth` | `/auth/*` | Login/logout del personal |
| `webhook` | `/webhook`, `/webhook/monei`, `/webhook/meta` | Entrada de mensajes WA y pagos |
| `menu` | `/menu/<token>`, `/confirmacion_pago` | Menú web del cliente |
| `api` | `/api/confirmacion`, `/api/agregar_pedido` | Carrito y pagos |
| `dashboard` | `/dashboard/*` | Panel de operaciones (admin) |
| `picker` | `/picker/*` | Cola de preparación (almacén) |
| `repartidor` | `/repartidor/*` | Cola y tracking de entregas |
| `empleado` | `/empleado/*` | Fichaje y métricas del empleado |
| `productos` | `/productos-admin/*` | Gestión de stock y precios |
| `metricas_operacion` | `/metricas/operacion/*` | Métricas en tiempo real |
| `metricas_analitica` | `/metricas/analitica/*` | Métricas históricas |
| *(global)* | `/health` | Health check: verifica Redis + DB |

## Flujos clave

**Registro (usuario nuevo):**
`/webhook [sin usuario en DB] → controllers/registro.py [máquina de estados en Redis] → SALUDO_INICIAL → ESPERANDO_NOMBRE [spaCy] → ESPERANDO_DIRECCION [Maps+Shapely] → CONFIRMANDO_DIRECCION → guardar en DB → borrar estado Redis`

Rollback posible: si el usuario corrige la dirección, el estado vuelve a `ESPERANDO_DIRECCION`.

**Pedido online:**
`/webhook [usuario en DB] → genera token Redis (TTL) → GET /menu/<token> → POST /api/confirmacion [guarda carrito Redis] → POST /api/agregar_pedido [valida precios vs DB] → crea pedido + pedido_detalles → crea pago Monei → POST /webhook/monei [verifica HMAC] → PAGADO → crea picking_pedido`

**Pedido en efectivo:**
`POST /api/agregar_pedido_efectivo → crea pedido → CONTRA_REEMBOLSO (salta flujo Monei)`

**Flujo operativo (picking → reparto):**
`PAGADO/CONTRA_REEMBOLSO → dashboard asigna picker → EN_PREPARACION → /picker/cola → picker actualiza items → PREPARADO → dashboard asigna repartidor → EN_REPARTO [registro en reparto] → /repartidor/cola → repartidor marca entrega → ENTREGADO`

## Estados del pedido

Camino principal: `PENDIENTE → ENLACE → ENLACE2 → CONFIRMANDO_PAGO → PAGADO → EN_PREPARACION → PREPARADO → EN_REPARTO → ENTREGADO`
Efectivo: `ENLACE2 → CONTRA_REEMBOLSO → PAGADO`
Cancelación: `PAGADO → CANCELADO → REEMBOLSADO`

Todas las transiciones validadas en `states.py`. Todo cambio de estado pasa por `gestor_pedidos.py`, que registra historial en `historial_estados_pedido`.

## Variables de entorno

| Variable | Condición |
|----------|-----------|
| `SECRET_KEY`, `SQL_SERVER`, `SQL_DATABASE`, `SQL_UID`, `SQL_PWD` | Siempre |
| `REDIS_HOST`, `PUBLIC_URL`, `MONEI_API_KEY`, `MONEI_WEBHOOK_SECRET` | Siempre |
| `GOOGLE_MAPS_API_KEY`, `INTERNAL_API_TOKEN`, `WHATSAPP_PROVIDER` | Siempre |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER` | Si `PROVIDER=twilio` |
| `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID`, `META_APP_SECRET`, `META_VERIFY_TOKEN` | Si `PROVIDER=meta` |
| `ALLOWED_ORIGIN`, `SENTRY_DSN`, `CUSTOMER_SUPPORT_PHONE` | Recomendadas |

Valores y formato en `.env.example`.

## Dependencias críticas

| Paquete | Versión | Crítico si falla |
|---------|---------|-----------------|
| SQLAlchemy + pyodbc | 2.0.38 / 5.2.0 | Sistema completo caído |
| redis + fakeredis | 5.2.1 / 2.27.0 | Sin estado entre mensajes / sin tests |
| tenacity | 9.1.4 | Fragilidad ante timeouts en DB y APIs |
| monei | 2.5.2 | Sin cobros online |
| spacy (`es_core_news_sm`) | 3.8.11 | Registro de usuarios fallido |
| shapely | 2.1.2 | Cualquier dirección aceptada sin validar zona |
| pydantic | 2.10.6 | Sin validación de input en webhooks |

⚠ `pyodbc` requiere **ODBC Driver 18 for SQL Server** instalado en el SO (no es pip). En Docker debe incluirse en la imagen base.
⚠ `es_core_news_sm` no se instala con pip: requiere `python -m spacy download es_core_news_sm`.

## Problemas conocidos

**`managers/gestor_dashboard.py` (121 KB) — God Object.** Concentra toda la lógica de agregación del dashboard. Cambios en cualquier área requieren tocar este archivo; imposible hacer tests unitarios granulares. Fix: extraer por dominio (`gestor_pedidos_dashboard.py`, `gestor_turnos.py`, `gestor_reparto_dashboard.py`).

**`managers/gestor_metricas.py` (48 KB) — Sobredimensionado.** Mezcla métricas operacionales (tiempo real) e históricas (analítica) con ciclos de cambio distintos. Fix: separar en `gestor_metricas_operacion.py` y `gestor_metricas_analitica.py`, alineado con la separación ya existente en blueprints.

**Threading sin pool en `blueprints/picker.py`, `repartidor.py`, `dashboard.py`.** `threading.Thread(...).start()` directo, sin pool ni captura de excepciones. Notificaciones WhatsApp fallidas son invisibles en producción. Fix: `ThreadPoolExecutor` con pool acotado + try/except con logging dentro del thread.

**Ruta typo activa: `/webhoo/monei` en `blueprints/webhook.py`.** Alias con error tipográfico expuesto en producción procesando pagos reales (hay un TODO pendiente). Fix: verificar que el dashboard de Monei apunte a `/webhook/monei` y eliminar la ruta errónea.

**Sin CI/CD.** 395 funciones de test que nunca se ejecutan automáticamente. Fix: GitHub Actions con `pytest` en cada push (FakeRedis + mocks ya evitan dependencias externas).

**`openai==1.64.0` en `requirements.txt` sin usar.** Dependencia fantasma de ~50 MB sin ningún `import` en el código. Fix: eliminar.

**Sin rate limiting en `POST /webhook`.** El bloqueo Redis actúa post-procesamiento; un número puede disparar múltiples llamadas a Maps, spaCy y DB antes de bloquearse. Fix: `flask-limiter` por número de teléfono antes de entrar al procesamiento de negocio.

**Lógica de negocio en `blueprints/api.py`.** Validación de precios del carrito contra DB y coordinación de múltiples managers directamente en el blueprint. Fix: extraer a `controllers/carrito.py`.

**SQL Server + pyodbc — acoplamiento al SO.** Imposible usar otro motor en tests de integración. Onboarding complejo en macOS/Linux sin ODBC Driver 18.
