# analyze-repo Refactor — Domain Analyzers + PROJECT_MAP Routing Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactorizar `analyze-repo.py` en un orquestador + módulos por dominio, rediseñar `PROJECT_MAP.json` como routing index con `domains`, y añadir 3 nuevos analyzers (api, services, jobs).

**Architecture:** El monolito `analyze-repo.py` (~1700 líneas) se divide en `analyzers/core.py` (infraestructura compartida) + 7 módulos independientes, cada uno con una función `run()` y modo standalone. El orquestador llama `core.walk_repo()` una sola vez y delega en cada analyzer. `PROJECT_MAP.json` pasa de tener `modules` a tener `domains` con `trigger_keywords` para routing dinámico en `reader.md`.

**Tech Stack:** Python 3.9+, ast, re, subprocess, pathlib, dataclasses. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-03-25-analyze-repo-refactor-design.md`

---

## Mapa de archivos

| Acción | Archivo | Responsabilidad |
|--------|---------|-----------------|
| Crear | `.claude/hooks/analyzers/__init__.py` | Package vacío |
| Crear | `.claude/hooks/analyzers/core.py` | Walk, AST, git, dataclasses, constantes — extraídos de analyze-repo.py |
| Crear | `.claude/hooks/analyzers/project.py` | Genera PROJECT_MAP.json (nuevo formato routing index) |
| Crear | `.claude/hooks/analyzers/db.py` | Genera DB_MAP.json (lógica de build_db_map existente) |
| Crear | `.claude/hooks/analyzers/query.py` | Genera QUERY_MAP.json (lógica de build_query_map existente) |
| Crear | `.claude/hooks/analyzers/ui.py` | Genera UI_MAP.json (lógica de build_ui_map existente) |
| Crear | `.claude/hooks/analyzers/api.py` | Genera API_MAP.json (nuevo) |
| Crear | `.claude/hooks/analyzers/services.py` | Genera SERVICES_MAP.json (nuevo) |
| Crear | `.claude/hooks/analyzers/jobs.py` | Genera JOBS_MAP.json (nuevo) |
| Modificar | `.claude/hooks/analyze-repo.py` | Thin orchestrator — elimina toda la lógica interna |
| Modificar | `.claude/agents/readers/reader.md` | Pasos 2, 3, 4, 5 actualizados para routing dinámico |
| Modificar | `.claude/schemas/project-map.json` | Reemplaza modules/structure por domains |
| Modificar | `.claude/hooks/pre-commit.py` | Añade 3 nuevos MAPs, schemas y reader agents |
| Crear | `.claude/schemas/api-map.json` | JSON Schema para API_MAP.json |
| Crear | `.claude/schemas/services-map.json` | JSON Schema para SERVICES_MAP.json |
| Crear | `.claude/schemas/jobs-map.json` | JSON Schema para JOBS_MAP.json |
| Crear | `.claude/agents/readers/api-reader.md` | Reader agent para API_MAP.json |
| Crear | `.claude/agents/readers/services-reader.md` | Reader agent para SERVICES_MAP.json |
| Crear | `.claude/agents/readers/jobs-reader.md` | Reader agent para JOBS_MAP.json |
| Crear | `.claude/maps/API_MAP.json` | Generado por analyzers/api.py (vacío inicial) |
| Crear | `.claude/maps/SERVICES_MAP.json` | Generado por analyzers/services.py (vacío inicial) |
| Crear | `.claude/maps/JOBS_MAP.json` | Generado por analyzers/jobs.py (vacío inicial) |

---

## Task 1: Crear `analyzers/core.py` con infraestructura compartida

Extraer de `analyze-repo.py` todo lo que no es lógica de MAP: constantes, dataclasses, walk, AST, git.

**Files:**
- Crear: `.claude/hooks/analyzers/__init__.py`
- Crear: `.claude/hooks/analyzers/core.py`
- Crear: `tests/test_core.py`

- [ ] **Step 1: Crear el package vacío**

```bash
mkdir -p .claude/hooks/analyzers
touch .claude/hooks/analyzers/__init__.py
```

- [ ] **Step 2: Escribir el test de core.py**

Crear `tests/test_core.py`:

```python
"""Tests para analyzers/core.py — infraestructura compartida."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude" / "hooks"))

from analyzers.core import (
    FileInfo, FunctionInfo, ModelInfo, ProjectSummary,
    walk_repo, detect_stack, git_hotspots, git_cochange,
    IGNORE_DIRS, SOURCE_EXTS, ROLE_PATTERNS,
)


def test_fileinfo_defaults():
    fi = FileInfo(rel_path="main.py", language="python", role="entry_point", size=100)
    assert fi.classes == []
    assert fi.functions == []
    assert fi.has_db_access == False
    assert fi.function_infos == []


def test_walk_repo_returns_fileinfos(tmp_path):
    (tmp_path / "app.py").write_text("def hello(): pass")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "foo.js").write_text("// ignored")
    files = walk_repo(tmp_path)
    paths = [f.rel_path for f in files]
    assert any("app.py" in p for p in paths)
    assert not any("node_modules" in p for p in paths)


def test_walk_repo_parses_python_functions(tmp_path):
    (tmp_path / "service.py").write_text(
        "def create_order(): pass\ndef cancel_order(): pass\n"
    )
    files = walk_repo(tmp_path)
    svc = next(f for f in files if "service.py" in f.rel_path)
    assert "create_order" in svc.functions
    assert "cancel_order" in svc.functions


def test_detect_stack_from_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==3.1.0\nSQLAlchemy==2.0.38\n")
    stack = detect_stack(tmp_path)
    assert "Flask" in stack
    assert "SQLAlchemy" in stack


def test_git_hotspots_returns_empty_without_git(tmp_path):
    result = git_hotspots(tmp_path)
    assert result == []


def test_git_cochange_returns_empty_without_git(tmp_path):
    result = git_cochange(tmp_path)
    assert result == {}
```

- [ ] **Step 3: Ejecutar tests para verificar que fallan (core.py no existe aún)**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_core.py -v 2>&1 | head -30
```
Esperado: `ModuleNotFoundError` o `ImportError`

- [ ] **Step 4: Crear `analyzers/core.py` moviendo código de `analyze-repo.py`**

Crear `.claude/hooks/analyzers/core.py`. Mover EXACTAMENTE las siguientes secciones de `analyze-repo.py` (sin modificar la lógica):

1. **Imports** (líneas 21-38): `from __future__ import annotations`, todos los imports stdlib, `pathspec`
2. **Constantes** (líneas 46-183): `IGNORE_DIRS`, `IGNORE_EXTS`, `SOURCE_EXTS`, `ROLE_PATTERNS`, `FOLDER_ROLES`, `FRAMEWORK_MAP`, `RE_DB_PY`, `RE_DB_JS`
3. **Dataclasses** (líneas 201-261): `FileInfo`, `ModelField`, `FunctionInfo`, `ModelInfo`, `ProjectSummary`
4. **Funciones de detección** (líneas 283-416): `detect_stack`, `detect_project_name`, `detect_readme_summary`, `classify_role`, `should_ignore`, `load_gitignore_spec`, `scan_structure`, `walk_source_files`
5. **Extracción AST** (líneas 437-800): `extract_query_examples`, `extract_python`, `extract_js_ts`, `extract_prisma_models`
6. **Git** (líneas 802-935): `analyze_git`, `analyze_git_extended`
7. **Enriquecimiento semántico** (líneas 1056-1203): `extract_keywords`, `infer_purpose`, `find_related`, `build_symbols`, `build_module_entry`, `build_query_entry`, `resolve_dependencies`
8. **Arquitectura e smells** (líneas 997-1054): `infer_architecture`, `detect_code_smells`
9. **Validación** (líneas 1490-1588): `detect_dependency_cycles`, `validate_maps`

Añadir al final de `core.py` las **funciones públicas de alto nivel** que los analyzers usarán:

```python
# ─── API pública para analyzers ───────────────────────────────────────────────

def walk_repo(root: Path) -> list[FileInfo]:
    """Recorre el repo y retorna lista de FileInfo. Llama una sola vez desde el orquestador."""
    gitignore_spec = load_gitignore_spec(root)
    source_files = walk_source_files(root, gitignore_spec)
    all_files: list[FileInfo] = []
    all_models: list[ModelInfo] = []

    for fpath in source_files:
        lang = SOURCE_EXTS.get(fpath.suffix, "other")
        if lang == "python":
            fi = extract_python(fpath, root)
        elif lang in ("typescript", "javascript", "vue", "svelte"):
            fi = extract_js_ts(fpath, root)
        else:
            rel = str(fpath.relative_to(root))
            fi = FileInfo(rel, lang, classify_role(rel), fpath.stat().st_size)
        all_files.append(fi)
        all_models.extend(fi.__dict__.pop("_models", []))

    # Adjuntar modelos deduplicados como atributo de conveniencia en primer FileInfo
    seen: set[str] = set()
    unique_models: list[ModelInfo] = []
    for m in all_models + extract_prisma_models(root):
        if m.name not in seen:
            seen.add(m.name)
            unique_models.append(m)

    # Exponer en el módulo para que los analyzers los lean
    _walk_repo_models_cache.clear()
    _walk_repo_models_cache.extend(unique_models)

    return all_files

# Cache temporal de modelos — los analyzers que necesiten modelos leen esto
_walk_repo_models_cache: list[ModelInfo] = []


def git_hotspots(root: Path) -> list[tuple[str, int]]:
    """Retorna [(archivo, n_commits)]. Devuelve [] si no hay historial git."""
    hotspots, _ = analyze_git(root)
    return hotspots


def git_cochange(root: Path) -> dict[str, list[str]]:
    """Retorna {archivo: [archivos_cochangiados]}. Devuelve {} si no hay historial git."""
    _, cochange = analyze_git(root)
    return cochange
```

- [ ] **Step 5: Ejecutar tests para verificar que pasan**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_core.py -v
```
Esperado: todos PASS

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks/analyzers/ tests/test_core.py
git commit -m "feat: create analyzers/core.py with shared infrastructure extracted from analyze-repo.py"
```

---

## Task 2: Crear `analyzers/project.py` — nuevo formato PROJECT_MAP.json

El nuevo PROJECT_MAP.json tiene `domains` en lugar de `modules`. Esta es la pieza central del refactor.

**Files:**
- Crear: `.claude/hooks/analyzers/project.py`
- Crear: `tests/test_analyzer_project.py`

- [ ] **Step 1: Escribir el test**

Crear `tests/test_analyzer_project.py`:

```python
"""Tests para analyzers/project.py — genera PROJECT_MAP.json con routing index."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude" / "hooks"))

