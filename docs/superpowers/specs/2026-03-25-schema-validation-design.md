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
| ¿`additionalProperties` violation? | Warning, no error | Los agentes LLM pueden agregar campos extra. Degradar a warning permite evolución sin romper el pipeline. `additionalProperties: false` es un constraint de diseño, no de runtime |
| `validate_artifact` retorna o lanza | Siempre retorna `ValidationResult`, nunca lanza | El caller (hook) decide cómo reaccionar; permite diferentes políticas por hook si se necesita |
| ¿Versionado de schemas? | No — mensajes de error claros | Un solo operador, evolución lenta, YAGNI |
| ¿Fallback si jsonschema no instalado? | Fallo duro con `ImportError` | Simplicidad; el entorno debe estar correctamente configurado |
| Artifact desconocido en `validate_artifact` | Lanza `KeyError` con mensaje claro | Fail-fast: un nombre desconocido indica bug en el hook, no un caso válido en runtime |

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
import json
from dataclasses import dataclass, field
from pathlib import Path

# Schemas cargados desde disco relativo a este archivo:
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"

@dataclass
class ValidationResult:
    ok: bool              # False si hay al menos un error crítico
    errors: list[str]     # Mensajes bloqueantes — campo + descripción exacta
    warnings: list[str]   # Mensajes no bloqueantes

    def format(self) -> str:
        """Texto multilínea para consola. Incluye nombre del artifact, errores y warnings.
        Ejemplo:
          [BLOCKED] plan.json — 2 error(s), 1 warning(s)
            ERROR   steps[0].owner: 'devops' is not valid (enum: ...)
            ERROR   done_criteria: field required but missing
            WARN    impact_analysis.notes: expected string, got integer
        """

    def format_warnings(self) -> str:
        """Solo los warnings, sin el header de blocked."""

    def summary(self) -> str:
        """Una línea para incluir en dispatch JSON como campo 'reason'."""


def validate_artifact(name: str, data: dict) -> ValidationResult:
    """Valida `data` contra el schema correspondiente a `name`.

    Args:
        name: Nombre del artifact (ej: "plan.json", "PROJECT_MAP.json")
        data: Contenido ya parseado del artifact

    Returns:
        ValidationResult. `ok=True` si no hay errores críticos.
        Warnings presentes no afectan `ok`.

    Raises:
        KeyError: Si `name` no está en SCHEMA_MAP — indica bug en el hook caller
        ImportError: Si `jsonschema` no está instalado
    """
```

### Clasificación de errores

`jsonschema` devuelve todos los errores igual. La clasificación se hace por `error.validator`:

**Crítico — `result.ok = False`:**
- `"required"` — campo requerido ausente
- `"enum"` — valor fuera de los valores permitidos
- `"type"` — tipo incorrecto en campo que está en `required` del schema padre

**Warning — `result.ok` no cambia:**
- `"additionalProperties"` — campo extra presente (ver decisión de diseño)
- `"type"` en campo opcional — tipo incorrecto en campo no requerido
- Cualquier otro validator en campos opcionales

```python
CRITICAL_VALIDATORS = {"required", "enum"}

def _is_critical(error: ValidationError, schema: dict) -> bool:
    if error.validator in CRITICAL_VALIDATORS:
        return True
    if error.validator == "type":
        # Crítico solo si el campo está en `required` del schema padre
        field_name = error.path[-1] if error.path else None
        parent_required = error.parent.schema.get("required", []) if error.parent else []
        return field_name in parent_required
    return False
```

### SCHEMA_MAP — todos los artifacts mapeados

```python
SCHEMA_MAP: dict[str, str] = {
    # Runtime artifacts
    "reader-context.json":     "reader-context.json",
    "plan.json":               "plan.json",
    "files-read.json":         "files-read.json",
    "execution-brief.json":    "execution-brief.json",
    "execution-dispatch.json": "execution-dispatch.json",
    "operator-approval.json":  "operator-approval.json",
    "plan-review.json":        "plan-review.json",
    "result.json":             "result.json",
    "review.json":             "review.json",
    "reviewer-dispatch.json":  "reviewer-dispatch.json",
    "sense-check.json":        "sense-check.json",
    "quick-dispatch.json":     "quick-dispatch.json",
    "clarifications.json":     "clarifications.json",
    # Maps (nombre del artifact → nombre del schema file)
    "PROJECT_MAP.json":        "project-map.json",
    "DB_MAP.json":             "db-map.json",
    "QUERY_MAP.json":          "query-map.json",
    "UI_MAP.json":             "ui-map.json",
}
# Total: 17 artifacts — cubre todos los schemas en claude/schemas/
```

---

## Cambios por hook

### `execute-plan.py`

**Qué valida:** inputs antes de lógica de negocio.
**Cuándo:** inmediatamente después de `load_json()`, antes de cualquier lógica.

```python
# Reemplaza _REQUIRED_FIELDS dict y validate_fields() función
from validate import validate_artifact

