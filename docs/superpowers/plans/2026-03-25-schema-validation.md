# Schema Validation Automática — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear `claude/hooks/validate.py` como módulo central de validación JSON Schema y modificar 6 hooks para usarlo, eliminando validación manual hardcodeada.

**Architecture:** Un módulo `validate.py` carga los 17 schemas desde `claude/schemas/` usando `jsonschema`, clasifica errores en críticos (bloquean) y warnings (notifican), y expone `validate_artifact(name, data) -> ValidationResult`. Todos los hooks lo importan y reemplazan su validación manual actual.

**Tech Stack:** Python 3.10+, `jsonschema` (pip), `pathlib`, `dataclasses`

**Spec:** `docs/superpowers/specs/2026-03-25-schema-validation-design.md`

---

## Notas de implementación importantes

- **`result.json` schema**: no tiene `required` a nivel raíz. Los campos `frontend`/`backend` son opcionales en el schema (el agente que no actuó simplemente no los incluye). La validación detecta sub-objetos malformados (ej: `frontend.status = "unknown"`), pero no el objeto vacío `{}`. El guard `if not result:` existente en `dispatch-reviewer.py` cubre ese caso y debe preservarse.
- **`plan-review.json` schema**: requiere `verdict` + `summary` + `issues`. El `_REQUIRED_FIELDS` antiguo solo verificaba `verdict` — la migración a `validate_artifact` es intencionalmente más estricta.
- **`plan.json` schema**: requiere `risks` además de los campos que `_REQUIRED_FIELDS` verificaba. También es una mejora intencionada.
- **`approve-plan.py`**: la validación del payload es defensiva (el payload siempre es construido internamente y siempre es válido). Garantiza que bugs futuros en `build_payload()` sean detectados. No protege contra input externo.
- **Path construction**: `SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"` — `parents[1]` desde `claude/hooks/validate.py` apunta a `claude/`. Correcto.

---

## File Structure

| Acción | Archivo | Qué hace |
|--------|---------|----------|
| Crear | `claude/hooks/validate.py` | Módulo central: carga schemas, clasifica errores, expone `validate_artifact` |
| Crear | `claude/hooks/tests/__init__.py` | Hace el directorio un package Python |
| Crear | `claude/hooks/tests/test_validate.py` | Tests unitarios de `validate.py` |
| Crear | `claude/hooks/tests/test_hooks_integration.py` | Tests de integración: hooks usan validate correctamente |
| Modificar | `claude/hooks/execute-plan.py` | Reemplaza `_REQUIRED_FIELDS` + `validate_fields()` por `validate_artifact` |
| Modificar | `claude/hooks/approve-plan.py` | Valida payload antes de escribir (guard defensivo) |
| Modificar | `claude/hooks/quick-execute.py` | Valida `quick-dispatch.json` tras escribirlo |
| Modificar | `claude/hooks/dispatch-reviewer.py` | Valida `result.json` sub-objetos antes de generar reviewer-dispatch |
| Modificar | `claude/hooks/recover-cycle.py` | Agrega validación en `cmd_status`, `cmd_rollback`, `cmd_reset` |
| Modificar | `claude/hooks/pre-commit.py` | Valida `maps/*.json` contra schemas |

---

## Task 1: Instalar dependencia y crear `validate.py`

**Files:**
- Create: `claude/hooks/validate.py`

- [ ] **Step 1: Instalar jsonschema**

```bash
pip install jsonschema
python3 -c "import jsonschema; print('jsonschema', jsonschema.__version__)"
```
Expected: versión impresa sin error.

- [ ] **Step 2: Crear `claude/hooks/validate.py`**