from analyzers import core
from analyzers.project import run, DOMAIN_KEYWORDS


def _make_project(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==3.1.0\nSQLAlchemy==2.0.38\n")
    (tmp_path / "main.py").write_text('"""Entry point."""\ndef create_app(): pass')
    (tmp_path / "blueprints").mkdir()
    (tmp_path / "blueprints" / "pedidos.py").write_text(
        'from flask import Blueprint\nbp = Blueprint("pedidos", __name__)\n'
        '@bp.route("/", methods=["GET"])\ndef listar(): pass'
    )
    (tmp_path / "models.py").write_text(
        'class Pedido(Base):\n    __tablename__ = "pedidos"\n    id = Column(Integer)\n'
    )
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_creates_project_map_json(tmp_path):
    root, maps_dir = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    map_path = maps_dir / "PROJECT_MAP.json"
    # run() escribe en PLUGIN_DIR/maps — en tests usamos el root de tmp_path como root
    # Verificamos el dict devuelto
    assert "domains" in result
    assert "name" in result
    assert "stack" in result
    assert "architecture" in result
    assert "entry_points" in result


def test_domains_section_has_required_keys(tmp_path):
    root, _ = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    for domain_name, domain_data in result["domains"].items():
        assert "map" in domain_data, f"{domain_name} missing 'map'"
        assert "reader" in domain_data, f"{domain_name} missing 'reader'"
        assert "summary" in domain_data, f"{domain_name} missing 'summary'"
        assert "trigger_keywords" in domain_data, f"{domain_name} missing 'trigger_keywords'"
        assert isinstance(domain_data["trigger_keywords"], list)
        assert len(domain_data["trigger_keywords"]) > 0


def test_result_has_no_modules_key(tmp_path):
    root, _ = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert "modules" not in result, "PROJECT_MAP no debe tener 'modules'"
    assert "structure" not in result, "PROJECT_MAP no debe tener 'structure'"


def test_all_7_domains_present(tmp_path):
    root, _ = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    expected = {"db", "query", "ui", "api", "services", "jobs"}
    for domain in expected:
        assert domain in result["domains"], f"Dominio '{domain}' falta en domains"
```

- [ ] **Step 2: Ejecutar tests — deben fallar**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_analyzer_project.py -v 2>&1 | head -20
```
Esperado: `ModuleNotFoundError: No module named 'analyzers.project'`

- [ ] **Step 3: Crear `analyzers/project.py`**

Crear `.claude/hooks/analyzers/project.py`:

```python
#!/usr/bin/env python3
"""
analyzers/project.py — Genera PROJECT_MAP.json como routing index.

El MAP resultante tiene `domains` con trigger_keywords para routing dinámico
en reader.md. No incluye `modules` archivo por archivo.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyzers.core import (
    FileInfo, detect_stack, git_hotspots, git_cochange,
    walk_repo, detect_project_name, detect_readme_summary,
    infer_architecture, scan_structure,
    _walk_repo_models_cache,
    PLUGIN_DIR, MAPS_DIR,
)

# Dominios fijos — siempre se incluyen todos en el PROJECT_MAP.
# El reader usa trigger_keywords para decidir cuáles activar por petición.
DOMAIN_KEYWORDS: dict[str, dict] = {
    "db": {
        "map": "DB_MAP.json",
        "reader": "db-reader",
        "trigger_keywords": [
            "modelo", "tabla", "migración", "migración", "campo", "relación",
            "ORM", "schema", "base de datos", "database", "migration", "model",
            "table", "field", "relationship", "SQLAlchemy", "Prisma", "TypeORM",
        ],
    },
    "query": {
        "map": "QUERY_MAP.json",
        "reader": "query-reader",
        "trigger_keywords": [
            "consulta", "query", "filtro", "join", "rendimiento", "índice",
            "filter", "performance", "index", "select", "aggregate", "repository",
            "manager", "acceso a datos", "data access",
        ],
    },
    "ui": {
        "map": "UI_MAP.json",
        "reader": "ui-reader",
        "trigger_keywords": [
            "vista", "componente", "pantalla", "formulario", "plantilla",
            "frontend", "view", "component", "template", "page", "layout",
            "UI", "interfaz", "interface", "render", "HTML", "CSS",
        ],
    },
    "api": {
        "map": "API_MAP.json",
        "reader": "api-reader",
        "trigger_keywords": [
            "endpoint", "ruta", "blueprint", "HTTP", "request", "response",
            "webhook", "API", "route", "GET", "POST", "PUT", "DELETE", "PATCH",
            "REST", "controller", "handler", "middleware",
        ],
    },
    "services": {
        "map": "SERVICES_MAP.json",
        "reader": "services-reader",
        "trigger_keywords": [
            "servicio", "integración", "externo", "Twilio", "Stripe", "Redis",
            "Monei", "SMS", "email", "pago", "payment", "service", "integration",
            "external", "SDK", "API externa", "tercero", "third-party",
        ],
    },
    "jobs": {
        "map": "JOBS_MAP.json",
        "reader": "jobs-reader",
        "trigger_keywords": [
            "tarea", "job", "celery", "queue", "cola", "cron", "programado",
            "worker", "scheduled", "task", "background", "async task",
            "periodic", "interval",
        ],
    },
}


def _build_domain_summary(domain: str, root: Path) -> str:
    """Genera un summary breve leyendo el MAP del dominio si existe."""
    maps_dir = root / ".claude" / "maps"
    map_path = maps_dir / DOMAIN_KEYWORDS[domain]["map"]
    if not map_path.exists():
        return f"MAP no generado aún — ejecuta analyze-repo.py --maps {domain}"
    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "MAP inválido"

    if domain == "db":
        models = data.get("models", [])
        orm = data.get("orm") or data.get("database", "")
        return f"{len(models)} modelos {orm}".strip()
    if domain == "query":
        files = data.get("files", [])
        return f"{len(files)} archivos con acceso a datos, patrón: {data.get('pattern', 'desconocido')}"
    if domain == "ui":
        views = data.get("views", {})
        return f"{sum(len(v) for v in views.values())} archivos de UI en {len(views)} carpetas"
    if domain == "api":
        blueprints = data.get("blueprints", [])
        n_endpoints = sum(len(b.get("endpoints", [])) for b in blueprints)
        return f"{len(blueprints)} blueprints, {n_endpoints} endpoints"
    if domain == "services":
        integrations = data.get("integrations", [])
        return f"{len(integrations)} integraciones externas"
    if domain == "jobs":
        jobs = data.get("jobs", [])
        scheduler = data.get("scheduler") or "ninguno"
        return f"Scheduler: {scheduler}, {len(jobs)} jobs"
    return ""


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera PROJECT_MAP.json como routing index. Escribe en .claude/maps/. Devuelve el dict."""
    name, description = detect_project_name(root)
    if not description:
        description = detect_readme_summary(root)

    # Para infer_architecture necesitamos un objeto con folder_structure
    folder_structure = scan_structure(root)

    # Construir objeto mínimo que infer_architecture necesita
    class _MinProj:
        def __init__(self):
            self.folder_structure = folder_structure
            self.stack = stack

    architecture = infer_architecture(_MinProj())

    # Entry points
    entry_points = [f.rel_path for f in files if f.role == "entry_point"]

    # Languages
    from collections import Counter
    lang_counts = Counter(f.language for f in files if f.language not in ("html", "sql", "other"))
    languages = [lang for lang, _ in lang_counts.most_common()]

    # Hotspots y cochange desde git
    hotspots_raw = git_hotspots(root)
    cochange_raw = git_cochange(root)
    known_paths = {f.rel_path for f in files}

    hotspots = [
        {"file": f, "commits": c}
        for f, c in hotspots_raw[:10]
        if f in known_paths
    ]
    cochange = {
        f: [p for p in partners if p in known_paths]
        for f, partners in list(cochange_raw.items())[:20]
        if f in known_paths
    }

    # Construir sección domains (siempre incluye los 7)
    domains: dict[str, dict] = {}
    for domain_name, meta in DOMAIN_KEYWORDS.items():
        domains[domain_name] = {
            "map": meta["map"],
            "reader": meta["reader"],
            "summary": _build_domain_summary(domain_name, root),
            "trigger_keywords": meta["trigger_keywords"],
        }

    result = {
        "name": name,
        "description": description,
        "languages": languages,
        "architecture": architecture,
        "stack": stack,
        "entry_points": entry_points,
        "domains": domains,
        "cochange": cochange,
        "hotspots": hotspots,
    }

    # Escribir el MAP
    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    out_path = maps_dir / "PROJECT_MAP.json"
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    p = argparse.ArgumentParser(description="Genera PROJECT_MAP.json")
    p.add_argument("--root", default=None)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    if args.root:
        repo_root = Path(args.root).resolve()
    else:
        # Busca .claude/ subiendo desde cwd
        cwd = Path.cwd()
        for candidate in [cwd, *cwd.parents]:
            if (candidate / ".claude").exists():
                repo_root = candidate
                break
        else:
            repo_root = cwd

    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print(f"PROJECT_MAP.json generado en {repo_root / '.claude' / 'maps'}")
```

- [ ] **Step 4: Ejecutar tests**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_analyzer_project.py -v
```
Esperado: todos PASS

- [ ] **Step 5: Verificar output real con el proyecto existente**

```bash
python3 .claude/hooks/analyzers/project.py --root . --force 2>&1 | head -5
python3 -c "import json; d=json.load(open('.claude/maps/PROJECT_MAP.json')); print(list(d.keys())); print(list(d['domains'].keys()))"
```
Esperado: keys sin `modules`, con `domains` conteniendo los 7 dominios.

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks/analyzers/project.py tests/test_analyzer_project.py
git commit -m "feat: analyzers/project.py — PROJECT_MAP.json as routing index with domains"
```

---

## Task 3: Crear `analyzers/db.py`, `query.py`, `ui.py` (lógica existente migrada)

Mover las funciones `build_db_map`, `build_query_map`, `build_ui_map` de `analyze-repo.py` a módulos independientes.

**Files:**
- Crear: `.claude/hooks/analyzers/db.py`
- Crear: `.claude/hooks/analyzers/query.py`
- Crear: `.claude/hooks/analyzers/ui.py`
- Crear: `tests/test_analyzers_existing.py`

- [ ] **Step 1: Escribir tests**

Crear `tests/test_analyzers_existing.py`:

```python
"""Tests para db.py, query.py, ui.py — lógica migrada de analyze-repo.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude" / "hooks"))

from analyzers import core
from analyzers.db import run as run_db
from analyzers.query import run as run_query
from analyzers.ui import run as run_ui


def _make_flask_project(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\nSQLAlchemy==2.0.38\n"
    )
    (tmp_path / "models.py").write_text(
        'from sqlalchemy import Column, Integer, String\n'
        'from database import Base\n'
        'class Pedido(Base):\n'
        '    __tablename__ = "pedidos"\n'
        '    id = Column(Integer)\n'
        '    estado = Column(String)\n'
    )
    (tmp_path / "database.py").write_text("from sqlalchemy import create_engine")
    (tmp_path / "managers").mkdir()
    (tmp_path / "managers" / "pedido_manager.py").write_text(
        "from database import db\n"
        "def get_pedido(id):\n"
        "    return db.session.query(Pedido).filter_by(id=id).first()\n"
    )
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "pedidos.html").write_text("<html></html>")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_db_run_returns_required_keys(tmp_path):
    root, _ = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run_db(root, files, stack)
    assert "orm" in result
    assert "models" in result
    assert "connection_files" in result
    assert "migrations" in result


def test_db_run_detects_sqlalchemy_model(tmp_path):
    root, _ = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run_db(root, files, stack)
    model_names = [m["name"] for m in result["models"]]
    assert "Pedido" in model_names


def test_db_run_writes_file(tmp_path):
    root, maps_dir = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    run_db(root, files, stack)
    assert (maps_dir / "DB_MAP.json").exists()


def test_query_run_returns_required_keys(tmp_path):
    root, _ = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run_query(root, files, stack)
    assert "pattern" in result
    assert "files" in result
    assert "cochange_with_models" in result


def test_ui_run_returns_required_keys(tmp_path):
    root, _ = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run_ui(root, files, stack)
    assert "framework" in result
    assert "views" in result
    assert "routers" in result
```

- [ ] **Step 2: Ejecutar tests — deben fallar**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_analyzers_existing.py -v 2>&1 | head -20
```
Esperado: `ImportError`

- [ ] **Step 3: Crear `analyzers/db.py`**

Crear `.claude/hooks/analyzers/db.py`. Copiar la función `build_db_map` de `analyze-repo.py` (líneas 1392-1429) y adaptarla:

```python
#!/usr/bin/env python3
"""analyzers/db.py — Genera DB_MAP.json."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from analyzers.core import (
    FileInfo, ModelInfo, detect_stack, walk_repo,
    _walk_repo_models_cache, MAPS_DIR,
)

DB_ORMS = {
    "SQLAlchemy", "Django ORM", "TypeORM", "Prisma", "Mongoose",
    "Sequelize", "Drizzle", "Peewee", "Tortoise ORM", "MongoEngine", "PyMongo", "Knex",
}
DB_INFRA = ("SQL", "Postgres", "MySQL", "Mongo", "Redis", "SQLite", "Dynamo")


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    models: list[ModelInfo] = list(_walk_repo_models_cache)
    db_techs = [t for t in stack if t in DB_ORMS]
    db_infra = [t for t in stack if any(k in t for k in DB_INFRA)]
    migrations = [f.rel_path for f in files if f.role == "migration"]
    seeds = [m for m in migrations if "seed" in m.lower()]
    pure_migrations = [m for m in migrations if "seed" not in m.lower()]
    db_conn = [f.rel_path for f in files if f.role == "db_connection"]

    real_models = [
        m for m in models
        if any(k in m.file for k in ("model", "entit", "domain", "schema.prisma"))
        or m.file in ("models.py", "model.py")
        or (m.fields and len(m.fields) >= 2)
    ]

    result = {
        "orm": db_techs[0] if db_techs else None,
        "database": db_infra[0] if db_infra else None,
        "connection_files": db_conn,
        "models": [
            {"name": m.name, "table": m.table, "file": m.file,
             "fields": m.fields, "relationships": m.relationships}
            for m in sorted(real_models, key=lambda x: x.name)
        ],
        "migrations": pure_migrations,
        "seeds": seeds,
    }
    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "DB_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd()
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("DB_MAP.json generado.")
```

- [ ] **Step 4: Crear `analyzers/query.py`**

Crear `.claude/hooks/analyzers/query.py`. Adaptar `build_query_map` de `analyze-repo.py` (líneas 1432-1456):

```python
#!/usr/bin/env python3
"""analyzers/query.py — Genera QUERY_MAP.json."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from analyzers.core import (
    FileInfo, detect_stack, walk_repo, git_cochange,
    build_query_entry, _walk_repo_models_cache, MAPS_DIR,
)


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    models = list(_walk_repo_models_cache)
    cochange = git_cochange(root)
    db_files = [f for f in files if f.has_db_access and f.role != "test"]
    da_files = [f for f in files if f.role == "data_access"]
    all_query = list({f.rel_path: f for f in db_files + da_files}.values())
    all_query.sort(key=lambda f: f.rel_path)

    has_repo = any(f.role == "data_access" for f in all_query)
    pattern = "Manager / Repository" if has_repo else "Direct DB access"

    model_files = {m.file for m in models}
    cochange_with_models = []
    for f in all_query:
        partners = cochange.get(f.rel_path, [])
        model_partners = [p for p in partners if p in model_files]
        if model_partners:
            cochange_with_models.append({"file": f.rel_path, "cochanges": model_partners})

    result = {
        "pattern": pattern,
        "files": [build_query_entry(f, files, cochange) for f in all_query[:25]],
        "cochange_with_models": cochange_with_models[:10],
    }
    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "QUERY_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd()
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("QUERY_MAP.json generado.")
```

- [ ] **Step 5: Crear `analyzers/ui.py`**

Crear `.claude/hooks/analyzers/ui.py`. Adaptar `build_ui_map` de `analyze-repo.py` (líneas 1459-1487):

```python
#!/usr/bin/env python3
"""analyzers/ui.py — Genera UI_MAP.json."""
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path
from analyzers.core import FileInfo, detect_stack, walk_repo, MAPS_DIR

