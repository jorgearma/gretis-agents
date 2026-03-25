# Enriched MAP JSONs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir `modules` + `problems` a PROJECT_MAP y `test_file`/`env_vars`/`schema_files` a todos los MAPs especializados para que los readers entreguen al planner rutas y símbolos precisos sin exploración extra.

**Architecture:** Tres helpers nuevos en `core.py` (`find_test_file`, `detect_problems`, y extensión de `build_module_entry` con `test_file`). Cada analyzer llama a estos helpers al construir su MAP. Schemas JSON actualizados en paralelo. Sin post-processors separados.

**Tech Stack:** Python 3.12, stdlib `ast`+`re`+`pathlib`, pytest 9.x

---

## File Map

| Acción | Archivo | Qué cambia |
|---|---|---|
| Modify | `claude/hooks/analyzers/core.py` | `find_test_file`, `detect_problems`, `build_module_entry` +test_file, `build_symbols` cap 8→10, `build_query_entry` +test_file |
| Modify | `claude/hooks/analyzers/project.py` | Añadir `modules` + `problems` al output |
| Modify | `claude/hooks/analyzers/api.py` | Añadir `schema_files` al raíz, `test_file` por blueprint |
| Modify | `claude/hooks/analyzers/db.py` | Añadir `test_file` por modelo |
| Modify | `claude/hooks/analyzers/services.py` | Añadir `test_file` por integración |
| Modify | `claude/hooks/analyzers/jobs.py` | Añadir `test_file` por job |
| Modify | `claude/hooks/analyzers/query.py` | `build_query_entry` ya actualizado en Task 1 |
| Modify | `claude/schemas/project-map.json` | Añadir `modules` + `problems` |
| Modify | `claude/schemas/api-map.json` | Añadir `schema_files`, `test_file` en blueprints |
| Modify | `claude/schemas/db-map.json` | Añadir `test_file` en models |
| Modify | `claude/schemas/services-map.json` | Añadir `test_file` en integrations |
| Modify | `claude/schemas/jobs-map.json` | Añadir `test_file` en jobs |
| Modify | `claude/schemas/query-map.json` | Añadir `test_file` en files |
| Modify | `claude/schemas/reader-context.json` | Añadir `test_file` en file_hint; campos raíz `problems_in_scope`, `env_vars_needed`, `schema_files`; actualizar enums de readers y maps |
| Test | `claude/hooks/tests/test_core.py` | Tests para helpers nuevos |
| Test | `claude/hooks/tests/test_analyzer_project.py` | Tests para modules + problems |
| Test | `claude/hooks/tests/test_analyzer_api.py` | Test schema_files + test_file |
| Test | `claude/hooks/tests/test_analyzer_services.py` | Test test_file |
| Test | `claude/hooks/tests/test_analyzer_jobs.py` | Test test_file |

---

## Task 1: `find_test_file` helper en core.py

**Files:**
- Modify: `claude/hooks/analyzers/core.py`
- Test: `claude/hooks/tests/test_core.py`

- [ ] **Step 1: Escribir el test que falla**

En `claude/hooks/tests/test_core.py`, añadir al final:

```python
def _make_fi(rel_path: str) -> "FileInfo":
    from analyzers.core import FileInfo
    return FileInfo(rel_path=rel_path, language="python", role="controller", size=100)

def test_find_test_file_pytest_convention():
    from analyzers.core import find_test_file
    all_files = [
        _make_fi("controllers/auth.py"),
        _make_fi("tests/test_auth.py"),
    ]
    result = find_test_file("controllers/auth.py", all_files)
    assert result == "tests/test_auth.py"

def test_find_test_file_suffix_convention():
    from analyzers.core import find_test_file
    all_files = [
        _make_fi("services/stripe.py"),
        _make_fi("tests/stripe_test.py"),
    ]
    result = find_test_file("services/stripe.py", all_files)
    assert result == "tests/stripe_test.py"

def test_find_test_file_sibling_dir():
    from analyzers.core import find_test_file
    all_files = [
        _make_fi("blueprints/auth.py"),
        _make_fi("blueprints/tests/test_auth.py"),
    ]
    result = find_test_file("blueprints/auth.py", all_files)
    assert result == "blueprints/tests/test_auth.py"

def test_find_test_file_returns_none_when_missing():
    from analyzers.core import find_test_file
    all_files = [_make_fi("controllers/auth.py")]
    result = find_test_file("controllers/auth.py", all_files)
    assert result is None

def test_find_test_file_never_returns_self():
    from analyzers.core import find_test_file
    # test files themselves should not match themselves
    all_files = [_make_fi("tests/test_auth.py")]
    result = find_test_file("tests/test_auth.py", all_files)
    assert result is None
```