```python
#!/usr/bin/env python3
"""Validación central de artifacts JSON contra sus schemas.

Uso desde hooks:
    from validate import validate_artifact

    result = validate_artifact("plan.json", data)
    if not result.ok:
        print(result.format())
        return 1
    if result.warnings:
        print(result.format_warnings())
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

try:
    import jsonschema
    from jsonschema import ValidationError
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "jsonschema no está instalado. Ejecuta: pip install jsonschema"
    ) from exc


# claude/hooks/ -> parents[0]; claude/ -> parents[1]; claude/schemas/ -> parents[1]/schemas
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"

# Mapeo: nombre del artifact en runtime → nombre del archivo schema en SCHEMA_DIR
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
    # Maps (artifact name → schema filename en schemas/)
    "PROJECT_MAP.json":        "project-map.json",
    "DB_MAP.json":             "db-map.json",
    "QUERY_MAP.json":          "query-map.json",
    "UI_MAP.json":             "ui-map.json",
}

# Validators que son críticos en campos requeridos
_CRITICAL_VALIDATORS = {"required", "enum"}


@dataclass
class ValidationResult:
    name: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def format(self) -> str:
        """Texto multilínea para consola. Incluye nombre del artifact, errores y warnings."""
        n_e = len(self.errors)
        n_w = len(self.warnings)
        header = f"[BLOCKED] {self.name} — {n_e} error(s), {n_w} warning(s)"
        lines = [header]
        for e in self.errors:
            lines.append(f"  ERROR   {e}")
        for w in self.warnings:
            lines.append(f"  WARN    {w}")
        return "\n".join(lines)

    def format_warnings(self) -> str:
        """Solo los warnings, sin header de blocked."""
        lines = [f"[WARN] {self.name} — {len(self.warnings)} warning(s)"]
        for w in self.warnings:
            lines.append(f"  WARN    {w}")
        return "\n".join(lines)

    def summary(self) -> str:
        """Una línea para incluir como campo 'reason' en dispatch JSON."""
        if self.errors:
            return f"{self.name} inválido: {self.errors[0]}"
        if self.warnings:
            return f"{self.name} con {len(self.warnings)} advertencia(s)"
        return f"{self.name} válido"


def _load_schema(schema_filename: str) -> dict:
    schema_path = SCHEMA_DIR / schema_filename
    with schema_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _is_critical(error: ValidationError) -> bool:
    """Determina si un error de jsonschema es bloqueante."""
    if error.validator in _CRITICAL_VALIDATORS:
        return True
    if error.validator == "type":
        # Crítico solo si el campo está en `required` del schema padre
        field_name = error.path[-1] if error.path else None
        if error.parent is not None:
            parent_required = error.parent.schema.get("required", [])
            return field_name in parent_required
    return False


def _error_message(error: ValidationError) -> str:
    """Formatea un error de jsonschema como mensaje legible."""
    path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
    return f"{path}: {error.message}"


def validate_artifact(name: str, data: dict) -> ValidationResult:
    """Valida `data` contra el schema correspondiente a `name`.

    Args:
        name: Nombre del artifact (ej: "plan.json", "PROJECT_MAP.json").
        data: Contenido ya parseado del artifact.

    Returns:
        ValidationResult. ok=True si no hay errores críticos.
        Warnings presentes no afectan ok.

    Raises:
        KeyError: Si `name` no está en SCHEMA_MAP — indica bug en el hook caller.
        ImportError: Si jsonschema no está instalado.
    """
    if name not in SCHEMA_MAP:
        raise KeyError(
            f"Artifact desconocido: '{name}'. "
            f"Artifacts válidos: {sorted(SCHEMA_MAP)}"
        )

    schema = _load_schema(SCHEMA_MAP[name])
    validator = jsonschema.Draft202012Validator(schema)

    errors: list[str] = []
    warnings: list[str] = []

    for error in validator.iter_errors(data):
        msg = _error_message(error)
        if _is_critical(error):
            errors.append(msg)
        else:
            warnings.append(msg)

    return ValidationResult(
        name=name,
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
```