UI_FRAMEWORKS = {"React", "Vue", "Angular", "Svelte", "Solid", "Next.js", "Nuxt.js", "Gatsby"}
TEMPLATE_ENGINES = {"Jinja2", "Handlebars", "Nunjucks"}


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    ui_techs = [t for t in stack if t in UI_FRAMEWORKS]
    template_techs = [t for t in stack if t in TEMPLATE_ENGINES]
    ui_files = [f for f in files if f.role in ("template", "component")]

    by_folder: dict[str, list[str]] = defaultdict(list)
    for f in ui_files:
        folder = str(Path(f.rel_path).parent)
        by_folder[folder].append(Path(f.rel_path).name)

    route_files = [
        f.rel_path for f in files
        if f.role == "controller" and f.language in ("python", "typescript", "javascript")
    ]

    from analyzers.core import scan_structure
    folder_structure = scan_structure(root)
    static_dir = next(
        (k for k in folder_structure if k in ("static", "public", "assets")), None
    )

    result = {
        "framework": ui_techs[0] if ui_techs else None,
        "template_engine": template_techs[0] if template_techs else None,
        "views": {folder: sorted(files)[:12] for folder, files in sorted(by_folder.items())},
        "routers": route_files[:15],
        "static": static_dir,
    }
    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "UI_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd()
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("UI_MAP.json generado.")
```

- [ ] **Step 6: Ejecutar tests**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_analyzers_existing.py -v
```
Esperado: todos PASS

- [ ] **Step 7: Verificar standalone de cada uno**

```bash
python3 .claude/hooks/analyzers/db.py --root . 2>&1
python3 .claude/hooks/analyzers/query.py --root . 2>&1
python3 .claude/hooks/analyzers/ui.py --root . 2>&1
```
Esperado: cada uno imprime "X_MAP.json generado." sin errores

- [ ] **Step 8: Commit**

```bash
git add .claude/hooks/analyzers/db.py .claude/hooks/analyzers/query.py .claude/hooks/analyzers/ui.py tests/test_analyzers_existing.py
git commit -m "feat: analyzers/db.py, query.py, ui.py — migrate existing build functions to standalone modules"
```

---

## Task 4: Crear `analyzers/api.py` — API_MAP.json

Nuevo analyzer: detecta blueprints Flask, endpoints HTTP, webhooks y middleware.

**Files:**
- Crear: `.claude/hooks/analyzers/api.py`
- Crear: `.claude/maps/API_MAP.json` (vacío inicial)
- Crear: `tests/test_analyzer_api.py`

- [ ] **Step 1: Escribir tests**

Crear `tests/test_analyzer_api.py`:

```python
"""Tests para analyzers/api.py — genera API_MAP.json."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude" / "hooks"))

from analyzers import core
from analyzers.api import run


def _make_flask_api(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==3.1.0\n")
    bp_dir = tmp_path / "blueprints"
    bp_dir.mkdir()
    (bp_dir / "pedidos.py").write_text(
        'from flask import Blueprint\n'
        'from utils.auth import login_required\n'
        'bp = Blueprint("pedidos", __name__, url_prefix="/api/pedidos")\n\n'
        '@bp.route("/", methods=["GET"])\n'
        '@login_required\n'
        'def listar_pedidos():\n'
        '    pass\n\n'
        '@bp.route("/<int:pid>", methods=["PUT"])\n'
        'def actualizar_pedido(pid):\n'
        '    pass\n\n'
        '@bp.route("/webhook", methods=["POST"])\n'
        'def twilio_webhook():\n'
        '    pass\n'
    )
    (tmp_path / "utils").mkdir()
    (tmp_path / "utils" / "auth.py").write_text("def login_required(f): return f")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_returns_required_keys(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert "framework" in result
    assert "blueprints" in result
    assert "webhooks" in result
    assert "middleware_files" in result


def test_detects_flask_framework(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert result["framework"] == "Flask"


def test_detects_blueprint_with_endpoints(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert len(result["blueprints"]) >= 1
    bp = result["blueprints"][0]
    assert "name" in bp
    assert "file" in bp
    assert "prefix" in bp
    assert "endpoints" in bp
    assert len(bp["endpoints"]) >= 1


def test_webhook_classified_separately(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    # twilio_webhook debe estar en webhooks, no en endpoints normales
    all_endpoint_fns = [
        ep["function"]
        for bp in result["blueprints"]
        for ep in bp["endpoints"]
    ]
    webhook_fns = [w["function"] for w in result["webhooks"]]
    assert "twilio_webhook" in webhook_fns
    assert "twilio_webhook" not in all_endpoint_fns


def test_auth_required_detected(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    # listar_pedidos tiene @login_required
    for bp in result["blueprints"]:
        for ep in bp["endpoints"]:
            if ep["function"] == "listar_pedidos":
                assert ep["auth_required"] == True


def test_empty_project_returns_empty_structure(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run(tmp_path, files, stack)
    assert result["framework"] is None
    assert result["blueprints"] == []
    assert result["webhooks"] == []
```