- [ ] **Step 2: Correr los tests (deben fallar)**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_core.py::test_find_test_file_pytest_convention -v
```
Expected: `ImportError` o `AttributeError: module 'analyzers.core' has no attribute 'find_test_file'`

- [ ] **Step 3: Implementar `find_test_file` en core.py**

Añadir después de la función `find_related` (línea ~1076), antes de `build_symbols`:

```python
def find_test_file(rel_path: str, all_files: list[FileInfo]) -> str | None:
    """
    Busca el archivo de test asociado a rel_path dentro de all_files.
    Heurística en cascada — nunca inventa rutas, solo devuelve paths que existen en all_files.
    """
    stem = Path(rel_path).stem
    dir_ = str(Path(rel_path).parent)
    all_paths = {f.rel_path for f in all_files}

    # Excluir el propio archivo (evita que test files se apunten a sí mismos)
    if stem.startswith("test_") or stem.endswith("_test"):
        return None

    candidates = [
        f"tests/test_{stem}.py",
        f"tests/{stem}_test.py",
        f"{dir_}/tests/test_{stem}.py",
        f"{dir_}/tests/{stem}_test.py",
    ]
    for c in candidates:
        if c in all_paths:
            return c

    # Fallback: cualquier archivo cuyo stem contiene "test" + stem del archivo
    for f in all_files:
        f_stem = Path(f.rel_path).stem
        if ("test" in f_stem.lower()) and (stem.lower() in f_stem.lower()):
            return f.rel_path

    return None
```

- [ ] **Step 4: Correr todos los tests nuevos**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_core.py -k "find_test_file" -v
```
Expected: todos PASS

- [ ] **Step 5: Commit**

```bash
cd /home/siemprearmando/agentes/losgretis
git add claude/hooks/analyzers/core.py claude/hooks/tests/test_core.py
git commit -m "feat(core): add find_test_file helper"
```

---

## Task 2: `detect_problems` helper en core.py

**Files:**
- Modify: `claude/hooks/analyzers/core.py`
- Test: `claude/hooks/tests/test_core.py`

- [ ] **Step 1: Escribir el test que falla**

En `claude/hooks/tests/test_core.py`, añadir:

```python
def test_detect_problems_god_object():
    from analyzers.core import detect_problems, FileInfo
    big_file = FileInfo(
        rel_path="managers/dashboard.py",
        language="python", role="data_access", size=450 * 80,  # ~450 lines
        functions=["fn_" + str(i) for i in range(20)],  # 20 functions
    )
    problems = detect_problems([big_file])
    types = [p["type"] for p in problems]
    assert "god_object" in types

def test_detect_problems_no_tests():
    from analyzers.core import detect_problems, FileInfo
    ctrl = FileInfo(
        rel_path="controllers/auth.py",
        language="python", role="controller", size=200,
        functions=["login"],
    )
    problems = detect_problems([ctrl])
    types = [p["type"] for p in problems]
    assert "no_tests" in types

def test_detect_problems_skips_test_files():
    from analyzers.core import detect_problems, FileInfo
    test_file = FileInfo(
        rel_path="tests/test_auth.py",
        language="python", role="test", size=100,
        functions=["test_login"] * 20,
    )
    problems = detect_problems([test_file])
    assert problems == []

def test_detect_problems_skips_migrations():
    from analyzers.core import detect_problems, FileInfo
    mig = FileInfo(
        rel_path="migrations/001_init.py",
        language="python", role="migration", size=10000,
    )
    problems = detect_problems([mig])
    assert problems == []

def test_detect_problems_no_test_only_for_logic_roles():
    from analyzers.core import detect_problems, FileInfo
    util = FileInfo(
        rel_path="utils/helpers.py",
        language="python", role="utility", size=50,
        functions=["format_date"],
    )
    # Utilities don't trigger no_tests
    problems = detect_problems([util])
    no_test_probs = [p for p in problems if p["type"] == "no_tests"]
    assert no_test_probs == []
```

- [ ] **Step 2: Correr los tests (deben fallar)**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_core.py::test_detect_problems_god_object -v
```
Expected: `AttributeError: module 'analyzers.core' has no attribute 'detect_problems'`

- [ ] **Step 3: Implementar `detect_problems` en core.py**

Añadir después de `find_test_file` (antes de `build_symbols`):

```python
# Roles que deben tener tests (si no los tienen, se reporta no_tests)
_LOGIC_ROLES = frozenset({"controller", "service", "data_access"})
# Roles que se excluyen de problemas
_SKIP_ROLES = frozenset({"test", "migration", "seed", "template", "component"})