for path, name in [(APPROVAL_PATH, "operator-approval.json"),
                   (PLAN_PATH, "plan.json"),
                   (REVIEW_PATH, "plan-review.json"),
                   (BRIEF_PATH, "execution-brief.json")]:
    data = load_json(path)
    result = validate_artifact(name, data)
    if not result.ok:
        print(result.format())
        write_json(DISPATCH_PATH, _block(task, result.summary()))
        return 1
    if result.warnings:
        print(result.format_warnings())
```

**Eliminar:** `_REQUIRED_FIELDS`, `validate_fields()`.

### `approve-plan.py`

**Qué valida:** `operator-approval.json` al leerlo (verificar estado actual antes de sobrescribir).
**Cuándo:** después de leer el archivo existente, antes de escribir el nuevo estado.

```python
result = validate_artifact("operator-approval.json", current_approval)
if not result.ok:
    print(result.format())
    return 1
```

### `quick-execute.py`

**Qué valida:** `quick-dispatch.json` antes de pasar a ejecución.
**Cuándo:** después de cargar el archivo, antes de lógica.

```python
result = validate_artifact("quick-dispatch.json", data)
if not result.ok:
    print(result.format())
    return 1
```

### `dispatch-reviewer.py`

**Qué valida:** `result.json` (input) antes de generar `reviewer-dispatch.json`.
**Cuándo:** después de cargar `result.json`, antes de escribir el dispatch.

```python
result = validate_artifact("result.json", result_data)
if not result.ok:
    print(result.format())
    return 1
```

### `recover-cycle.py`

**Qué valida:** cada artifact de runtime presente en disco.
**Cuándo:** al inicio, como diagnóstico. No falla si el archivo no existe — solo si existe y está malformado o inválido.

```python
for artifact_name, path in RUNTIME_ARTIFACTS.items():
    if path.exists():
        try:
            data = load_json(path)
        except ValueError:
            print(f"  CORRUPT  {artifact_name}")
            continue
        result = validate_artifact(artifact_name, data)
        if not result.ok:
            print(f"  INVALID  {artifact_name}")
            print(result.format())
        elif result.warnings:
            print(f"  WARN     {artifact_name}")
            print(result.format_warnings())
        else:
            print(f"  OK       {artifact_name}")
```

### `pre-commit.py`

**Qué valida:** `maps/*.json` contra sus schemas (hoy solo verifica JSON parseable).
**Cuándo:** en el bloque existente de validación JSON, después del check de parseable.
**Comportamiento:** fallo duro si un map es inválido contra su schema — los maps son archivos versionados, no artifacts runtime.

```python
from validate import validate_artifact

MAP_ARTIFACTS = {
    "PROJECT_MAP.json": PLUGIN_DIR / "maps" / "PROJECT_MAP.json",
    "DB_MAP.json":      PLUGIN_DIR / "maps" / "DB_MAP.json",
    "QUERY_MAP.json":   PLUGIN_DIR / "maps" / "QUERY_MAP.json",
    "UI_MAP.json":      PLUGIN_DIR / "maps" / "UI_MAP.json",
}

for artifact_name, path in MAP_ARTIFACTS.items():
    with path.open() as f:
        data = json.load(f)
    result = validate_artifact(artifact_name, data)
    if not result.ok:
        invalid_json.append(f"{path.relative_to(ROOT)}: schema inválido\n{result.format()}")
```

---

## Dependencia

```bash
pip install jsonschema
```

Requerida. `validate.py` lanza `ImportError` en el import si no está disponible — fallo inmediato antes de cualquier ejecución.

---

## Criterios de done

- [ ] `validate_artifact("plan.json", {"task": "x", "steps": []})` retorna `result.ok = False` con error en `done_criteria` (campo required faltante)
- [ ] `validate_artifact("plan.json", {"task": "x", "steps": [{"id":"1","title":"t","owner":"devops"}], ...})` retorna `result.ok = False` con error en `steps[0].owner` (enum inválido)
- [ ] Campo opcional malformado retorna `result.ok = True` con entry en `result.warnings`
- [ ] `execute-plan.py` no contiene `_REQUIRED_FIELDS` ni `validate_fields()`
- [ ] Todos los hooks (execute-plan, approve-plan, quick-execute, dispatch-reviewer, recover-cycle) importan y usan `validate_artifact`
- [ ] `pre-commit.py` detecta un map con campo required faltante y retorna exit code 1
- [ ] `python3 .claude/hooks/pre-commit.py` pasa sin errores en el repo actual tras los cambios
- [ ] `validate_artifact("unknown.json", {})` lanza `KeyError` con mensaje que incluye el nombre del artifact

---

## Lo que NO cambia

- La lógica de negocio de ningún hook
- Los schemas JSON en `claude/schemas/` (son la fuente de verdad, no se modifican)
- Los artifacts de runtime ni su estructura
- Las instrucciones de los agentes `.md`