- [ ] **Step 2: Ejecutar tests — deben fallar**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_analyzer_api.py -v 2>&1 | head -20
```
Esperado: `ImportError`

- [ ] **Step 3: Crear `analyzers/api.py`**

Crear `.claude/hooks/analyzers/api.py`:

```python
#!/usr/bin/env python3
"""
analyzers/api.py — Genera API_MAP.json.

Detecta:
- Blueprints Flask / routers FastAPI/Express con prefix y endpoints
- Webhooks (rutas con /webhook o /callback, o funciones con ese nombre)
- Archivos de middleware y decoradores de auth

Heurísticas de detección:
- auth_required: decoradores @login_required, @jwt_required, @token_required,
  @require_auth, @permission_required
- webhook: ruta contiene /webhook o /callback, O nombre de función contiene
  "webhook" o "callback"
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from analyzers.core import FileInfo, detect_stack, walk_repo, SOURCE_EXTS

# Patrones de auth
AUTH_DECORATORS = frozenset({
    "login_required", "jwt_required", "token_required",
    "require_auth", "permission_required", "auth_required",
})

# Frameworks por stack key
FRAMEWORK_KEYS = {
    "Flask": "Flask",
    "FastAPI": "FastAPI",
    "Express": "Express",
    "Fastify": "Fastify",
    "NestJS": "NestJS",
}

RE_BLUEPRINT = re.compile(
    r'(\w+)\s*=\s*Blueprint\s*\(\s*["\']([^"\']+)["\']'
    r'(?:.*?url_prefix\s*=\s*["\']([^"\']+)["\'])?',
    re.DOTALL,
)
RE_ROUTE = re.compile(
    r'@(\w+)\.route\s*\(\s*["\']([^"\']+)["\'](?:[^)]*methods\s*=\s*\[([^\]]+)\])?[^)]*\)'
)
RE_METHODS = re.compile(r'["\'](\w+)["\']')
RE_DECORATOR = re.compile(r'@([\w\.]+)')


def _is_webhook(route: str, func_name: str) -> bool:
    return (
        "webhook" in route.lower()
        or "callback" in route.lower()
        or "webhook" in func_name.lower()
        or "callback" in func_name.lower()
    )


def _analyze_flask_file(path: Path, root: Path) -> dict | None:
    """Analiza un archivo Python buscando blueprints Flask y sus rutas."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if "Blueprint" not in source and ".route" not in source:
        return None

    rel = str(path.relative_to(root))
    blueprints = []

    # Detectar blueprints definidos en este archivo
    bp_vars: dict[str, dict] = {}
    for m in RE_BLUEPRINT.finditer(source):
        var_name = m.group(1)
        bp_name = m.group(2)
        prefix = m.group(3) or ""
        bp_vars[var_name] = {"name": bp_name, "prefix": prefix, "file": rel, "endpoints": []}

    # Si no encontramos Blueprint pero sí hay .route, usar "app" como var genérica
    if not bp_vars and ".route" in source:
        bp_vars["app"] = {"name": Path(rel).stem, "prefix": "", "file": rel, "endpoints": []}

    if not bp_vars:
        return None

    # Parsear con AST para extraer endpoints con decoradores
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback a regex
        return _analyze_flask_file_regex(source, rel, bp_vars)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        func_name = node.name
        decorators_raw = []
        route_info = None
        auth_req = False

        for dec in node.decorator_list:
            try:
                dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else ""
            except Exception:
                dec_str = ""

            decorators_raw.append(dec_str)

            # Detectar auth
            dec_base = dec_str.split("(")[0].split(".")[-1]
            if dec_base in AUTH_DECORATORS:
                auth_req = True

            # Detectar ruta
            if ".route(" in dec_str:
                m = re.search(r'\.route\s*\(\s*["\']([^"\']+)["\']', dec_str)
                methods_m = re.search(r'methods\s*=\s*\[([^\]]+)\]', dec_str)
                if m:
                    route_path = m.group(1)
                    methods = (
                        [x.strip().strip("\"'") for x in methods_m.group(1).split(",")]
                        if methods_m else ["GET"]
                    )
                    # Identificar a qué blueprint pertenece
                    bp_var = dec_str.split(".route(")[0].split(".")[-2] if "." in dec_str else list(bp_vars.keys())[0]
                    route_info = (bp_var, route_path, methods)

        if route_info:
            bp_var, route_path, methods = route_info
            endpoint = {
                "function": func_name,
                "line": node.lineno,
                "methods": methods,
                "route": route_path,
                "auth_required": auth_req,
            }
            # Asignar al blueprint correcto (o al primero si no hay match exacto)
            target_bp = bp_vars.get(bp_var) or list(bp_vars.values())[0]
            target_bp["endpoints"].append(endpoint)

    return bp_vars


def _analyze_flask_file_regex(source: str, rel: str, bp_vars: dict) -> dict:
    """Fallback regex para archivos con SyntaxError."""
    for m in RE_ROUTE.finditer(source):
        bp_var = m.group(1)
        route_path = m.group(2)
        methods_raw = m.group(3) or '"GET"'
        methods = RE_METHODS.findall(methods_raw)
        # Buscar nombre de función en la siguiente línea
        pos = m.end()
        rest = source[pos:]
        fn_match = re.search(r'def\s+(\w+)\s*\(', rest[:200])
        if fn_match:
            func_name = fn_match.group(1)
        else:
            continue
        endpoint = {
            "function": func_name,
            "line": source[:m.start()].count("\n") + 1,
            "methods": methods or ["GET"],
            "route": route_path,
            "auth_required": False,
        }
        target_bp = bp_vars.get(bp_var) or list(bp_vars.values())[0]
        target_bp["endpoints"].append(endpoint)
    return bp_vars


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera API_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""
    # Detectar framework
    framework = next(
        (FRAMEWORK_KEYS[k] for k in FRAMEWORK_KEYS if k in stack),
        None
    )

    # Detectar archivos de middleware
    middleware_files = [
        f.rel_path for f in files
        if f.role == "middleware" or any(
            kw in f.rel_path.lower()
            for kw in ("auth", "middleware", "decorator", "guard")
        )
    ]

    blueprints_result = []
    webhooks_result = []

    # Analizar archivos Python (Flask / FastAPI)
    py_files = [f for f in files if f.language == "python" and f.role in ("controller", "entry_point", "other")]
    # También revisar blueprints/ directamente
    for fi in files:
        if fi.language != "python":
            continue
        fpath = root / fi.rel_path
        bp_data = _analyze_flask_file(fpath, root)
        if not bp_data:
            continue

        for bp_var, bp_info in bp_data.items():
            if not bp_info["endpoints"]:
                continue

            normal_endpoints = []
            for ep in bp_info["endpoints"]:
                if _is_webhook(ep["route"], ep["function"]):
                    webhooks_result.append({
                        "file": bp_info["file"],
                        "function": ep["function"],
                        "line": ep["line"],
                        "route": ep["route"],
                        "methods": ep["methods"],
                    })
                else:
                    normal_endpoints.append(ep)

            if normal_endpoints:
                blueprints_result.append({
                    "name": bp_info["name"],
                    "file": bp_info["file"],
                    "prefix": bp_info["prefix"],
                    "endpoints": normal_endpoints,
                })

    result = {
        "framework": framework,
        "blueprints": blueprints_result,
        "webhooks": webhooks_result,
        "middleware_files": middleware_files[:10],
    }

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "API_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera API_MAP.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd()
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("API_MAP.json generado.")
```

- [ ] **Step 4: Ejecutar tests**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_analyzer_api.py -v
```
Esperado: todos PASS

- [ ] **Step 5: Verificar con el proyecto real**

```bash
python3 .claude/hooks/analyzers/api.py --root . 2>&1
python3 -c "import json; d=json.load(open('.claude/maps/API_MAP.json')); print('framework:', d['framework']); print('blueprints:', len(d['blueprints'])); print('webhooks:', len(d['webhooks']))"
```

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks/analyzers/api.py tests/test_analyzer_api.py .claude/maps/API_MAP.json
git commit -m "feat: analyzers/api.py — API_MAP.json with blueprints, endpoints, webhooks"
```

---

## Task 5: Crear `analyzers/services.py` — SERVICES_MAP.json

Nuevo analyzer: detecta integraciones externas por imports de SDKs y env vars.

**Files:**
- Crear: `.claude/hooks/analyzers/services.py`
- Crear: `.claude/maps/SERVICES_MAP.json` (vacío inicial)
- Crear: `tests/test_analyzer_services.py`

- [ ] **Step 1: Escribir tests**

Crear `tests/test_analyzer_services.py`:

```python
"""Tests para analyzers/services.py — genera SERVICES_MAP.json."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude" / "hooks"))

from analyzers import core
from analyzers.services import run


def _make_project_with_services(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\ntwilio==9.4.6\nredis==5.2.1\nsentry-sdk==2.54.0\n"
    )
    svc_dir = tmp_path / "services"
    svc_dir.mkdir()
    (svc_dir / "twilio_service.py").write_text(
        'import twilio\nTWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]\n'
        'def enviar_mensaje(to, body): pass\n'
        'def procesar_respuesta(data): pass\n'
    )
    (svc_dir / "cache_service.py").write_text(
        'import redis\nREDIS_URL = os.environ.get("REDIS_URL")\n'
        'def get_cache(key): pass\n'
        'def set_cache(key, value): pass\n'
    )
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_returns_required_keys(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert "integrations" in result


def test_detects_twilio(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    names = [i["name"] for i in result["integrations"]]
    assert "Twilio" in names


def test_integration_has_type(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    for integration in result["integrations"]:
        assert "type" in integration
        assert integration["type"] in (
            "sms", "email", "payments", "storage", "cache", "queue", "monitoring", "other"
        )


def test_integration_has_env_vars(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    twilio = next((i for i in result["integrations"] if i["name"] == "Twilio"), None)
    if twilio:
        assert "TWILIO_ACCOUNT_SID" in twilio.get("env_vars", [])


def test_empty_project_returns_empty_integrations(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run(tmp_path, files, stack)
    assert result == {"integrations": []}
```

- [ ] **Step 2: Ejecutar tests — deben fallar**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_analyzer_services.py -v 2>&1 | head -20
```

- [ ] **Step 3: Crear `analyzers/services.py`**

Crear `.claude/hooks/analyzers/services.py`:

```python
#!/usr/bin/env python3
"""
analyzers/services.py — Genera SERVICES_MAP.json.

