# JSON Navigator Skill

Eres experto en extraer información estructurada de JSONs. Tu trabajo es interpretar los MAPs del sistema y mapearlos a instrucciones técnicas precisas.

## MAPs del Sistema — Estructura y Lectura

### 1. ROUTING_MAP.json — El director de tráfico

**Estructura:**
```
project_summary
  ├─ name, languages, stack, architecture
  └─ entry_points: puntos de entrada de la aplicación
domains[]
  ├─ name: "api", "data", "ui", "services", "jobs"
  ├─ keywords: palabras clave para detectar relevancia
  ├─ negative_keywords: palabras que descartan el dominio
  ├─ priority: orden de búsqueda
  └─ preferred_indexes: qué DOMAIN_INDEX leer si este dominio es seleccionado
default_constraints: restricciones globales del proyecto
```

**Estrategia de lectura:**
1. Para cada palabra en el prompt del operario, busca match en `keywords` de cada dominio
2. Descarta falsos positivos con `negative_keywords`
3. Ordena resultados por `priority` (menor = más relevante)
4. Anota `preferred_indexes` del dominio seleccionado — esos son los archivos que leerás después
5. Extrae `default_constraints` — van **siempre** a constraints del output

**Ejemplo:**
- Prompt: "agregar validación en el endpoint de login"
- Match: dominio "api" (keywords: ["endpoint", "route", "controller", ...])
- Descarta: "ui" tiene negative_keyword "frontend"
- Resultado: DOMAIN_INDEX_api.json es tu siguiente lectura
- Constraints globales: cópiadas desde default_constraints

---

### 2. DOMAIN_INDEX_*.json — El inventario de candidatos

Mismo schema para todos: api, data, ui, services, jobs.

**Estructura uniforme:**
```
domain: "api" / "data" / "ui" / ...
candidates[]  ← AQUÍ VA TODO
  ├─ path: "ruta/del/archivo.py"
  ├─ role: "controller", "service", "data_access", "model", "model_validator", etc
  ├─ purpose: "descripción legible para el planner"
  ├─ key_symbols: ["FunctionName", "ClassName"] ← lo que el planner debe buscar con Grep
  ├─ symbols[]: [{name, line, end_line, kind}] ← rango exacto si necesita lectura quirúrgica
  ├─ test_files: ["tests/test_archivo.py", ...] ← pruebas asociadas
  ├─ related_paths: ["otro/archivo.py", ...] ← impacto indirecto
  ├─ contracts: ["POST /route", "model:X", "env:VAR"] ← lo que no se puede romper
  └─ open_priority: "seed" | "review"
     ├─ "seed" → donde ocurre el cambio DIRECTO → files_to_open
     └─ "review" → impacto INDIRECTO → files_to_review
```

**Estrategia de lectura:**
1. **Selecciona seeds:** todos los candidatos con `open_priority: "seed"`
2. **Extrae related:** para cada seed, incluye su `related_paths` en files_to_review
3. **Agrupa por role:** agrupa candidates por `role` para detectar patrones
4. **Prioriza por confidence:** ordena por cantidad de confidence_signals

**Mapeo a output:**
- `open_priority: "seed"` → entra en `files_to_open` (máximo 3-5 archivos)
- `open_priority: "review"` → entra en `files_to_review` (resto de candidatos relevantes)
- `key_symbols` → buscar estos en el código fuente (Grep del planner)
- `test_files[0]` → el test más reciente/relevante
- `purpose` → convertir a `hint` en el JSON de salida

**Patrones típicos:**
- Controller → Service → Data → Model (cadena vertical de responsabilidad)
- Un cambio en Model afecta: test_files + related_paths (cascada)
- `contracts: ["POST /route"]` significa que este archivo rompe contratos si cambia

---

### 3. CONTRACT_MAP.json — Las zonas de peligro

**Estructura:**
```
endpoints[]
  ├─ method, full_path: "POST", "/api/users/{id}"
  ├─ owner: "UserController" (quién lo implementa)
  └─ breaking_if_changed: true ← PROHIBIDO CAMBIAR FIRMA
payload_schemas[]
  ├─ file: "api/schemas/user.py"
  ├─ classes: ["UserSchema", "UserResponseSchema"]
  ├─ used_by: ["/users/list", "/users/get"]
  └─ breaking_if_changed: true ← NO TOCAR CAMPOS PÚBLICOS
env_vars[]
  ├─ name: "DATABASE_URL", "STRIPE_SECRET"
  └─ owner: "services/database.py"
legacy_contracts[]
  ├─ description: "No renombrar tabla users → afectaría migraciones"
  └─ file, line: ubicación exacta de la restricción
```

**Estrategia de lectura:**
- Busca endpoints cuyo `full_path` matchea con la petición
- Si `breaking_if_changed: true` → generar constraint explícito
- Busca env_vars cuyo `owner` matchea con archivos seleccionados en Turno 2
- Busca schemas usados por los endpoints encontrados
- Todo esto → constraints en el output (restricciones que el planner DEBE respetar)