def detect_problems(files: list[FileInfo]) -> list[dict]:
    """
    Detecta señales de riesgo en el conjunto de archivos.
    Solo evalúa archivos de lógica (excluye tests, migrations, templates).
    """
    # Construir set de stems de archivos de test para detectar no_tests
    test_stems: set[str] = set()
    for fi in files:
        if fi.role == "test" or "test" in Path(fi.rel_path).stem.lower():
            test_stems.add(Path(fi.rel_path).stem.lower())

    problems: list[dict] = []
    for fi in files:
        if fi.role in _SKIP_ROLES:
            continue
        if "test" in Path(fi.rel_path).parts[0].lower() if Path(fi.rel_path).parts else False:
            continue

        # god_object: >400 líneas aproximadas (size / 80) O >15 funciones
        approx_lines = fi.size // 80 if fi.size > 0 else 0
        fn_count = len(fi.functions or [])
        if approx_lines > 400 or fn_count > 15:
            problems.append({
                "file": fi.rel_path,
                "type": "god_object",
                "description": f"{approx_lines} líneas aprox, {fn_count} funciones",
            })
            continue  # no acumular no_tests sobre el mismo archivo

        # no_tests: roles de lógica sin test file asociado
        if fi.role in _LOGIC_ROLES:
            stem = Path(fi.rel_path).stem.lower()
            has_test = (
                f"test_{stem}" in test_stems
                or f"{stem}_test" in test_stems
                or any(stem in ts for ts in test_stems)
            )
            if not has_test:
                problems.append({
                    "file": fi.rel_path,
                    "type": "no_tests",
                    "description": "sin archivo de test asociado",
                })

    return problems
```

- [ ] **Step 4: Correr todos los tests nuevos**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_core.py -k "detect_problems" -v
```
Expected: todos PASS

- [ ] **Step 5: Commit**

```bash
cd /home/siemprearmando/agentes/losgretis
git add claude/hooks/analyzers/core.py claude/hooks/tests/test_core.py
git commit -m "feat(core): add detect_problems helper"
```

---

## Task 3: Actualizar `build_module_entry` y `build_query_entry` en core.py

**Files:**
- Modify: `claude/hooks/analyzers/core.py`
- Test: `claude/hooks/tests/test_core.py`

`build_module_entry` necesita `test_file`. `build_query_entry` necesita `test_file`. `build_symbols` sube cap de 8 a 10.

- [ ] **Step 1: Escribir tests que fallan**

En `claude/hooks/tests/test_core.py`, añadir:

```python
def test_build_module_entry_includes_test_file():
    from analyzers.core import build_module_entry, FileInfo
    fi = FileInfo(
        rel_path="controllers/auth.py",
        language="python", role="controller", size=200,
        classes=["AuthController"], functions=["login"],
        symbols_with_lines={"AuthController": 5, "login": 20},
        docstring="Gestiona autenticacion de usuarios.",
    )
    test_fi = FileInfo(
        rel_path="tests/test_auth.py",
        language="python", role="test", size=100,
    )
    entry = build_module_entry(fi, [fi, test_fi], {})
    assert "test_file" in entry
    assert entry["test_file"] == "tests/test_auth.py"

def test_build_module_entry_test_file_null_when_missing():
    from analyzers.core import build_module_entry, FileInfo
    fi = FileInfo(
        rel_path="controllers/auth.py",
        language="python", role="controller", size=200,
    )
    entry = build_module_entry(fi, [fi], {})
    assert entry["test_file"] is None

def test_build_query_entry_includes_test_file():
    from analyzers.core import build_query_entry, FileInfo
    fi = FileInfo(
        rel_path="managers/user_manager.py",
        language="python", role="data_access", size=300,
        functions=["get_user", "create_user"],
    )
    test_fi = FileInfo(
        rel_path="tests/test_user_manager.py",
        language="python", role="test", size=100,
    )
    entry = build_query_entry(fi, [fi, test_fi], {})
    assert "test_file" in entry
    assert entry["test_file"] == "tests/test_user_manager.py"

def test_build_symbols_cap_is_10():
    from analyzers.core import build_symbols, FileInfo
    # 12 symbols — should cap at 10
    syms = {f"fn_{i}": i * 10 for i in range(12)}
    fi = FileInfo(
        rel_path="controllers/big.py",
        language="python", role="controller", size=500,
        functions=[f"fn_{i}" for i in range(12)],
        symbols_with_lines=syms,
    )
    result = build_symbols(fi)
    assert len(result) <= 10
```

- [ ] **Step 2: Correr los tests (deben fallar)**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_core.py::test_build_module_entry_includes_test_file -v
```
Expected: FAIL — `test_file` no está en el dict

- [ ] **Step 3: Actualizar `build_module_entry` y `build_query_entry` en core.py**

Reemplazar `build_module_entry` (línea ~1087):

```python
def build_module_entry(
    fi: FileInfo,
    all_files: list[FileInfo],
    cochange: dict[str, list[str]],
) -> dict:
    """Construye el objeto enriquecido para un módulo en PROJECT_MAP.json."""
    return {
        "path":            fi.rel_path,
        "purpose":         infer_purpose(fi),
        "search_keywords": extract_keywords(fi),
        "related_to":      find_related(fi, all_files, cochange),
        "symbols":         build_symbols(fi),
        "test_file":       find_test_file(fi.rel_path, all_files),
    }
```

Reemplazar `build_query_entry` (línea ~1101):

```python
def build_query_entry(
    fi: FileInfo,
    all_files: list[FileInfo],
    cochange: dict[str, list[str]],
) -> dict:
    """Objeto mínimo para query-reader: path, role, functions, query_examples, test_file."""
    return {
        "path":           fi.rel_path,
        "role":           fi.role,
        "functions":      (fi.functions or fi.exports)[:10],
        "query_examples": fi.query_examples[:3],
        "test_file":      find_test_file(fi.rel_path, all_files),
    }