Detecta integraciones externas por:
1. Imports de SDKs conocidos (twilio, stripe, boto3, etc.)
2. Patrones de env vars de credenciales (_KEY, _SECRET, _TOKEN, _URL)
3. Archivos en carpetas services/, adapters/, providers/
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from analyzers.core import FileInfo, detect_stack, walk_repo

# SDK → (nombre display, tipo)
SDK_MAP: dict[str, tuple[str, str]] = {
    "twilio":        ("Twilio", "sms"),
    "vonage":        ("Vonage", "sms"),
    "sinch":         ("Sinch", "sms"),
    "sendgrid":      ("SendGrid", "email"),
    "mailgun":       ("Mailgun", "email"),
    "boto3":         ("AWS SES/S3", "email"),   # puede ser email o storage
    "stripe":        ("Stripe", "payments"),
    "monei":         ("Monei", "payments"),
    "paypalrestsdk": ("PayPal", "payments"),
    "braintree":     ("Braintree", "payments"),
    "google.cloud.storage": ("GCS", "storage"),
    "azure.storage": ("Azure Storage", "storage"),
    "redis":         ("Redis", "cache"),
    "aioredis":      ("Redis (async)", "cache"),
    "memcache":      ("Memcached", "cache"),
    "celery":        ("Celery", "queue"),
    "rq":            ("RQ", "queue"),
    "dramatiq":      ("Dramatiq", "queue"),
    "sentry_sdk":    ("Sentry", "monitoring"),
    "datadog":       ("Datadog", "monitoring"),
    "newrelic":      ("New Relic", "monitoring"),
    "httpx":         ("httpx", "other"),
    "requests":      ("requests", "other"),
}

# Patrones de env vars de credenciales
RE_ENV_VAR = re.compile(
    r'(?:os\.environ|os\.getenv)\s*[\[\(]\s*["\']([A-Z][A-Z0-9_]+(?:_KEY|_SECRET|_TOKEN|_URL|_SID|_API|_PASSWORD|_PASS|_AUTH)["\'])',
)


def _detect_integrations(
    files: list[FileInfo], root: Path, stack: dict
) -> list[dict]:
    integrations: dict[str, dict] = {}

    for fi in files:
        # Solo archivos de servicios/adapters/providers
        is_service_file = any(
            seg in fi.rel_path.lower()
            for seg in ("service", "adapter", "provider", "integration", "client")
        )

        # Detectar por imports externos conocidos
        for imp in fi.imports_external:
            imp_lower = imp.lower().replace("-", "_")
            # Match exacto o prefix
            for sdk_key, (sdk_name, sdk_type) in SDK_MAP.items():
                if imp_lower == sdk_key or imp_lower.startswith(sdk_key + "."):
                    if sdk_name not in integrations:
                        integrations[sdk_name] = {
                            "name": sdk_name,
                            "type": sdk_type,
                            "files": [],
                            "functions": [],
                            "env_vars": [],
                        }
                    if fi.rel_path not in integrations[sdk_name]["files"]:
                        integrations[sdk_name]["files"].append(fi.rel_path)
                    integrations[sdk_name]["functions"].extend(
                        [fn for fn in fi.functions if not fn.startswith("_")][:5]
                    )

        # También detectar por stack (de requirements.txt)
        for stack_name in stack:
            for sdk_key, (sdk_name, sdk_type) in SDK_MAP.items():
                if stack_name.lower() == sdk_key.replace("_", "-") or stack_name == sdk_name:
                    if sdk_name not in integrations:
                        integrations[sdk_name] = {
                            "name": sdk_name, "type": sdk_type,
                            "files": [], "functions": [], "env_vars": [],
                        }

        # Detectar env vars de credenciales en el código fuente
        if is_service_file or any(k in fi.imports_external for k in SDK_MAP):
            try:
                source = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in RE_ENV_VAR.finditer(source):
                env_name = m.group(1).strip("\"'")
                # Asignar la env var a la integración más probable por prefijo
                assigned = False
                for sdk_name, int_data in integrations.items():
                    sdk_prefix = sdk_name.upper().replace(" ", "_").replace("(", "").replace(")", "")
                    if env_name.startswith(sdk_prefix[:4]):
                        if env_name not in int_data["env_vars"]:
                            int_data["env_vars"].append(env_name)
                        assigned = True
                        break
                if not assigned and integrations:
                    # Asignar al que tiene archivos en este mismo file
                    for sdk_name, int_data in integrations.items():
                        if fi.rel_path in int_data["files"]:
                            if env_name not in int_data["env_vars"]:
                                int_data["env_vars"].append(env_name)
                            break

    # Limpiar duplicados en functions
    for int_data in integrations.values():
        int_data["functions"] = list(dict.fromkeys(int_data["functions"]))[:8]

    return list(integrations.values())


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera SERVICES_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""
    integrations = _detect_integrations(files, root, stack)
    result = {"integrations": integrations}

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "SERVICES_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera SERVICES_MAP.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd()
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("SERVICES_MAP.json generado.")
```

- [ ] **Step 4: Ejecutar tests**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_analyzer_services.py -v
```
Esperado: todos PASS

- [ ] **Step 5: Verificar con el proyecto real**

```bash
python3 .claude/hooks/analyzers/services.py --root . 2>&1
python3 -c "import json; d=json.load(open('.claude/maps/SERVICES_MAP.json')); [print(i['name'], '-', i['type']) for i in d['integrations']]"
```

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks/analyzers/services.py tests/test_analyzer_services.py .claude/maps/SERVICES_MAP.json
git commit -m "feat: analyzers/services.py — SERVICES_MAP.json with external integrations detection"
```

---

## Task 6: Crear `analyzers/jobs.py` — JOBS_MAP.json

Nuevo analyzer: detecta schedulers, jobs y queues.

**Files:**
- Crear: `.claude/hooks/analyzers/jobs.py`
- Crear: `.claude/maps/JOBS_MAP.json` (vacío inicial)
- Crear: `tests/test_analyzer_jobs.py`

- [ ] **Step 1: Escribir tests**

Crear `tests/test_analyzer_jobs.py`:

```python
"""Tests para analyzers/jobs.py — genera JOBS_MAP.json."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude" / "hooks"))

from analyzers import core
from analyzers.jobs import run


def _make_project_with_celery(tmp_path):
    (tmp_path / "requirements.txt").write_text("celery==5.3.0\nredis==5.2.1\n")
    (tmp_path / "tasks.py").write_text(
        'from celery import Celery\n'
        'app = Celery("tasks")\n\n'
        '@app.task\n'
        'def enviar_notificacion(user_id):\n'
        '    """Envía notificación por email al usuario."""\n'
        '    pass\n\n'
        '@app.task(bind=True)\n'
        'def procesar_pago(self, pedido_id):\n'
        '    pass\n'
    )
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_returns_required_keys(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert "scheduler" in result
    assert "jobs" in result
    assert "queues" in result


def test_detects_celery_scheduler(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert result["scheduler"] == "celery"


def test_detects_celery_tasks(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    job_fns = [j["function"] for j in result["jobs"]]
    assert "enviar_notificacion" in job_fns or "procesar_pago" in job_fns


def test_empty_project_returns_null_scheduler(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run(tmp_path, files, stack)
    assert result == {"scheduler": None, "jobs": [], "queues": []}


def test_job_has_required_fields(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    for job in result["jobs"]:
        assert "file" in job
        assert "function" in job
        assert "trigger" in job
        assert "schedule" in job
        assert "description" in job
        assert job["trigger"] in ("manual", "cron", "interval", "event", "startup")
```

- [ ] **Step 2: Ejecutar tests — deben fallar**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_analyzer_jobs.py -v 2>&1 | head -20
```

- [ ] **Step 3: Crear `analyzers/jobs.py`**

Crear `.claude/hooks/analyzers/jobs.py`:

```python
#!/usr/bin/env python3
"""
analyzers/jobs.py — Genera JOBS_MAP.json.

Detecta scheduler (Celery, RQ, APScheduler, cron), jobs y queues.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from analyzers.core import FileInfo, FunctionInfo, detect_stack, walk_repo

SCHEDULER_KEYS = {
    "celery":       "celery",
    "Celery":       "celery",
    "rq":           "rq",
    "RQ":           "rq",
    "apscheduler":  "apscheduler",
    "APScheduler":  "apscheduler",
}

RE_CRON = re.compile(r'\d+\s+\d+\s+\*\s+\*\s+\*|\*/\d+|\bcron\b', re.IGNORECASE)
RE_INTERVAL = re.compile(r'every\s+\d+|interval\s*=|countdown\s*=', re.IGNORECASE)
RE_CELERY_TASK = re.compile(r'@\w+\.task|@shared_task|@app\.task')
RE_RQ_JOB = re.compile(r'@job\b|q\.enqueue\b')


def _detect_scheduler(files: list[FileInfo], stack: dict) -> str | None:
    for stack_name in stack:
        key = stack_name.lower()
        if "celery" in key:
            return "celery"
        if key == "rq":
            return "rq"
        if "apscheduler" in key:
            return "apscheduler"
    for fi in files:
        for imp in fi.imports_external:
            if imp.lower() == "celery":
                return "celery"
            if imp.lower() == "rq":
                return "rq"
            if imp.lower() == "apscheduler":
                return "apscheduler"
    return None


