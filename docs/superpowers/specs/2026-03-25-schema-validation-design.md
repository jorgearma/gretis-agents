# Schema Validation Automática para el Pipeline de Agentes

**Fecha:** 2026-03-25
**Estado:** Aprobado
**Alcance:** `claude/hooks/`

---

## Problema

Los 17 schemas JSON en `claude/schemas/` están bien definidos (JSON Schema draft/2020-12, con `required`, `enum`, `additionalProperties: false`) pero ningún hook los usa para validar los artifacts de runtime. La validación actual en `execute-plan.py` es un diccionario hardcodeado (`_REQUIRED_FIELDS`) con un subset mínimo de campos. Los demás hooks no validan el contenido de sus inputs en absoluto.

Esto permite que un agente produzca un artifact malformado que pase silenciosamente al siguiente stage, causando fallos difíciles de diagnosticar lejos del origen.

---

## Objetivo

Validar automáticamente todos los artifacts JSON en entry/exit de cada hook, usando los schemas existentes como fuente de verdad, con el menor overhead de tokens y sin cambiar la lógica de negocio de los hooks.

---

## Decisiones de diseño

| Decisión | Elección | Razón |
|----------|----------|-------|
| ¿Dónde validar? | Solo en hooks Python | Los agentes .md no ejecutan código; los hooks son el único punto de control programático |
| ¿Qué tan estricto? | Fallo duro para errores críticos, warning para problemas menores | Evita falsos bloqueos por campos opcionales sin romper el pipeline en casos no críticos |
| ¿Versionado de schemas? | No (mensajes de error claros) | Un solo operador, evolución lenta, YAGNI |
| ¿Fallback si jsonschema no instalado? | Fallo duro | Simplicidad; el entorno debe estar correctamente configurado |

---

## Arquitectura

### Componente nuevo: `claude/hooks/validate.py`

Módulo central reutilizable. Todos los hooks lo importan. No contiene lógica de negocio.

```
claude/hooks/
├── validate.py          ← NUEVO
├── execute-plan.py      ← modificado
├── approve-plan.py      ← modificado
├── quick-execute.py     ← modificado
├── dispatch-reviewer.py ← modificado
├── recover-cycle.py     ← modificado
└── pre-commit.py        ← modificado
```

### API pública de `validate.py`

```python
@dataclass
class ValidationResult:
    ok: bool              # False si hay al menos un error crítico
    errors: list[str]     # Mensajes de error bloqueantes
    warnings: list[str]   # Mensajes no bloqueantes

    def format(self) -> str: ...         # Output formateado para consola
    def format_warnings(self) -> str: ...
    def summary(self) -> str: ...        # Una línea para escribir en dispatch JSON


def validate_artifact(name: str, data: dict) -> ValidationResult:
    """Valida `data` contra el schema correspondiente a `name`.

    Args:
        name: Nombre del artifact (ej: "plan.json", "PROJECT_MAP.json")
        data: Contenido parseado del artifact

    Returns:
        ValidationResult con errores clasificados

    Raises:
        ImportError: Si jsonschema no está instalado
        KeyError: Si `name` no tiene schema registrado en SCHEMA_MAP
    """
```

### Clasificación de errores

`jsonschema` devuelve todos los errores igual. La clasificación es:

**Crítico (bloquea) — `result.ok = False`:**
- Campo `required` ausente
- Valor fuera de `enum` permitido
- Tipo incorrecto en campo requerido

**Warning (notifica, no bloquea):**
- Campo opcional con tipo incorrecto
- `additionalProperties` violation (degradado a warning en runtime para tolerar campos nuevos que un agente agregue sin romper compatibilidad)

```python
CRITICAL_VALIDATORS = {"required", "enum", "type"}

def _classify(error: ValidationError, schema: dict) -> Literal["error", "warning"]:
    if error.validator in CRITICAL_VALIDATORS and _is_required_field(error, schema):
        return "error"
    return "warning"
```

### Formato de output en consola

```
[BLOCKED] plan.json — 2 error(s), 1 warning(s)
  ERROR   steps[0].owner: 'devops' is not valid (enum: frontend, backend, reviewer, test-runner)
  ERROR   done_criteria: field required but missing
  WARN    impact_analysis.notes: expected string, got integer
```

### SCHEMA_MAP — mapeo artifact → schema file

```python
SCHEMA_MAP = {
    "reader-context.json":     "reader-context.json",
    "plan.json":               "plan.json",
    "execution-brief.json":    "execution-brief.json",
    "execution-dispatch.json": "execution-dispatch.json",
    "operator-approval.json":  "operator-approval.json",
    "plan-review.json":        "plan-review.json",
    "result.json":             "result.json",
    "review.json":             "review.json",
    "sense-check.json":        "sense-check.json",
    "quick-dispatch.json":     "quick-dispatch.json",
    "clarifications.json":     "clarifications.json",
    "PROJECT_MAP.json":        "project-map.json",
    "DB_MAP.json":             "db-map.json",
    "QUERY_MAP.json":          "query-map.json",
    "UI_MAP.json":             "ui-map.json",
}
```

---

## Cambios por hook

### `execute-plan.py`
- **Eliminar:** `_REQUIRED_FIELDS` dict, función `validate_fields()`
- **Agregar:** `validate_artifact` para `operator-approval.json`, `plan.json`, `plan-review.json`, `execution-brief.json`
- El flujo de bloqueo y mensajes se mantiene idéntico

### `approve-plan.py`
- **Agregar:** validación de `operator-approval.json` al leer/escribir

### `quick-execute.py`
- **Agregar:** validación de `quick-dispatch.json`

### `dispatch-reviewer.py`
- **Agregar:** validación de `result.json` antes de generar `reviewer-dispatch.json`

### `recover-cycle.py`
- **Agregar:** validación de los artifacts runtime presentes (no falla si un archivo no existe, solo si existe y está malformado)

### `pre-commit.py`
- **Mantener:** verificación de existencia de archivos y JSON parseable (sin cambios)
- **Agregar:** validación de `maps/*.json` contra sus schemas (`project-map.json`, `db-map.json`, `query-map.json`, `ui-map.json`)

---

## Dependencia

```bash
pip install jsonschema
```

Fallo duro si no está instalado — el entorno debe estar correctamente configurado.

---

## Criterios de done

- [ ] `validate_artifact("plan.json", data)` retorna lista de errores con campo + mensaje exacto
- [ ] Campos `required` faltantes o enum inválidos → `result.ok = False` → hook bloquea
- [ ] Campos opcionales malformados → `result.warnings` → solo imprime en consola
- [ ] `execute-plan.py` no tiene más `_REQUIRED_FIELDS` ni `validate_fields()`
- [ ] Todos los hooks importan y usan `validate.py`
- [ ] `pre-commit.py` detecta maps malformados contra schema
- [ ] `python3 .claude/hooks/pre-commit.py` pasa sin errores tras los cambios

---

## Lo que NO cambia

- La lógica de negocio de ningún hook
- Los schemas JSON en `claude/schemas/` (son la fuente de verdad, no se modifican)
- Los artifacts de runtime ni su estructura
- Las instrucciones de los agentes `.md`