**Ejemplo:**
- Encontraste: `POST /api/users/{id}` con breaking_if_changed: true
- Constraint generado: "No cambiar firma de POST /api/users/{id} (owner: UserController)"

---

### 4. DATA_MODEL_MAP.json — La estructura de datos (opcional)

Úsalo SOLO si:
- El dominio `data` fue seleccionado, O
- Los candidatos hablan de modelos/queries/migrations

**Estructura:**
```
orm: "SQLAlchemy"
database: "Postgres"
pattern: "Manager / Repository"
models[]
  ├─ name: "User"
  ├─ file: "api/models/user.py"
  ├─ fields: [{ name, type, nullable, foreign_key }]
  ├─ relationships: [{ name, target, cardinality }]
  └─ migrations: ["001_create_users.sql", ...]
query_files[]
  └─ rutas a archivos de queries compiladas
```

**Estrategia:**
- Extrae `orm`, `database`, `pattern` → key_facts
- Si el cambio toca un modelo, extrae sus `fields` y `relationships` → key_facts
- `migrations` → detectar si necesitas alterar la BD

---

## Patrones de Extracción Quirúrgica

### Patrón 1: Detectar qué archivo cambiar
**Entrada:** prompt del operario + keywords del dominio
**Proceso:**
1. Lee ROUTING_MAP → identifica dominio(s)
2. Lee DOMAIN_INDEX_<dominio> → filtra `open_priority: "seed"`
3. Resultado: lista de archivos principales (files_to_open)

**Ejemplo:**
```
Prompt: "arreglar bug en validación de email"
→ ROUTING_MAP: dominio "api" (keyword "validación", "email")
→ DOMAIN_INDEX_api: seeds = [UserValidator, EmailService]
→ files_to_open = [api/validators/user.py, api/services/email.py]
```

### Patrón 2: Cascada de impacto
**Entrada:** archivo principal (seed)
**Proceso:**
1. Extrae `related_paths` del seed
2. Para cada related_path, busca en el mismo DOMAIN_INDEX si es `open_priority: "review"`
3. Resultado: lista de archivos que se ven afectados (files_to_review)

**Ejemplo:**
```
Seed: api/models/user.py
→ related_paths: ["api/services/user_service.py", "tests/test_user.py"]
→ files_to_review = [api/services/user_service.py]  (review)
```

### Patrón 3: Restricciones de breaking
**Entrada:** cualquier archivo con `contracts: [...]`
**Proceso:**
1. Extrae contratos del archivo
2. Busca esos contratos en CONTRACT_MAP
3. Si alguno tiene `breaking_if_changed: true` → generar constraint

**Ejemplo:**
```
Candidato api/controllers/user_controller.py
→ contracts: ["POST /api/users/{id}"]
→ CONTRACT_MAP.endpoints: POST /api/users/{id} (breaking_if_changed: true)
→ Constraint: "No romper firma de POST /api/users/{id}"
```

### Patrón 4: Dependencias env_vars
**Entrada:** archivos seleccionados
**Proceso:**
1. Para cada archivo, busca en CONTRACT_MAP.env_vars cuyo `owner` matchea
2. Si encuentra, generar constraint con el nombre de la var

**Ejemplo:**
```
Archivo: services/stripe_service.py
→ CONTRACT_MAP.env_vars: [{name: "STRIPE_SECRET_KEY", owner: "services/stripe_service.py"}]
→ Constraint: "env:STRIPE_SECRET_KEY requerida en services/stripe_service.py"
```

---

## Decisiones Rápidas

| Pregunta | Respuesta | Fuente |
|----------|-----------|--------|
| ¿Qué dominio toca este cambio? | Matchear keywords en ROUTING_MAP.domains[] | ROUTING_MAP |
| ¿Qué archivos abrir? | `open_priority: "seed"` en DOMAIN_INDEX_<dominio> | DOMAIN_INDEX |
| ¿Qué archivos revisar? | `related_paths` + `open_priority: "review"` | DOMAIN_INDEX |
| ¿Qué NO puedo romper? | `breaking_if_changed: true` en CONTRACT_MAP | CONTRACT_MAP |
| ¿Qué env_vars? | `owner` matchea con archivos seleccionados | CONTRACT_MAP |
| ¿Qué modelos afectan? | Buscar en DATA_MODEL_MAP.models[] | DATA_MODEL_MAP |

---

## Checklist de Extracción

Antes de generar el JSON de salida:

- [ ] ¿Identifiqué 1-2 dominios correctamente? (sin falsos positivos)
- [ ] ¿Extraje todos los seeds (`open_priority: "seed"`)?
- [ ] ¿Incluí related_paths de cada seed en files_to_review?
- [ ] ¿Incluí TODAS las restricciones de breaking en constraints?
- [ ] ¿Incluí default_constraints del ROUTING_MAP en constraints?
- [ ] ¿Incluí env_vars relevantes en constraints?
- [ ] ¿Cada archivo en files_to_open tiene key_symbols?
- [ ] ¿key_symbols viene de DOMAIN_INDEX (no inventados)?
- [ ] ¿test_file es el primer elemento de test_files[] o null?