def _extract_celery_jobs(fi: FileInfo, root: Path) -> list[dict]:
    """Extrae tareas Celery de un archivo."""
    jobs = []
    try:
        source = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return jobs

    if not RE_CELERY_TASK.search(source):
        return jobs

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return jobs

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        is_task = False
        schedule_str = None
        trigger = "manual"

        for dec in node.decorator_list:
            try:
                dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else str(dec)
            except Exception:
                dec_str = ""
            if "task" in dec_str.lower() or "shared_task" in dec_str.lower():
                is_task = True
            if RE_CRON.search(dec_str):
                trigger = "cron"
                schedule_str = dec_str
            elif RE_INTERVAL.search(dec_str):
                trigger = "interval"
                schedule_str = dec_str

        if not is_task:
            continue

        # Docstring como descripción
        desc = ""
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)):
            desc = str(node.body[0].value.value).strip().split(".")[0][:100]

        jobs.append({
            "file": fi.rel_path,
            "function": node.name,
            "trigger": trigger,
            "schedule": schedule_str,
            "description": desc,
        })

    return jobs


def _extract_manual_jobs(fi: FileInfo, root: Path) -> list[dict]:
    """Scripts manuales en scripts/ o con 'main' que parecen jobs."""
    if "script" not in fi.rel_path.lower() and "job" not in fi.rel_path.lower():
        return []
    if "main" not in fi.functions and "run" not in fi.functions:
        return []

    fn_name = "main" if "main" in fi.functions else "run"
    desc = fi.docstring[:100] if fi.docstring else f"Script manual en {fi.rel_path}"

    return [{
        "file": fi.rel_path,
        "function": fn_name,
        "trigger": "manual",
        "schedule": None,
        "description": desc,
    }]


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera JOBS_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""
    scheduler = _detect_scheduler(files, stack)

    jobs: list[dict] = []
    queues: list[str] = []

    if scheduler == "celery":
        for fi in files:
            jobs.extend(_extract_celery_jobs(fi, root))

    # Scripts manuales en todos los casos
    for fi in files:
        if fi.language == "python":
            jobs.extend(_extract_manual_jobs(fi, root))

    # Deduplicar por (file, function)
    seen = set()
    unique_jobs = []
    for j in jobs:
        key = (j["file"], j["function"])
        if key not in seen:
            seen.add(key)
            unique_jobs.append(j)

    result: dict = {
        "scheduler": scheduler,
        "jobs": unique_jobs,
        "queues": queues,
    }

    if not scheduler and not unique_jobs:
        result = {"scheduler": None, "jobs": [], "queues": []}

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "JOBS_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera JOBS_MAP.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd()
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("JOBS_MAP.json generado.")
```

- [ ] **Step 4: Ejecutar tests**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_analyzer_jobs.py -v
```
Esperado: todos PASS

- [ ] **Step 5: Verificar con el proyecto real**

```bash
python3 .claude/hooks/analyzers/jobs.py --root . 2>&1
python3 -c "import json; d=json.load(open('.claude/maps/JOBS_MAP.json')); print(d)"
```

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks/analyzers/jobs.py tests/test_analyzer_jobs.py .claude/maps/JOBS_MAP.json
git commit -m "feat: analyzers/jobs.py — JOBS_MAP.json with scheduler, jobs, queues detection"
```

---

## Task 7: Refactorizar `analyze-repo.py` como thin orchestrator

Reemplazar el contenido del monolito por un orquestador delgado que importa de `analyzers/`.

**Files:**
- Modificar: `.claude/hooks/analyze-repo.py`

- [ ] **Step 1: Verificar que todos los analyzers pasan sus tests**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/test_core.py tests/test_analyzer_project.py tests/test_analyzers_existing.py tests/test_analyzer_api.py tests/test_analyzer_services.py tests/test_analyzer_jobs.py -v
```
Esperado: todos PASS antes de tocar el orquestador

- [ ] **Step 2: Reemplazar `analyze-repo.py` con el orquestador**

Reemplazar TODO el contenido de `.claude/hooks/analyze-repo.py` con:

```python
#!/usr/bin/env python3
"""
analyze-repo.py — Orquestador que genera los MAP.json del plugin.

Llama core.walk_repo() UNA SOLA VEZ y delega en cada analyzer.

Uso:
    python3 .claude/hooks/analyze-repo.py [--root DIR] [--maps project,db,query,ui,api,services,jobs] [--force]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
HOOKS_DIR  = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

APPROVAL_PATH = PLUGIN_DIR / "runtime" / "map-scan-approval.json"
MAPS_DIR = PLUGIN_DIR / "maps"

# Importaciones de analyzers (después de sys.path)
from analyzers import core
from analyzers.project  import run as run_project
from analyzers.db       import run as run_db
from analyzers.query    import run as run_query
from analyzers.ui       import run as run_ui
from analyzers.api      import run as run_api
from analyzers.services import run as run_services
from analyzers.jobs     import run as run_jobs

ANALYZER_MAP = {
    "project":  run_project,
    "db":       run_db,
    "query":    run_query,
    "ui":       run_ui,
    "api":      run_api,
    "services": run_services,
    "jobs":     run_jobs,
}


def check_approval(force: bool) -> None:
    if force:
        return
    if not APPROVAL_PATH.exists():
        raise SystemExit(
            "Aprobación requerida. Ejecuta:\n"
            "  python3 .claude/hooks/approve-map-scan.py approve --by 'nombre'"
        )
    data = json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))
    if data.get("status") != "approved":
        raise SystemExit(
            f"Estado de aprobación: {data.get('status', 'desconocido')}. "
            "Ejecuta approve-map-scan.py approve primero."
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Genera MAP.json para el plugin de Claude.")
    p.add_argument("--root", default=None,
                   help="Raíz del repositorio a analizar (default: directorio que contiene .claude/)")
    p.add_argument("--maps", default="project,db,query,ui,api,services,jobs",
                   help="MAPs a generar, coma-separados.")
    p.add_argument("--force", action="store_true",
                   help="Omitir verificación de aprobación")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    check_approval(args.force)

    if args.root:
        root = Path(args.root).resolve()
    else:
        # Busca .claude/ subiendo desde cwd
        cwd = Path.cwd()
        for candidate in [cwd, *cwd.parents]:
            if (candidate / ".claude").exists():
                root = candidate
                break
        else:
            root = PLUGIN_DIR.parent

    maps_to_gen = {m.strip().lower() for m in args.maps.split(",")}
    invalid = maps_to_gen - set(ANALYZER_MAP.keys())
    if invalid:
        print(f"MAPs desconocidos: {', '.join(sorted(invalid))}")
        print(f"Opciones válidas: {', '.join(sorted(ANALYZER_MAP.keys()))}")
        return 1

    print(f"Analizando repositorio: {root}")

    print("  Detectando stack...")
    stack = core.detect_stack(root)

    print("  Escaneando archivos...")
    files = core.walk_repo(root)

    print(f"  Archivos fuente: {len(files)}")
    print(f"  Stack: {len(stack)} paquetes relevantes")

    MAPS_DIR.mkdir(parents=True, exist_ok=True)

    for map_name in ["project", "db", "query", "ui", "api", "services", "jobs"]:
        if map_name not in maps_to_gen:
            continue
        print(f"  Generando {map_name.upper()}_MAP.json...")
        ANALYZER_MAP[map_name](root, files, stack)
        print(f"  ✓ {map_name.upper()}_MAP.json")

    # Reset aprobación
    if not args.force and APPROVAL_PATH.exists():
        approval = json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))
        approval["status"] = "pending"
        approval["approved_by"] = ""
        APPROVAL_PATH.write_text(
            json.dumps(approval, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("  Aprobación reseteada.")

    print(f"\n  {len(maps_to_gen)} MAP(s) generados correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Verificar que el orquestador funciona**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 .claude/hooks/analyze-repo.py --force --maps project,db,api 2>&1
```
Esperado: genera 3 MAPs sin errores

- [ ] **Step 4: Verificar todos los 7 MAPs**