```

En `build_symbols`, cambiar `return result[:8]` → `return result[:10]`.

- [ ] **Step 4: Correr tests**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_core.py -k "build_module_entry or build_query_entry or build_symbols_cap" -v
```
Expected: todos PASS

- [ ] **Step 5: Commit**

```bash
cd /home/siemprearmando/agentes/losgretis
git add claude/hooks/analyzers/core.py claude/hooks/tests/test_core.py
git commit -m "feat(core): build_module_entry+build_query_entry include test_file, build_symbols cap 10"
```

---

## Task 4: `project.py` — añadir `modules` + `problems`; actualizar schema

**Files:**
- Modify: `claude/hooks/analyzers/project.py`
- Modify: `claude/schemas/project-map.json`
- Test: `claude/hooks/tests/test_analyzer_project.py`

- [ ] **Step 1: Escribir test que falla**

En `claude/hooks/tests/test_analyzer_project.py`, añadir:

```python
def test_project_map_has_modules_and_problems(tmp_path):
    """PROJECT_MAP debe tener modules (dict por rol) y problems (lista)."""
    from analyzers.core import walk_repo, detect_stack
    from analyzers.project import run

    # Crear estructura mínima
    (tmp_path / "app.py").write_text('"""Entry point."""\nfrom flask import Flask\napp = Flask(__name__)\n')
    (tmp_path / "controllers").mkdir()
    (tmp_path / "controllers" / "auth.py").write_text('"""Auth controller."""\ndef login():\n    pass\n')
    (tmp_path / ".git").mkdir()  # simular repo

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    assert "modules" in result, "PROJECT_MAP debe tener campo modules"
    assert isinstance(result["modules"], dict), "modules debe ser un dict"
    assert "problems" in result, "PROJECT_MAP debe tener campo problems"
    assert isinstance(result["problems"], list), "problems debe ser una lista"

def test_project_map_modules_have_required_fields(tmp_path):
    """Cada módulo en modules debe tener path, purpose, search_keywords, symbols, test_file, related_to."""
    from analyzers.core import walk_repo, detect_stack
    from analyzers.project import run

    (tmp_path / "controllers").mkdir()
    (tmp_path / "controllers" / "auth.py").write_text('"""Auth handler."""\ndef login(): pass\n')
    (tmp_path / ".git").mkdir()

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    for role, entries in result["modules"].items():
        for entry in entries:
            for field in ("path", "purpose", "search_keywords", "symbols", "test_file", "related_to"):
                assert field in entry, f"modules[{role}][].{field} ausente"
```

- [ ] **Step 2: Correr test (debe fallar)**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_analyzer_project.py::test_project_map_has_modules_and_problems -v
```
Expected: FAIL — `AssertionError: PROJECT_MAP debe tener campo modules`

- [ ] **Step 3: Actualizar `project.py`**

En `project.py`, actualizar el import al inicio del archivo para añadir los helpers nuevos:

```python
from analyzers.core import (
    FileInfo, detect_stack, git_hotspots, git_cochange,
    walk_repo, detect_project_name, detect_readme_summary,
    infer_architecture, scan_structure,
    build_module_entry, detect_problems,
)
```

Dentro de la función `run()`, `cochange_raw` ya se llama en la línea 137 del archivo actual. Reutilizar esa variable — **no llamar `git_cochange` de nuevo**. Añadir el bloque de modules y problems justo después del bloque `cochange = {…}` (línea ~149) y antes del bloque `domains`:

```python
# ── Construir modules por rol ─────────────────────────────────────────────
# Nota: reutiliza cochange_raw ya calculado arriba (línea ~137)
MODULES_ROLES = frozenset({"controller", "service", "data_access", "model",
                            "middleware", "utility", "entry_point"})
modules: dict[str, list[dict]] = {role: [] for role in MODULES_ROLES}
for fi in files:
    if fi.role in MODULES_ROLES:
        entry = build_module_entry(fi, files, cochange_raw)
        modules[fi.role].append(entry)