- [ ] **Step 3: Verificar import**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python3 -c "from validate import validate_artifact; print('OK')"
```
Expected: `OK` sin traceback.

- [ ] **Step 4: Commit**

```bash
git add claude/hooks/validate.py
git commit -m "feat: add validate.py — central JSON schema validation module"
```

---

## Task 2: Tests unitarios de `validate.py`

**Files:**
- Create: `claude/hooks/tests/__init__.py`
- Create: `claude/hooks/tests/test_validate.py`

- [ ] **Step 1: Crear directorio de tests**

```bash
mkdir -p /home/siemprearmando/agentes/losgretis/claude/hooks/tests
touch /home/siemprearmando/agentes/losgretis/claude/hooks/tests/__init__.py
```

- [ ] **Step 2: Escribir test_validate.py**

```python
# claude/hooks/tests/test_validate.py
"""Tests unitarios para validate.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from validate import validate_artifact, ValidationResult, SCHEMA_MAP, SCHEMA_DIR


# ── Helpers de datos de test ──────────────────────────────────────────────────

def _valid_plan() -> dict:
    """Plan mínimo completamente válido según plan.json schema."""
    return {
        "task": "Agregar endpoint /health",
        "steps": [{"id": "s1", "title": "Crear handler", "owner": "backend"}],
        "risks": [],           # required en el schema real
        "done_criteria": ["GET /health retorna 200"],
        "context_inputs": {
            "selected_readers": ["project-reader"],
            "maps_used": ["PROJECT_MAP.json"],
            "files_to_open": [],
            "files_to_review": [],
        },
    }


def _valid_plan_review() -> dict:
    """plan-review.json mínimo válido: requiere verdict + summary + issues."""
    return {
        "verdict": "approved",
        "summary": "El plan es correcto.",
        "issues": [],
    }


# ── Criterio 1: campo required faltante bloquea ──────────────────────────────

def test_plan_missing_done_criteria_is_critical():
    """Campo required faltante → ok=False, error menciona done_criteria."""
    data = _valid_plan()
    del data["done_criteria"]
    result = validate_artifact("plan.json", data)
    assert not result.ok
    assert any("done_criteria" in e for e in result.errors), f"errors: {result.errors}"


# ── Criterio 2: enum inválido bloquea ────────────────────────────────────────

def test_plan_invalid_owner_enum_is_critical():
    """Valor enum inválido en steps[0].owner → ok=False."""
    data = _valid_plan()
    data["steps"][0]["owner"] = "devops"  # no válido
    result = validate_artifact("plan.json", data)
    assert not result.ok
    assert any("owner" in e or "devops" in e for e in result.errors), f"errors: {result.errors}"


# ── Criterio 3: campo opcional malformado → warning, no error ─────────────────

def test_plan_optional_field_wrong_type_is_warning():
    """Campo opcional con tipo incorrecto → ok=True, entry en warnings."""
    data = _valid_plan()
    data["context_inputs"]["notes"] = 99999  # notes es string opcional
    result = validate_artifact("plan.json", data)
    assert result.ok, f"errors: {result.errors}"
    assert len(result.warnings) > 0, "Se esperaba al menos un warning"


# ── Criterio 8: artifact desconocido lanza KeyError ──────────────────────────

def test_unknown_artifact_raises_key_error():
    """Artifact no registrado → KeyError con el nombre en el mensaje."""
    with pytest.raises(KeyError) as exc_info:
        validate_artifact("unknown-artifact.json", {})
    assert "unknown-artifact.json" in str(exc_info.value)


# ── plan-review.json requiere verdict + summary + issues ─────────────────────

def test_plan_review_missing_summary_is_critical():
    """plan-review.json sin 'summary' (campo required) → ok=False."""
    data = _valid_plan_review()
    del data["summary"]
    result = validate_artifact("plan-review.json", data)
    assert not result.ok
    assert any("summary" in e for e in result.errors), f"errors: {result.errors}"


def test_plan_review_missing_issues_is_critical():
    """plan-review.json sin 'issues' (campo required) → ok=False."""
    data = _valid_plan_review()
    del data["issues"]
    result = validate_artifact("plan-review.json", data)
    assert not result.ok
    assert any("issues" in e for e in result.errors), f"errors: {result.errors}"


# ── result.json: sin required a nivel raíz ───────────────────────────────────

def test_result_empty_object_passes_schema():
    """result.json vacío es válido per schema (frontend/backend son opcionales).
    El guard 'if not result' en dispatch-reviewer.py cubre este caso."""
    result = validate_artifact("result.json", {})
    assert result.ok


def test_result_with_invalid_frontend_status_is_critical():
    """result.json con frontend.status inválido → ok=False."""
    data = {
        "frontend": {
            "status": "unknown_status",   # no está en enum
            "summary": "hecho",
            "artifacts": [],
            "next_steps": [],
        }
    }
    result = validate_artifact("result.json", data)
    assert not result.ok
    assert any("status" in e or "unknown_status" in e for e in result.errors), \
        f"errors: {result.errors}"


# ── operator-approval.json ────────────────────────────────────────────────────

def test_operator_approval_valid():
    result = validate_artifact("operator-approval.json", {"status": "approved", "approved_by": "alice"})
    assert result.ok


def test_operator_approval_invalid_status():
    result = validate_artifact("operator-approval.json", {"status": "maybe", "approved_by": "alice"})
    assert not result.ok


# ── Cobertura de SCHEMA_MAP ───────────────────────────────────────────────────

def test_schema_map_covers_all_17_schemas():
    """SCHEMA_MAP debe cubrir exactamente 17 artifacts."""
    assert len(SCHEMA_MAP) == 17, f"Esperado 17, encontrado {len(SCHEMA_MAP)}"


def test_all_schema_files_exist_on_disk():
    """Todos los schema files referenciados deben existir en claude/schemas/."""
    missing = [
        f"{name} → {schema_file}"
        for name, schema_file in SCHEMA_MAP.items()
        if not (SCHEMA_DIR / schema_file).exists()
    ]
    assert missing == [], f"Schema files faltantes: {missing}"


# ── ValidationResult formatting ──────────────────────────────────────────────

def test_format_includes_artifact_name_and_blocked():
    data = {"status": "bad", "approved_by": "x"}
    result = validate_artifact("operator-approval.json", data)
    formatted = result.format()
    assert "operator-approval.json" in formatted
    assert "BLOCKED" in formatted


def test_summary_is_single_line():
    result = validate_artifact("operator-approval.json", {"status": "approved", "approved_by": "a"})
    assert "\n" not in result.summary()
```

- [ ] **Step 3: Correr tests**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 -m pytest claude/hooks/tests/test_validate.py -v --tb=short
```
Expected: todos pasan. Si alguno falla, corregir `validate.py`.

- [ ] **Step 4: Commit**

```bash
git add claude/hooks/tests/__init__.py claude/hooks/tests/test_validate.py
git commit -m "test: unit tests for validate.py — 17 schemas, critical/warning classification"
```

---

## Task 3: Modificar `execute-plan.py`

**Files:**
- Modify: `claude/hooks/execute-plan.py`

- [ ] **Step 1: Agregar import al inicio del archivo (después de los imports existentes)**

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_artifact
```

- [ ] **Step 2: Eliminar `_REQUIRED_FIELDS` dict y `validate_fields()` function**

Eliminar el bloque completo:
```python
# Campos requeridos mínimos por archivo (subset crítico del schema)
_REQUIRED_FIELDS: dict[str, list[str]] = {
    "operator-approval.json": ["status", "approved_by"],
    "plan.json":               ["task", "steps", "done_criteria", "context_inputs"],
    "execution-brief.json":   ["task", "approval_status", "target_agents", "implementation_steps"],
    "plan-review.json":       ["verdict"],
}


def validate_fields(data: dict, filename: str) -> list[str]:
    """Devuelve lista de campos requeridos ausentes."""
    required = _REQUIRED_FIELDS.get(filename, [])
    return [f for f in required if f not in data]
```

- [ ] **Step 3: Reemplazar los bloques de validación en `main()`**

Reemplazar el bucle existente `for obj, name in ((approval, ...), (plan, ...)):` y el bloque de `missing_review` y `missing_brief` con:

```python
    # Validar operator-approval.json y plan.json
    for data_obj, name in ((approval, "operator-approval.json"), (plan, "plan.json")):
        vr = validate_artifact(name, data_obj)
        if not vr.ok:
            print(vr.format())
            write_json(DISPATCH_PATH, _block(
                plan.get("task", "") if name != "plan.json" else "",
                vr.summary()
            ))
            return 1
        if vr.warnings:
            print(vr.format_warnings())

    # ... (código existente para REVIEW_PATH.exists() check, sin cambios) ...

    # Reemplazar validate_fields(review, "plan-review.json") con:
    vr_review = validate_artifact("plan-review.json", review)
    if not vr_review.ok:
        print(vr_review.format())
        write_json(DISPATCH_PATH, _block(task, vr_review.summary()))
        return 1

    # ... (código existente para verdict == "blocked", verdict == "warning") ...

    # Reemplazar validate_fields(brief, "execution-brief.json") con:
    vr_brief = validate_artifact("execution-brief.json", brief)
    if not vr_brief.ok:
        print(vr_brief.format())
        write_json(DISPATCH_PATH, _block(task, vr_brief.summary(), approved=True))
        return 1
    if vr_brief.warnings:
        print(vr_brief.format_warnings())
```

- [ ] **Step 4: Verificar que no quedan referencias eliminadas**

```bash
grep -n "_REQUIRED_FIELDS\|validate_fields" /home/siemprearmando/agentes/losgretis/claude/hooks/execute-plan.py
```
Expected: sin output.

- [ ] **Step 5: Smoke test**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 claude/hooks/execute-plan.py
```
Expected: mensaje de error por archivo faltante o `Execution ready`. No debe haber `ImportError` ni `AttributeError`.

- [ ] **Step 6: Commit**

```bash
git add claude/hooks/execute-plan.py
git commit -m "refactor(execute-plan): replace hardcoded _REQUIRED_FIELDS with validate_artifact"
```

---

## Task 4: Modificar `approve-plan.py`

**Files:**
- Modify: `claude/hooks/approve-plan.py`

Validación defensiva del payload construido antes de escribirlo. Garantiza que bugs futuros en `build_payload()` sean detectados inmediatamente.

- [ ] **Step 1: Agregar import después de los imports existentes**

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_artifact
```

- [ ] **Step 2: Agregar validación en `main()` entre `build_payload` y `write_payload`**

```python
def main() -> int:
    args = parse_args()
    payload = build_payload(args.action, args.by, args.notes)
    # Validación defensiva: detecta bugs en build_payload()
    vr = validate_artifact("operator-approval.json", payload)
    if not vr.ok:
        print(vr.format())
        return 1
    write_payload(payload)
    # ... resto sin cambios
```

- [ ] **Step 3: Smoke test — ambas acciones**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 claude/hooks/approve-plan.py approve --by "test-user"
python3 claude/hooks/approve-plan.py reject --by "test-user" --notes "razón"
python3 claude/hooks/approve-plan.py reset
```
Expected: cada comando imprime su estado sin error de validación.

- [ ] **Step 4: Commit**

```bash
git add claude/hooks/approve-plan.py
git commit -m "feat(approve-plan): defensive validation of operator-approval payload"
```

---

## Task 5: Modificar `quick-execute.py`

**Files:**
- Modify: `claude/hooks/quick-execute.py`

- [ ] **Step 1: Agregar import después de los imports existentes**

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_artifact
```

- [ ] **Step 2: Agregar validación en `main()` después de `write_json(DISPATCH_PATH, dispatch)`**

Localizar `write_json(DISPATCH_PATH, dispatch)` (aprox línea 302) y añadir inmediatamente después:

```python
    vr = validate_artifact("quick-dispatch.json", dispatch)
    if not vr.ok:
        print(vr.format())
        return 1
    if vr.warnings:
        print(vr.format_warnings())
```

- [ ] **Step 3: Smoke test**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 claude/hooks/quick-execute.py "Cambiar color del botón a rojo"
```
Expected: `FAST TRACK listo` sin error de validación.

- [ ] **Step 4: Commit**

```bash
git add claude/hooks/quick-execute.py
git commit -m "feat(quick-execute): validate quick-dispatch.json after writing"
```

---

## Task 6: Modificar `dispatch-reviewer.py`

**Files:**
- Modify: `claude/hooks/dispatch-reviewer.py`

La validación de `result.json` detecta sub-objetos malformados (ej: `frontend.status = "unknown"`). El guard existente `if not result:` cubre el caso de objeto vacío y debe preservarse.

- [ ] **Step 1: Agregar import**

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_artifact
```

- [ ] **Step 2: Agregar validación en `main()` después del guard `if not result:`**

```python
    # Después del bloque "if not result:" existente, agregar:
    vr = validate_artifact("result.json", result)
    if not vr.ok:
        write_json(REVIEWER_DISPATCH_PATH, _block(vr.summary(), list(result.keys())))
        print(vr.format())
        return 1
    if vr.warnings:
        print(vr.format_warnings())
```

- [ ] **Step 3: Smoke test (sin result.json)**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 claude/hooks/dispatch-reviewer.py
```
Expected: `Reviewer dispatch bloqueado: result.json no encontrado.` (comportamiento existente).

- [ ] **Step 4: Commit**

```bash
git add claude/hooks/dispatch-reviewer.py
git commit -m "feat(dispatch-reviewer): validate result.json sub-objects before generating reviewer dispatch"
```

---

## Task 7: Modificar `recover-cycle.py`

**Files:**
- Modify: `claude/hooks/recover-cycle.py`

Agregar validación en `cmd_status()` (diagnóstico), `cmd_rollback()` (plan.json antes de ejecutar), y `cmd_reset()` (informativo).

- [ ] **Step 1: Agregar import**

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_artifact, SCHEMA_MAP
```

- [ ] **Step 2: Reemplazar bloque de impresión en `cmd_status()`**

Reemplazar el bucle `for f in all_files:` con:

```python
def cmd_status() -> int:
    print("Estado del runtime")
    print("=" * 52)
    all_files = EXECUTION_ARTIFACTS + PLANNING_ARTIFACTS + READER_ARTIFACTS
    seen: set[str] = set()
    for f in all_files:
        if f.name in seen:
            continue
        seen.add(f.name)
        if f.exists():
            data = load_json(f)
            if not data:
                print(f"  [CORRUPT] {f.name:<34} (JSON inválido o vacío)")
                continue
            status_val = data.get("status") or data.get("verdict") or "—"
            task_val   = data.get("task", "")
            extra      = f" task={task_val[:40]!r}" if task_val else ""
            if f.name in SCHEMA_MAP:
                vr = validate_artifact(f.name, data)
                if not vr.ok:
                    print(f"  [INVALID] {f.name:<34} {status_val}{extra}")
                    for e in vr.errors:
                        print(f"            ERROR: {e}")
                elif vr.warnings:
                    print(f"  [WARN]    {f.name:<34} {status_val}{extra}")
                else:
                    print(f"  [OK]      {f.name:<34} {status_val}{extra}")
            else:
                print(f"  [OK]      {f.name:<34} {status_val}{extra}")
        else:
            print(f"  [--]      {f.name}")

    print()
    plan = load_json(PLAN_PATH)
    rollback = plan.get("rollback_plan", {})
    if rollback.get("enabled"):
        n = len(rollback.get("steps", []))
        owners = list(dict.fromkeys(s.get("owner", "?") for s in rollback.get("steps", [])))
        print(f"  Rollback disponible: {n} paso(s) — agentes: {', '.join(owners)}")
    else:
        print("  Rollback: no definido en el plan actual")
    return 0
```

- [ ] **Step 3: Agregar validación de plan.json en `cmd_rollback()`**

Localizar la línea `if not plan:` en `cmd_rollback()` y agregar después del check existente:

```python
    # Validar schema de plan.json antes de ejecutar rollback
    if PLAN_PATH.name in SCHEMA_MAP:
        vr = validate_artifact(PLAN_PATH.name, plan)
        if not vr.ok:
            print(f"Error: plan.json es inválido:\n{vr.format()}")
            return 1
```

- [ ] **Step 4: Agregar validación de plan.json en `cmd_reset()`**

Localizar `plan = load_json(PLAN_PATH)` en `cmd_reset()` y agregar después:

```python
    if plan and PLAN_PATH.name in SCHEMA_MAP:
        vr = validate_artifact(PLAN_PATH.name, plan)
        if vr.errors:
            print(f"Advertencia: plan.json tiene errores de schema (se conserva de todas formas):")
            print(vr.format())
```

> Nota: en `cmd_reset` es informativo (no bloquea), porque el operador puede querer resetear precisamente para salir de un estado corrupto.

- [ ] **Step 5: Smoke test**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 claude/hooks/recover-cycle.py status
```
Expected: tabla con `[OK]`, `[--]`, o `[INVALID]`. Sin error.

- [ ] **Step 6: Commit**

```bash
git add claude/hooks/recover-cycle.py
git commit -m "feat(recover-cycle): add schema validation to status, rollback, and reset commands"
```

---

## Task 8: Modificar `pre-commit.py`

**Files:**
- Modify: `claude/hooks/pre-commit.py`

- [ ] **Step 1: Agregar import**

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_artifact
```

- [ ] **Step 2: Agregar bloque de validación de maps en `main()` después del bloque `if invalid_json:`**

```python
    # Validar maps/*.json contra sus schemas
    MAP_ARTIFACTS = {
        "PROJECT_MAP.json": PLUGIN_DIR / "maps" / "PROJECT_MAP.json",
        "DB_MAP.json":      PLUGIN_DIR / "maps" / "DB_MAP.json",
        "QUERY_MAP.json":   PLUGIN_DIR / "maps" / "QUERY_MAP.json",
        "UI_MAP.json":      PLUGIN_DIR / "maps" / "UI_MAP.json",
    }
    map_schema_errors: list[str] = []
    for artifact_name, map_path in MAP_ARTIFACTS.items():
        try:
            with map_path.open("r", encoding="utf-8") as fh:
                map_data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue  # ya detectado en invalid_json
        vr = validate_artifact(artifact_name, map_data)
        if not vr.ok:
            map_schema_errors.append(
                f"{map_path.relative_to(ROOT)}: schema violations\n{vr.format()}"
            )

    if map_schema_errors:
        print("Map files with schema violations:")
        for error in map_schema_errors:
            print(f"- {error}")
        return 1
```

- [ ] **Step 3: Verificar que el repo actual pasa (criterio 7)**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 claude/hooks/pre-commit.py
```
Expected: `Claude plugin structure ok`

- [ ] **Step 4: Verificar detección de map inválido (criterio 6) — con backup seguro**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 - <<'EOF'
import json, shutil, subprocess, sys
from pathlib import Path

map_path = Path("claude/maps/PROJECT_MAP.json")
backup   = Path("/tmp/PROJECT_MAP_backup.json")

# Backup
shutil.copy2(map_path, backup)

try:
    data = json.loads(map_path.read_text())
    # Eliminar un campo required del schema project-map.json:
    # required: ["name", "languages", "stack", "structure", "architecture", "modules"]
    data.pop("name", None)
    map_path.write_text(json.dumps(data, indent=2))

    result = subprocess.run(
        ["python3", "claude/hooks/pre-commit.py"],
        capture_output=True, text=True
    )
    print("stdout:", result.stdout)
    print("returncode:", result.returncode)
    assert result.returncode == 1, "pre-commit.py debería haber fallado con map inválido"
    print("OK: detección de map inválido funciona correctamente")
finally:
    shutil.copy2(backup, map_path)
    print("Map restaurado.")
EOF
```
Expected:
```
stdout: ... schema violations ...
returncode: 1
OK: detección de map inválido funciona correctamente
Map restaurado.
```

- [ ] **Step 5: Verificar que pre-commit.py pasa después del restore**

```bash
python3 claude/hooks/pre-commit.py
```
Expected: `Claude plugin structure ok`

- [ ] **Step 6: Commit**

```bash
git add claude/hooks/pre-commit.py
git commit -m "feat(pre-commit): validate maps/*.json against JSON schemas"
```

---

## Task 9: Tests de integración y verificación final

**Files:**
- Create: `claude/hooks/tests/test_hooks_integration.py`

- [ ] **Step 1: Escribir tests de integración**

```python
# claude/hooks/tests/test_hooks_integration.py
"""Verifica que los hooks modificados usan validate_artifact."""
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]


def _src(name: str) -> str:
    return (HOOKS_DIR / name).read_text(encoding="utf-8")


def test_execute_plan_no_required_fields_dict():
    source = _src("execute-plan.py")
    assert "_REQUIRED_FIELDS" not in source, "_REQUIRED_FIELDS debe haber sido eliminado"
    assert "validate_fields" not in source, "validate_fields debe haber sido eliminado"


def test_execute_plan_uses_validate_artifact():
    assert "validate_artifact" in _src("execute-plan.py")


def test_approve_plan_uses_validate_artifact():
    assert "validate_artifact" in _src("approve-plan.py")


def test_quick_execute_uses_validate_artifact():
    assert "validate_artifact" in _src("quick-execute.py")


def test_dispatch_reviewer_uses_validate_artifact():
    assert "validate_artifact" in _src("dispatch-reviewer.py")


def test_recover_cycle_uses_validate_artifact():
    assert "validate_artifact" in _src("recover-cycle.py")


def test_pre_commit_uses_validate_artifact():
    assert "validate_artifact" in _src("pre-commit.py")
```

- [ ] **Step 2: Correr todos los tests**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 -m pytest claude/hooks/tests/ -v --tb=short
```
Expected: todos pasan.

- [ ] **Step 3: Correr pre-commit.py final**

```bash
python3 claude/hooks/pre-commit.py
```
Expected: `Claude plugin structure ok`

- [ ] **Step 4: Commit final**

```bash
git add claude/hooks/tests/test_hooks_integration.py
git commit -m "test: integration tests verifying all 6 hooks use validate_artifact"
```

---

## Criterios de done — checklist final

- [ ] `validate_artifact("plan.json", {sin done_criteria})` → `ok=False`, error menciona `done_criteria`
- [ ] `validate_artifact("plan.json", {steps[0].owner="devops"})` → `ok=False`, error menciona enum
- [ ] Campo opcional malformado → `ok=True`, entry en `warnings`
- [ ] `execute-plan.py` no contiene `_REQUIRED_FIELDS` ni `validate_fields`
- [ ] Los 5 hooks (execute-plan, approve-plan, quick-execute, dispatch-reviewer, recover-cycle) usan `validate_artifact`
- [ ] `pre-commit.py` detecta map con campo required faltante → exit 1
- [ ] `python3 claude/hooks/pre-commit.py` pasa en el repo actual
- [ ] `validate_artifact("unknown.json", {})` lanza `KeyError` con el nombre del artifact