```bash
python3 .claude/hooks/analyze-repo.py --force 2>&1
ls -la .claude/maps/*.json
```
Esperado: 7 archivos MAP en `.claude/maps/`

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/analyze-repo.py
git commit -m "refactor: analyze-repo.py as thin orchestrator — delegates to analyzers/"
```

---

## Task 8: Añadir schemas JSON para los 3 nuevos MAPs y actualizar project-map.json

**Files:**
- Crear: `.claude/schemas/api-map.json`
- Crear: `.claude/schemas/services-map.json`
- Crear: `.claude/schemas/jobs-map.json`
- Modificar: `.claude/schemas/project-map.json`

- [ ] **Step 1: Crear `schemas/api-map.json`**

Crear `.claude/schemas/api-map.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "APIMap",
  "description": "Mapa de endpoints HTTP, blueprints y webhooks generado por analyzers/api.py.",
  "type": "object",
  "required": ["framework", "blueprints", "webhooks", "middleware_files"],
  "additionalProperties": false,
  "properties": {
    "framework": { "type": ["string", "null"] },
    "blueprints": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "file", "prefix", "endpoints"],
        "additionalProperties": false,
        "properties": {
          "name":   { "type": "string" },
          "file":   { "type": "string" },
          "prefix": { "type": "string" },
          "endpoints": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["function", "line", "methods", "route", "auth_required"],
              "additionalProperties": false,
              "properties": {
                "function":     { "type": "string" },
                "line":         { "type": "integer" },
                "methods":      { "type": "array", "items": { "type": "string" } },
                "route":        { "type": "string" },
                "auth_required": { "type": "boolean" }
              }
            }
          }
        }
      }
    },
    "webhooks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["file", "function", "line", "route", "methods"],
        "additionalProperties": false,
        "properties": {
          "file":     { "type": "string" },
          "function": { "type": "string" },
          "line":     { "type": "integer" },
          "route":    { "type": "string" },
          "methods":  { "type": "array", "items": { "type": "string" } }
        }
      }
    },
    "middleware_files": { "type": "array", "items": { "type": "string" } }
  }
}
```

- [ ] **Step 2: Crear `schemas/services-map.json`**

Crear `.claude/schemas/services-map.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ServicesMap",
  "description": "Mapa de integraciones externas generado por analyzers/services.py.",
  "type": "object",
  "required": ["integrations"],
  "additionalProperties": false,
  "properties": {
    "integrations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "type", "files", "functions", "env_vars"],
        "additionalProperties": false,
        "properties": {
          "name":      { "type": "string" },
          "type":      { "type": "string", "enum": ["sms", "email", "payments", "storage", "cache", "queue", "monitoring", "other"] },
          "files":     { "type": "array", "items": { "type": "string" } },
          "functions": { "type": "array", "items": { "type": "string" } },
          "env_vars":  { "type": "array", "items": { "type": "string" } }
        }
      }
    }
  }
}
```

- [ ] **Step 3: Crear `schemas/jobs-map.json`**

Crear `.claude/schemas/jobs-map.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "JobsMap",
  "description": "Mapa de tareas programadas y queues generado por analyzers/jobs.py.",
  "type": "object",
  "required": ["scheduler", "jobs", "queues"],
  "additionalProperties": false,
  "properties": {
    "scheduler": { "type": ["string", "null"], "enum": ["celery", "rq", "apscheduler", "cron", null] },
    "jobs": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["file", "function", "trigger", "schedule", "description"],
        "additionalProperties": false,
        "properties": {
          "file":        { "type": "string" },
          "function":    { "type": "string" },
          "trigger":     { "type": "string", "enum": ["manual", "cron", "interval", "event", "startup"] },
          "schedule":    { "type": ["string", "null"] },
          "description": { "type": "string" }
        }
      }
    },
    "queues": { "type": "array", "items": { "type": "string" } }
  }
}
```

- [ ] **Step 4: Actualizar `schemas/project-map.json`**

Reemplazar el contenido de `.claude/schemas/project-map.json` con el nuevo schema que usa `domains` en lugar de `modules`/`structure`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ProjectMap",
  "description": "Routing index generado por analyzers/project.py. Consumido por reader.md para activar sub-readers.",
  "type": "object",
  "additionalProperties": false,
  "required": ["name", "architecture", "stack", "entry_points", "domains"],
  "properties": {
    "name":         { "type": "string" },
    "description":  { "type": "string" },
    "languages":    { "type": "array", "items": { "type": "string" } },
    "stack": {
      "type": "object",
      "additionalProperties": { "type": "string" }
    },
    "architecture": {
      "type": "string",
      "description": "Cadena de capas. Ej: BLUEPRINTS → CONTROLLERS → MANAGERS → [DB | Redis]"
    },
    "entry_points": { "type": "array", "items": { "type": "string" } },
    "domains": {
      "type": "object",
      "description": "Dominios disponibles. El reader hace match de trigger_keywords contra el prompt para decidir qué sub-readers activar.",
      "additionalProperties": {
        "type": "object",
        "required": ["map", "reader", "summary", "trigger_keywords"],
        "additionalProperties": false,
        "properties": {
          "map":              { "type": "string", "description": "Nombre del archivo MAP (ej: DB_MAP.json)" },
          "reader":           { "type": "string", "description": "Nombre del reader agent (ej: db-reader)" },
          "summary":          { "type": "string", "description": "Descripción breve del contenido del MAP" },
          "trigger_keywords": { "type": "array", "items": { "type": "string" }, "minItems": 1 }
        }
      }
    },
    "hotspots": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["file", "commits"],
        "properties": {
          "file":    { "type": "string" },
          "commits": { "type": "integer" }
        }
      }
    },
    "cochange": {
      "type": "object",
      "additionalProperties": { "type": "array", "items": { "type": "string" } }
    }
  }
}
```

- [ ] **Step 5: Verificar que el schema valida el PROJECT_MAP.json generado**

```bash
python3 -c "
import json
from pathlib import Path
import sys
sys.path.insert(0, '.claude/hooks')
from validate import validate_artifact
data = json.loads(Path('.claude/maps/PROJECT_MAP.json').read_text())
result = validate_artifact('PROJECT_MAP.json', data)
print('OK' if result.ok else result.format())
"
```
Esperado: `OK`

- [ ] **Step 6: Commit**

```bash
git add .claude/schemas/api-map.json .claude/schemas/services-map.json .claude/schemas/jobs-map.json .claude/schemas/project-map.json
git commit -m "feat: JSON schemas for API_MAP, SERVICES_MAP, JOBS_MAP — update project-map.json schema to domains"
```

---

## Task 9: Actualizar `reader.md` — routing dinámico desde `domains`

Reemplazar los pasos 2, 3, 4, 5 con la nueva lógica de routing dinámico.

**Files:**
- Modificar: `.claude/agents/readers/reader.md`

- [ ] **Step 1: Leer el archivo actual para entender líneas exactas**

Leer `.claude/agents/readers/reader.md` (ya conocemos líneas 72-143 del paso 2 al 5).

- [ ] **Step 2: Reemplazar Paso 2 (líneas 72-88)**

Reemplazar desde `### Paso 2 — Leer PROJECT_MAP.json (siempre obligatorio)` hasta el final del bloque de Paso 2 (antes de `### Paso 3`), con:

```markdown
### Paso 2 — Leer PROJECT_MAP.json (siempre obligatorio)

Lee `.claude/maps/PROJECT_MAP.json`.

El MAP es **válido** si `domains` existe y tiene al menos una clave. Si el archivo no existe, `domains` está ausente, o `domains` es `{}`, detente y devuelve JSON con `status: "blocked_no_maps"` y `map_scan_requested: true`.

Si el MAP es válido, extrae:
- `tech_stack` desde `project_map.stack`
- `architecture` desde `project_map.architecture`
- `entry_points` desde `project_map.entry_points`
- `domains` completo — lo usarás en el paso 4 para routing
```

- [ ] **Step 3: Reemplazar Paso 3 (construcción de context_summary)**

Reemplazar el bloque `### Paso 3 — Construir context_summary` completo con:

```markdown
### Paso 3 — Construir context_summary

Con `improved_prompt` y los datos de `PROJECT_MAP.json`, construye `context_summary`: párrafo conciso (3-6 líneas) que describe:

- tipo de proyecto, propósito y stack principal (desde `description` + `stack`)
- capa o flujo arquitectónico general (desde `architecture`)
- dominios activos en el proyecto (desde las claves de `domains`)
- cualquier restricción arquitectónica importante que pueda inferirse del stack
```

- [ ] **Step 4: Reemplazar Paso 4 (routing)**

Reemplazar el bloque `### Paso 4 — Decidir MAPs adicionales` completo con:

```markdown
### Paso 4 — Decidir MAPs adicionales (routing dinámico)

Para cada dominio en `PROJECT_MAP.domains`, extrae sus `trigger_keywords`. Haz match **case-insensitive** (substring match) contra los tokens del `improved_prompt`. Si al menos **1 keyword** de un dominio tiene coincidencia, incluye ese dominio en `selected_readers`.

Si ningún dominio hace match, activa solo `project-reader` como fallback.

Para cada dominio seleccionado, lee el archivo indicado en `domains[nombre].map`. Si el archivo existe y no está vacío en sus arrays principales, úsalo. Si está vacío o no existe, continúa sin él.

**Nunca explores el repositorio directamente como sustituto de los MAPs.**
```

- [ ] **Step 5: Actualizar Paso 5 — filtrado para nuevos MAPs**

En el Paso 5, añadir al final del bloque de filtros existentes:

```markdown
**Para API_MAP.json:**
- Conserva en `blueprints` solo los que tienen endpoints cuya `route` o `function` coincide con los conceptos de la petición.
- Conserva siempre: `framework`, `middleware_files`.
- Incluye `webhooks` solo si la petición menciona webhooks o integraciones entrantes.

**Para SERVICES_MAP.json:**
- Conserva en `integrations` solo las que coinciden con el servicio o `type` mencionado en la petición.

**Para JOBS_MAP.json:**
- Conserva en `jobs` solo los que coinciden con la función o trigger mencionado.
- Conserva siempre: `scheduler`.
```

- [ ] **Step 6: Actualizar "Reglas de enrutado"**

En la sección `## Reglas de enrutado`, añadir las 3 nuevas líneas:

```markdown
- `api-reader`      → endpoints HTTP, rutas, blueprints, webhooks, contratos de API
- `services-reader` → integraciones externas, SDKs de terceros, env vars de credenciales
- `jobs-reader`     → tareas programadas, queues, workers, crons
```

- [ ] **Step 7: Commit**

```bash
git add .claude/agents/readers/reader.md
git commit -m "feat: reader.md — dynamic routing from domains.trigger_keywords, update pasos 2/3/4/5"
```

---

## Task 10: Crear los 3 nuevos reader agents

**Files:**
- Crear: `.claude/agents/readers/api-reader.md`
- Crear: `.claude/agents/readers/services-reader.md`
- Crear: `.claude/agents/readers/jobs-reader.md`

- [ ] **Step 1: Crear `api-reader.md`**

Crear `.claude/agents/readers/api-reader.md`:

```markdown
---
model: claude-haiku-4-5-20251001
---

# API Reader

Eres el subagente que interpreta el mapa de API HTTP del proyecto.

## Objetivo

Usar `API_MAP.json` para identificar qué endpoints, blueprints, rutas y middleware son relevantes cuando la petición afecta la capa HTTP: añadir/modificar endpoints, cambiar autenticación, modificar rutas, webhooks.

## Fuente principal

`.claude/maps/API_MAP.json` — ya leído y pasado por `reader` como objeto JSON filtrado.

## Entradas

- `improved_prompt` — la petición refinada por `reader`
- `context_summary` — resumen del proyecto
- el contenido de `API_MAP.json` como objeto JSON

## Cómo analizar API_MAP.json

- `framework` — framework HTTP (Flask, FastAPI, Express). Determina patrones de decoradores y routing.
- `blueprints[]` — cada blueprint tiene `name`, `file`, `prefix` y `endpoints[]`. Filtra los blueprints cuyos endpoints coincidan con la petición (por `route` o `function`).
- `endpoints[].auth_required` — determina si el endpoint requiere autenticación. Relevante para peticiones de seguridad.
- `webhooks[]` — endpoints especiales con ruta `/webhook` o `/callback`. Relevante para integraciones entrantes.
- `middleware_files[]` — archivos de middleware y auth. Incluye siempre si la petición toca autenticación.

## Reglas de selección

- `files_to_open`: archivos de blueprints que contienen los endpoints directamente afectados
- `files_to_review`: middleware de auth si la petición toca permisos; otros blueprints si comparten lógica

## Salida

Devuelve JSON parcial con:

```json
{
  "files_to_open": [
    {
      "path": "blueprints/pedidos.py",
      "hint": "Blueprint de pedidos — contiene el endpoint POST /api/pedidos/ que la petición modifica",
      "key_symbols": ["crear_pedido", "pedidos_bp"],
      "estimated_relevance": "high"
    }
  ],
  "files_to_review": [
    {
      "path": "utils/auth.py",
      "hint": "Decorador @login_required — afecta si el nuevo endpoint requiere autenticación",
      "key_symbols": ["login_required"],
      "estimated_relevance": "medium"
    }
  ]
}
```
```