# ── Detectar problemas ────────────────────────────────────────────────────
problems = detect_problems(files)
```

Añadir `"modules": modules` y `"problems": problems` al dict `result`:

```python
result = {
    "name": name,
    "description": description,
    "languages": languages,
    "architecture": architecture,
    "stack": stack,
    "entry_points": entry_points,
    "domains": domains,
    "modules": modules,
    "problems": problems,
    "cochange": cochange,
    "hotspots": hotspots,
}
```

- [ ] **Step 4: Actualizar `claude/schemas/project-map.json`**

Añadir en `"properties"` los dos campos nuevos:

```json
"modules": {
  "type": "object",
  "description": "Índice de archivos por rol. Claves fijas: controller, service, data_access, model, middleware, utility, entry_point.",
  "additionalProperties": {
    "type": "array",
    "items": {
      "type": "object",
      "required": ["path", "purpose", "search_keywords", "symbols", "test_file", "related_to"],
      "additionalProperties": false,
      "properties": {
        "path":            { "type": "string" },
        "purpose":         { "type": "string" },
        "search_keywords": { "type": "array", "items": { "type": "string" } },
        "symbols": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "line", "kind"],
            "additionalProperties": false,
            "properties": {
              "name": { "type": "string" },
              "line": { "type": "integer" },
              "kind": { "type": "string", "enum": ["class", "function"] }
            }
          }
        },
        "test_file":  { "type": ["string", "null"] },
        "related_to": { "type": "array", "items": { "type": "string" } }
      }
    }
  }
},
"problems": {
  "type": "array",
  "items": {
    "type": "object",
    "required": ["file", "type", "description"],
    "additionalProperties": false,
    "properties": {
      "file":        { "type": "string" },
      "type":        { "type": "string", "enum": ["god_object", "no_tests"] },
      "description": { "type": "string" }
    }
  }
}
```

- [ ] **Step 5: Correr tests**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_analyzer_project.py -v
```
Expected: todos PASS

- [ ] **Step 6: Commit**

```bash
cd /home/siemprearmando/agentes/losgretis
git add claude/hooks/analyzers/project.py claude/schemas/project-map.json claude/hooks/tests/test_analyzer_project.py
git commit -m "feat(project): add modules + problems to PROJECT_MAP"
```

---

## Task 5: `api.py` — añadir `schema_files` y `test_file` por blueprint

**Files:**
- Modify: `claude/hooks/analyzers/api.py`
- Modify: `claude/schemas/api-map.json`
- Test: `claude/hooks/tests/test_analyzer_api.py`

- [ ] **Step 1: Escribir test que falla**

En `claude/hooks/tests/test_analyzer_api.py`, añadir:

```python
def test_api_map_has_schema_files(tmp_path):
    from analyzers.core import walk_repo, detect_stack
    from analyzers.api import run

    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "auth.py").write_text("from pydantic import BaseModel\nclass LoginRequest(BaseModel):\n    email: str\n")
    (tmp_path / "blueprints").mkdir()
    (tmp_path / "blueprints" / "auth.py").write_text(
        "from flask import Blueprint\nauth = Blueprint('auth', __name__)\n@auth.route('/login', methods=['POST'])\ndef login(): pass\n"
    )
    (tmp_path / ".git").mkdir()

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    assert "schema_files" in result
    assert any("schemas/auth.py" in s for s in result["schema_files"])

def test_api_blueprint_has_test_file(tmp_path):
    from analyzers.core import walk_repo, detect_stack
    from analyzers.api import run

    (tmp_path / "blueprints").mkdir()
    (tmp_path / "blueprints" / "auth.py").write_text(
        "from flask import Blueprint\nauth = Blueprint('auth', __name__)\n@auth.route('/login', methods=['POST'])\ndef login(): pass\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text("def test_login(): pass\n")
    (tmp_path / ".git").mkdir()

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    assert result["blueprints"], "debe haber al menos un blueprint"
    bp = result["blueprints"][0]
    assert "test_file" in bp
    assert bp["test_file"] == "tests/test_auth.py"
```

- [ ] **Step 2: Correr test (debe fallar)**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_analyzer_api.py::test_api_map_has_schema_files -v
```
Expected: FAIL — `KeyError: 'schema_files'`

- [ ] **Step 3: Actualizar `api.py`**

Añadir el import al inicio del archivo:

```python
from analyzers.core import FileInfo, detect_stack, walk_repo, find_test_file
```

Añadir regex de detección de schemas después de las constantes existentes:

```python
RE_SCHEMA_FILE = re.compile(
    r'(from\s+pydantic|class\s+\w+Schema|@dataclass)',
    re.MULTILINE,
)
SCHEMA_DIRS = frozenset({"schemas", "serializers", "validators", "dtos", "dto"})
```

Añadir función `_find_schema_files` antes de `run()`:

```python
def _find_schema_files(files: list[FileInfo], root: Path) -> list[str]:
    """Detecta archivos de schema/validación por directorio o contenido."""
    result = []
    for fi in files:
        if fi.language not in ("python", "typescript", "javascript"):
            continue
        parts = Path(fi.rel_path).parts
        in_schema_dir = any(p.lower() in SCHEMA_DIRS for p in parts)
        if in_schema_dir:
            result.append(fi.rel_path)
            continue
        try:
            source = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
            if RE_SCHEMA_FILE.search(source):
                result.append(fi.rel_path)
        except OSError:
            continue
    return result[:20]
```

En la función `run()`, añadir después de `middleware_files = [...]`:

```python
schema_files = _find_schema_files(files, root)
```

Añadir `"schema_files": schema_files` al dict `result`:

```python
result = {
    "framework": framework,
    "schema_files": schema_files,
    "blueprints": blueprints_result,
    "webhooks": webhooks_result,
    "middleware_files": middleware_files[:10],
}
```

Para `test_file` por blueprint: en el bloque que construye `blueprints_result`, al crear el dict de cada blueprint, añadir `test_file`:

Reemplazar el append de `blueprints_result`:

```python
if normal_endpoints:
    bp_file = bp_info["file"]
    blueprints_result.append({
        "name": bp_info["name"],
        "file": bp_file,
        "prefix": bp_info["prefix"],
        "test_file": find_test_file(bp_file, files),
        "endpoints": normal_endpoints,
    })
```

- [ ] **Step 4: Actualizar `claude/schemas/api-map.json`**

Añadir `"schema_files"` al raíz y `"test_file"` en blueprint items:

En `"required"` del objeto raíz, añadir `"schema_files"`:
```json
"required": ["framework", "blueprints", "webhooks", "middleware_files", "schema_files"],
```

En `"properties"` del raíz, añadir:
```json
"schema_files": { "type": "array", "items": { "type": "string" } }
```

En blueprint items, añadir `"test_file"` en `"properties"` y en `"required"`:
```json
"required": ["name", "file", "prefix", "test_file", "endpoints"],
"properties": {
  ...
  "test_file": { "type": ["string", "null"] }
}
```

- [ ] **Step 5: Correr tests**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_analyzer_api.py -v
```
Expected: todos PASS

- [ ] **Step 6: Commit**

```bash
cd /home/siemprearmando/agentes/losgretis
git add claude/hooks/analyzers/api.py claude/schemas/api-map.json claude/hooks/tests/test_analyzer_api.py
git commit -m "feat(api): add schema_files and test_file per blueprint to API_MAP"
```

---

## Task 6: `db.py` — añadir `test_file` por modelo; actualizar schema

**Files:**
- Modify: `claude/hooks/analyzers/db.py`
- Modify: `claude/schemas/db-map.json`
- Test: `claude/hooks/tests/test_analyzers_existing.py`

- [ ] **Step 1: Escribir test que falla**

En `claude/hooks/tests/test_analyzers_existing.py`, añadir:

```python
def test_db_map_models_have_test_file(tmp_path):
    from analyzers.core import walk_repo, detect_stack
    from analyzers.db import run

    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "user.py").write_text(
        "from sqlalchemy import Column, Integer, String\n"
        "from sqlalchemy.ext.declarative import declarative_base\n"
        "Base = declarative_base()\n"
        "class User(Base):\n    __tablename__ = 'users'\n    id = Column(Integer, primary_key=True)\n    email = Column(String)\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_user.py").write_text("def test_user_model(): pass\n")
    (tmp_path / ".git").mkdir()

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    assert result["models"], "debe detectar al menos un modelo"
    for model in result["models"]:
        assert "test_file" in model, f"modelo {model['name']} no tiene test_file"
```

- [ ] **Step 2: Correr test (debe fallar)**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_analyzers_existing.py::test_db_map_models_have_test_file -v
```
Expected: FAIL — `KeyError: 'test_file'`

- [ ] **Step 3: Actualizar `db.py`**

Añadir import al inicio:

```python
from analyzers.core import (
    FileInfo, ModelInfo, detect_stack, walk_repo,
    _walk_repo_models_cache, find_test_file,
)
```

En la construcción de `result["models"]`, pasar `files` al helper:

```python
result = {
    ...
    "models": [
        {
            "name": m.name, "table": m.table, "file": m.file,
            "test_file": find_test_file(m.file, files),
            "fields": m.fields, "relationships": m.relationships,
        }
        for m in sorted(real_models, key=lambda x: x.name)
    ],
    ...
}
```

- [ ] **Step 4: Actualizar `claude/schemas/db-map.json`**

En model items, añadir `"test_file"` a `"required"` y `"properties"`:

```json
"required": ["name", "table", "file", "test_file", "fields", "relationships"],
"properties": {
  ...
  "test_file": { "type": ["string", "null"] }
}
```

- [ ] **Step 5: Correr tests**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_analyzers_existing.py -v
```
Expected: todos PASS

- [ ] **Step 6: Commit**

```bash
cd /home/siemprearmando/agentes/losgretis
git add claude/hooks/analyzers/db.py claude/schemas/db-map.json claude/hooks/tests/test_analyzers_existing.py
git commit -m "feat(db): add test_file per model to DB_MAP"
```

---

## Task 7: `services.py` — añadir `test_file` por integración; actualizar schema

**Files:**
- Modify: `claude/hooks/analyzers/services.py`
- Modify: `claude/schemas/services-map.json`
- Test: `claude/hooks/tests/test_analyzer_services.py`

**Nota:** `services.py` ya genera `env_vars` por integración ✅. El MAP usa `"files": [...]` (lista), no `"file"` singular — se mantiene así. `test_file` se deriva del primer archivo en `files`.

- [ ] **Step 1: Escribir test que falla**

En `claude/hooks/tests/test_analyzer_services.py`, añadir:

```python
def test_services_map_integrations_have_test_file(tmp_path):
    from analyzers.core import walk_repo, detect_stack
    from analyzers.services import run

    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "stripe_service.py").write_text(
        "import stripe\nSTRIPE_KEY = os.getenv('STRIPE_SECRET_KEY')\ndef charge(amount): pass\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_stripe_service.py").write_text("def test_charge(): pass\n")
    (tmp_path / ".git").mkdir()

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    for integration in result["integrations"]:
        assert "test_file" in integration, f"integración {integration['name']} no tiene test_file"
```