- [ ] **Step 2: Crear `services-reader.md`**

Crear `.claude/agents/readers/services-reader.md`:

```markdown
---
model: claude-haiku-4-5-20251001
---

# Services Reader

Eres el subagente que interpreta el mapa de integraciones externas del proyecto.

## Objetivo

Usar `SERVICES_MAP.json` para identificar qué servicios externos, SDKs y archivos de integración son relevantes cuando la petición toca integraciones de terceros: Twilio, pagos, email, Redis, etc.

## Fuente principal

`.claude/maps/SERVICES_MAP.json` — ya leído y pasado por `reader` como objeto JSON filtrado.

## Entradas

- `improved_prompt` — la petición refinada por `reader`
- `context_summary` — resumen del proyecto
- el contenido de `SERVICES_MAP.json` como objeto JSON

## Cómo analizar SERVICES_MAP.json

- `integrations[]` — cada integración tiene `name`, `type`, `files`, `functions` y `env_vars`.
- Filtra las integraciones cuyo `name` o `type` coincide con lo mencionado en la petición.
- `env_vars` — variables de entorno necesarias. Menciónalas en el hint si la petición toca configuración.
- `files[]` — archivos que implementan la integración. Son los candidatos principales a `files_to_open`.

## Reglas de selección

- `files_to_open`: archivos de la integración directamente afectada
- `files_to_review`: archivos de otras integraciones que comparten env vars o patrones similares

## Salida

```json
{
  "files_to_open": [
    {
      "path": "services/twilio_service.py",
      "hint": "Integración Twilio SMS — contiene enviar_mensaje() que la petición modifica",
      "key_symbols": ["enviar_mensaje", "procesar_respuesta"],
      "estimated_relevance": "high"
    }
  ],
  "files_to_review": []
}
```
```

- [ ] **Step 3: Crear `jobs-reader.md`**

Crear `.claude/agents/readers/jobs-reader.md`:

```markdown
---
model: claude-haiku-4-5-20251001
---

# Jobs Reader

Eres el subagente que interpreta el mapa de tareas programadas y queues del proyecto.

## Objetivo

Usar `JOBS_MAP.json` para identificar qué jobs, schedulers y colas son relevantes cuando la petición toca tareas asíncronas, crons, workers o procesos en background.

## Fuente principal

`.claude/maps/JOBS_MAP.json` — ya leído y pasado por `reader` como objeto JSON filtrado.

## Entradas

- `improved_prompt` — la petición refinada por `reader`
- `context_summary` — resumen del proyecto
- el contenido de `JOBS_MAP.json` como objeto JSON

## Cómo analizar JOBS_MAP.json

- `scheduler` — tipo de scheduler usado (`celery`, `rq`, `apscheduler`, `cron`, o null).
- `jobs[]` — cada job tiene `file`, `function`, `trigger`, `schedule` y `description`.
- Filtra los jobs cuya `function` o `description` coincida con la petición.
- `trigger` — indica si es manual, cron, interval, event o startup. Relevante para peticiones de scheduling.
- `queues[]` — nombres de queues disponibles.

## Reglas de selección

- `files_to_open`: archivo del job directamente afectado
- `files_to_review`: archivo de configuración del scheduler si la petición cambia el schedule

## Salida

```json
{
  "files_to_open": [
    {
      "path": "tasks.py",
      "hint": "Tarea Celery enviar_notificacion — la petición modifica su lógica de envío",
      "key_symbols": ["enviar_notificacion"],
      "estimated_relevance": "high"
    }
  ],
  "files_to_review": []
}
```
```

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/readers/api-reader.md .claude/agents/readers/services-reader.md .claude/agents/readers/jobs-reader.md
git commit -m "feat: api-reader.md, services-reader.md, jobs-reader.md — new domain reader agents"
```

---

## Task 11: Actualizar `pre-commit.py` y crear MAPs vacíos iniciales

**Files:**
- Modificar: `.claude/hooks/pre-commit.py`
- Crear: `.claude/maps/API_MAP.json`, `SERVICES_MAP.json`, `JOBS_MAP.json` (si no existen ya)

- [ ] **Step 1: Actualizar `REQUIRED_PATHS` en `pre-commit.py`**

En `.claude/hooks/pre-commit.py`, en el bloque `REQUIRED_PATHS` (líneas 18-55), añadir al final antes del `]`:

```python
    PLUGIN_DIR / "maps" / "API_MAP.json",
    PLUGIN_DIR / "maps" / "SERVICES_MAP.json",
    PLUGIN_DIR / "maps" / "JOBS_MAP.json",
    PLUGIN_DIR / "agents" / "readers" / "api-reader.md",
    PLUGIN_DIR / "agents" / "readers" / "services-reader.md",
    PLUGIN_DIR / "agents" / "readers" / "jobs-reader.md",
    PLUGIN_DIR / "schemas" / "api-map.json",
    PLUGIN_DIR / "schemas" / "services-map.json",
    PLUGIN_DIR / "schemas" / "jobs-map.json",
```

- [ ] **Step 2: Actualizar `JSON_FILES` en `pre-commit.py`**

En el bloque `JSON_FILES` (líneas 66-86), añadir antes del `]`:

```python
    PLUGIN_DIR / "schemas" / "api-map.json",
    PLUGIN_DIR / "schemas" / "services-map.json",
    PLUGIN_DIR / "schemas" / "jobs-map.json",
    PLUGIN_DIR / "maps" / "API_MAP.json",
    PLUGIN_DIR / "maps" / "SERVICES_MAP.json",
    PLUGIN_DIR / "maps" / "JOBS_MAP.json",
```

- [ ] **Step 3: Actualizar `MAP_ARTIFACTS` en `pre-commit.py`**

En el bloque `MAP_ARTIFACTS` (líneas 116-121), añadir las 3 nuevas entradas:

```python
    MAP_ARTIFACTS = {
        "PROJECT_MAP.json": PLUGIN_DIR / "maps" / "PROJECT_MAP.json",
        "DB_MAP.json":      PLUGIN_DIR / "maps" / "DB_MAP.json",
        "QUERY_MAP.json":   PLUGIN_DIR / "maps" / "QUERY_MAP.json",
        "UI_MAP.json":      PLUGIN_DIR / "maps" / "UI_MAP.json",
        "API_MAP.json":     PLUGIN_DIR / "maps" / "API_MAP.json",
        "SERVICES_MAP.json": PLUGIN_DIR / "maps" / "SERVICES_MAP.json",
        "JOBS_MAP.json":    PLUGIN_DIR / "maps" / "JOBS_MAP.json",
    }
```

- [ ] **Step 4: Verificar que los MAPs vacíos existen y son válidos**

```bash
python3 -c "import json; print(json.loads(open('.claude/maps/API_MAP.json').read()))"
python3 -c "import json; print(json.loads(open('.claude/maps/SERVICES_MAP.json').read()))"
python3 -c "import json; print(json.loads(open('.claude/maps/JOBS_MAP.json').read()))"
```
Si alguno no existe, crearlo con su estructura mínima válida:
- `API_MAP.json`: `{"framework": null, "blueprints": [], "webhooks": [], "middleware_files": []}`
- `SERVICES_MAP.json`: `{"integrations": []}`
- `JOBS_MAP.json`: `{"scheduler": null, "jobs": [], "queues": []}`

- [ ] **Step 5: Correr `pre-commit.py` — debe pasar**

```bash
python3 .claude/hooks/pre-commit.py
```
Esperado: sin errores, exit code 0

- [ ] **Step 6: Correr todos los tests**

```bash
cd /home/siemprearmando/agentes/losgretis && python3 -m pytest tests/ -v
```
Esperado: todos PASS

- [ ] **Step 7: Commit final**

```bash
git add .claude/hooks/pre-commit.py .claude/maps/API_MAP.json .claude/maps/SERVICES_MAP.json .claude/maps/JOBS_MAP.json
git commit -m "feat: update pre-commit.py for 3 new MAPs + schemas + reader agents"
```

---

## Task 12: Verificación end-to-end

Verificar que el sistema completo funciona: analyze-repo genera los 7 MAPs, pre-commit pasa, PROJECT_MAP.json tiene el formato correcto.

**Files:** ninguno nuevo

- [ ] **Step 1: Generar todos los MAPs frescos**

```bash
python3 .claude/hooks/approve-map-scan.py approve --by "test"
python3 .claude/hooks/analyze-repo.py
```
Esperado: 7 MAPs generados, "Aprobación reseteada."

- [ ] **Step 2: Verificar estructura de PROJECT_MAP.json**

```bash
python3 -c "
import json
d = json.loads(open('.claude/maps/PROJECT_MAP.json').read())
assert 'domains' in d, 'Falta domains'
assert 'modules' not in d, 'No debe tener modules'
assert len(d['domains']) == 6, f'Esperados 6 dominios, hay {len(d[\"domains\"])}'
for name, info in d['domains'].items():
    assert 'trigger_keywords' in info, f'{name} sin trigger_keywords'
    assert len(info['trigger_keywords']) > 0
print('PROJECT_MAP.json OK')
print('Dominios:', list(d['domains'].keys()))
"
```

- [ ] **Step 3: Verificar pre-commit completo**

```bash
python3 .claude/hooks/pre-commit.py
```
Esperado: exit 0 sin errores

- [ ] **Step 4: Verificar standalone de cada analyzer**

```bash
python3 .claude/hooks/analyzers/project.py --root .
python3 .claude/hooks/analyzers/api.py --root .
python3 .claude/hooks/analyzers/services.py --root .
python3 .claude/hooks/analyzers/jobs.py --root .
```
Esperado: cada uno imprime mensaje de éxito sin errores

- [ ] **Step 5: Correr suite completa de tests**

```bash
python3 -m pytest tests/ -v --tb=short
```
Esperado: todos PASS

- [ ] **Step 6: Commit final**

```bash
git add -A
git status  # verificar que no hay nada inesperado
git commit -m "chore: end-to-end verification — all 7 MAPs, pre-commit passing, standalone analyzers working"
```