- [ ] **Step 2: Correr test (debe fallar)**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_analyzer_services.py::test_services_map_integrations_have_test_file -v
```
Expected: FAIL — `KeyError: 'test_file'`

- [ ] **Step 3: Actualizar `services.py`**

Añadir import:

```python
from analyzers.core import FileInfo, detect_stack, walk_repo, find_test_file
```

En `_detect_integrations`, en la construcción de cada integración, añadir `"test_file": None` inicial:

```python
integrations[sdk_name] = {
    "name": sdk_name,
    "type": sdk_type,
    "files": [],
    "functions": [],
    "env_vars": [],
    "test_file": None,
}
```

En la función `run()`, después de `integrations = _detect_integrations(files, root, stack)`, añadir:

```python
# Añadir test_file derivado del primer archivo de cada integración
for integration in integrations:
    if integration["files"]:
        integration["test_file"] = find_test_file(integration["files"][0], files)
```

- [ ] **Step 4: Actualizar `claude/schemas/services-map.json`**

Añadir `"test_file"` a integration items:

```json
"required": ["name", "type", "files", "functions", "env_vars", "test_file"],
"properties": {
  ...
  "test_file": { "type": ["string", "null"] }
}
```

- [ ] **Step 5: Correr tests**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_analyzer_services.py -v
```
Expected: todos PASS

- [ ] **Step 6: Commit**

```bash
cd /home/siemprearmando/agentes/losgretis
git add claude/hooks/analyzers/services.py claude/schemas/services-map.json claude/hooks/tests/test_analyzer_services.py
git commit -m "feat(services): add test_file per integration to SERVICES_MAP"
```

---

## Task 8: `jobs.py` — añadir `test_file` por job; actualizar schema

**Files:**
- Modify: `claude/hooks/analyzers/jobs.py`
- Modify: `claude/schemas/jobs-map.json`
- Test: `claude/hooks/tests/test_analyzer_jobs.py`

- [ ] **Step 1: Escribir test que falla**

En `claude/hooks/tests/test_analyzer_jobs.py`, añadir:

```python
def test_jobs_map_jobs_have_test_file(tmp_path):
    from analyzers.core import walk_repo, detect_stack
    from analyzers.jobs import run

    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "email_tasks.py").write_text(
        "from celery import shared_task\n@shared_task\ndef send_welcome_email(user_id): pass\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_email_tasks.py").write_text("def test_send_welcome_email(): pass\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / "requirements.txt").write_text("celery==5.3.0\n")

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    for job in result["jobs"]:
        assert "test_file" in job, f"job {job['function']} no tiene test_file"
```

- [ ] **Step 2: Correr test (debe fallar)**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_analyzer_jobs.py::test_jobs_map_jobs_have_test_file -v
```
Expected: FAIL — `KeyError: 'test_file'`

- [ ] **Step 3: Actualizar `jobs.py`**

Añadir import:

```python
from analyzers.core import FileInfo, detect_stack, walk_repo, find_test_file
```

En la función `run()`, después de deduplicar jobs, añadir `test_file` a cada job:

```python
# Añadir test_file a cada job
for job in unique_jobs:
    job["test_file"] = find_test_file(job["file"], files)
```

- [ ] **Step 4: Actualizar `claude/schemas/jobs-map.json`**

En job items, añadir `"test_file"` a `"required"` y `"properties"`:

```json
"required": ["file", "function", "trigger", "schedule", "description", "test_file"],
"properties": {
  ...
  "test_file": { "type": ["string", "null"] }
}
```

- [ ] **Step 5: Correr tests**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/test_analyzer_jobs.py -v
```
Expected: todos PASS

- [ ] **Step 6: Commit**

```bash
cd /home/siemprearmando/agentes/losgretis
git add claude/hooks/analyzers/jobs.py claude/schemas/jobs-map.json claude/hooks/tests/test_analyzer_jobs.py
git commit -m "feat(jobs): add test_file per job to JOBS_MAP"
```

---

## Task 9: `query-map.json` schema — añadir `test_file`

**Files:**
- Modify: `claude/schemas/query-map.json`

`query.py` ya usa `build_query_entry` que fue actualizado en Task 3 para incluir `test_file`. Solo falta el schema.

- [ ] **Step 1: Actualizar `claude/schemas/query-map.json`**

En file items, añadir `"test_file"` a `"required"` y `"properties"`:

```json
"required": ["path", "role", "functions", "query_examples", "test_file"],
"properties": {
  "path":           { "type": "string" },
  "role":           { "type": "string" },
  "functions":      { "type": "array", "items": { "type": "string" } },
  "query_examples": { "type": "array", "items": { "type": "string" } },
  "test_file":      { "type": ["string", "null"] }
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/siemprearmando/agentes/losgretis
git add claude/schemas/query-map.json
git commit -m "feat(query): add test_file to QUERY_MAP schema"
```

---

## Task 10: Actualizar `reader-context.json` schema

**Files:**
- Modify: `claude/schemas/reader-context.json`

- [ ] **Step 1: Añadir `test_file` a `file_hint` definition**

En `"$defs"."file_hint"."properties"`, añadir:

```json
"test_file": {
  "type": ["string", "null"],
  "description": "Ruta del archivo de test asociado, si existe."
}
```

- [ ] **Step 2: Añadir campos raíz nuevos**

En `"properties"` del schema raíz, añadir:

```json
"problems_in_scope": {
  "type": "array",
  "description": "Problemas detectados en archivos involucrados en esta tarea.",
  "items": {
    "type": "object",
    "properties": {
      "file":        { "type": "string" },
      "type":        { "type": "string" },
      "description": { "type": "string" }
    }
  }
},
"env_vars_needed": {
  "type": "array",
  "items": { "type": "string" },
  "description": "Variables de entorno necesarias para las integraciones en scope."
},
"schema_files": {
  "type": "array",
  "items": { "type": "string" },
  "description": "Archivos de schema/validación relevantes para la tarea."
}
```

- [ ] **Step 3: Actualizar enums de readers y maps**

En `"primary_reader"` enum, añadir los tres readers nuevos:

```json
"enum": ["project-reader", "db-reader", "query-reader", "ui-reader",
         "api-reader", "services-reader", "jobs-reader"]
```

En `"selected_readers"` items enum, igual:

```json
"enum": ["project-reader", "db-reader", "query-reader", "ui-reader",
         "api-reader", "services-reader", "jobs-reader"]
```

En `"maps_used"` items enum, añadir los tres MAPs nuevos:

```json
"enum": ["PROJECT_MAP.json", "DB_MAP.json", "QUERY_MAP.json", "UI_MAP.json",
         "API_MAP.json", "SERVICES_MAP.json", "JOBS_MAP.json"]
```

- [ ] **Step 4: Commit**

```bash
cd /home/siemprearmando/agentes/losgretis
git add claude/schemas/reader-context.json
git commit -m "feat(schema): update reader-context — test_file, problems_in_scope, env_vars_needed, schema_files, reader enums"
```

---

## Task 11: Verificación final end-to-end

**Files:**
- Read: todos los MAPs generados y schemas

- [ ] **Step 1: Correr suite completa de tests**

```bash
cd /home/siemprearmando/agentes/losgretis/claude/hooks
python -m pytest tests/ -v
```
Expected: todos PASS, sin errores

- [ ] **Step 2: Correr pre-commit para validar integridad del plugin**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 claude/hooks/pre-commit.py
```
Expected: sin errores de validación

- [ ] **Step 3: Generar MAPs con analyze-repo.py sobre este mismo repo**

```bash
cd /home/siemprearmando/agentes/losgretis
python3 claude/hooks/analyze-repo.py --force
```
Expected: sin errores, archivos generados en `.claude/maps/`

- [ ] **Step 4: Verificar estructura de PROJECT_MAP generado**

```bash
python3 -c "
import json
from pathlib import Path
data = json.loads(Path('.claude/maps/PROJECT_MAP.json').read_text())
assert 'modules' in data, 'modules ausente'
assert 'problems' in data, 'problems ausente'
# Verificar estructura de cada módulo
for role, entries in data['modules'].items():
    for e in entries:
        for f in ('path','purpose','search_keywords','symbols','test_file','related_to'):
            assert f in e, f'campo {f} ausente en modules[{role}]'
print('✓ PROJECT_MAP estructura OK')
print(f'  modules roles: {list(data[\"modules\"].keys())}')
print(f'  total archivos en modules: {sum(len(v) for v in data[\"modules\"].values())}')
print(f'  problems: {len(data[\"problems\"])}')
"
```
Expected: `✓ PROJECT_MAP estructura OK` con conteos

- [ ] **Step 5: Verificar API_MAP y DB_MAP**

```bash
python3 -c "
import json
from pathlib import Path

# API_MAP
api = json.loads(Path('.claude/maps/API_MAP.json').read_text())
assert 'schema_files' in api, 'schema_files ausente en API_MAP'
for bp in api.get('blueprints', []):
    assert 'test_file' in bp, f'test_file ausente en blueprint {bp[\"name\"]}'
print(f'✓ API_MAP: {len(api[\"blueprints\"])} blueprints, {len(api[\"schema_files\"])} schema files')

# DB_MAP
db = json.loads(Path('.claude/maps/DB_MAP.json').read_text())
for m in db.get('models', []):
    assert 'test_file' in m, f'test_file ausente en modelo {m[\"name\"]}'
print(f'✓ DB_MAP: {len(db[\"models\"])} modelos')
"
```
Expected: output sin AssertionError

- [ ] **Step 6: Commit final**

```bash
cd /home/siemprearmando/agentes/losgretis
git add .claude/maps/
git commit -m "chore: regenerate MAPs with enriched fields — modules, problems, test_file, schema_files"
```
