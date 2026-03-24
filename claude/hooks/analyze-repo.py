#!/usr/bin/env python3
"""
analyze-repo.py — Genera los MAP.md del plugin a partir del código fuente.

Combina 5 fuentes de información:
  1. Manifests (requirements.txt, package.json, pyproject.toml…) → stack exacto con versiones
  2. AST Python (módulo ast)                                      → clases, funciones, imports
  3. Regex JS/TS                                                  → exports, imports, JSDoc
  4. Naming heuristics                                            → rol de cada archivo/carpeta
  5. Git history                                                  → co-change y hotspots

Salida: .claude/maps/PROJECT_MAP.md  DB_MAP.md  QUERY_MAP.md  UI_MAP.md

Uso:
    python3 .claude/hooks/analyze-repo.py [--root DIR] [--maps project,db,query,ui] [--force]

    --root   Raíz del repositorio a analizar. Default: directorio que contiene .claude/
    --maps   Coma-separado. Default: project,db,query,ui
    --force  Omite verificación de aprobación (solo para testing)
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ─── Rutas ────────────────────────────────────────────────────────────────────

PLUGIN_DIR = Path(__file__).resolve().parents[1]
MAPS_DIR   = PLUGIN_DIR / "maps"
APPROVAL_PATH = PLUGIN_DIR / "runtime" / "map-scan-approval.json"

# ─── Constantes de clasificación ──────────────────────────────────────────────

IGNORE_DIRS: set[str] = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "htmlcov", ".tox", ".eggs",
    "site-packages", ".idea", ".vscode",
}

IGNORE_EXTS: set[str] = {
    ".pyc", ".pyo", ".lock", ".sum", ".map",
    ".min.js", ".min.css", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".pdf",
}

SOURCE_EXTS: dict[str, str] = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".rb": "ruby", ".go": "go", ".java": "java", ".php": "php",
    ".rs": "rust", ".cs": "csharp",
    ".html": "html", ".jinja2": "jinja2", ".jinja": "jinja2",
    ".hbs": "handlebars", ".ejs": "ejs", ".njk": "nunjucks",
    ".vue": "vue", ".svelte": "svelte", ".sql": "sql",
}

# Patrones de rol por nombre de archivo (orden importa: primero más específico)
ROLE_PATTERNS: list[tuple[str, str]] = [
    (r"(main|app|server|index|wsgi|asgi)\.(py|ts|js|mjs)$",   "entry_point"),
    (r"state[s]?\.(py|ts|js)$",                               "state_machine"),
    (r"(blueprint|router|route)\w*\.(py|ts|js)$",             "controller"),
    (r"\w*(blueprint|router|route)\w*\.(py|ts|js)$",          "controller"),
    (r"(controller|view|handler)\w*\.(py|ts|js)$",            "controller"),
    (r"\w*(controller|handler)\w*\.(py|ts|js)$",              "controller"),
    (r"(service|adapter|client|provider)\w*\.(py|ts|js)$",    "service"),
    (r"\w*(service|adapter|client|provider)\w*\.(py|ts|js)$", "service"),
    (r"(manager|gestor|repository|repo|dao|store)\w*\.(py|ts|js)$", "data_access"),
    (r"\w*(manager|gestor|repository|repo|dao)\w*\.(py|ts|js)$",    "data_access"),
    (r"models?\.(py|ts|js)$",                                 "model"),
    (r"(entity|entities|domain)\w*\.(py|ts|js)$",             "model"),
    (r"\w*\.(entity|model)\.(py|ts|js)$",                     "model"),
    (r"(schema|schemas)\.(py|ts|js)$",                        "schema"),
    (r"(config|settings|configuration)\w*\.(py|ts|js)$",      "config"),
    (r"database?\.(py|ts|js)$",                               "db_connection"),
    (r"(middleware|guard|interceptor)\w*\.(py|ts|js)$",       "middleware"),
    (r"(util|helper|tool|lib|common)\w*\.(py|ts|js)$",        "utility"),
    (r"\w*(util|helper|lib)\w*\.(py|ts|js)$",                 "utility"),
    (r"(test|spec)\w*\.(py|ts|js)$",                          "test"),
    (r"\w*(test|spec)\w*\.(py|ts|js)$",                       "test"),
    (r"(migration|migrate|seed)\w*\.(py|ts|js|sql)$",         "migration"),
    (r"\w*\.(html|jinja2|jinja|hbs|ejs|njk|pug)$",            "template"),
    (r"\w*\.(vue|svelte)$",                                    "component"),
    (r"\w*\.(jsx|tsx)$",                                       "component"),
    (r"\w*\.component\.(ts|js)$",                             "component"),
]

FOLDER_ROLES: dict[str, str] = {
    "blueprints": "routing HTTP",
    "routes": "routing HTTP",
    "routers": "routing HTTP",
    "api": "API endpoints",
    "endpoints": "API endpoints",
    "controllers": "lógica de negocio",
    "handlers": "lógica de negocio",
    "managers": "acceso a datos (DB + caché)",
    "repositories": "acceso a datos",
    "services": "adaptadores externos / lógica de servicio",
    "adapters": "adaptadores externos",
    "providers": "proveedores de servicio",
    "models": "modelos ORM / entidades",
    "entities": "modelos ORM / entidades",
    "domain": "dominio del negocio",
    "schemas": "validación de entrada",
    "middlewares": "middlewares",
    "middleware": "middlewares",
    "utils": "helpers sin estado",
    "helpers": "helpers sin estado",
    "lib": "utilidades compartidas",
    "common": "código compartido",
    "shared": "código compartido",
    "templates": "plantillas HTML",
    "views": "vistas / plantillas",
    "components": "componentes UI",
    "pages": "páginas / rutas UI",
    "layouts": "layouts UI",
    "static": "assets estáticos",
    "public": "assets públicos",
    "assets": "assets",
    "tests": "tests", "test": "tests", "__tests__": "tests", "spec": "tests",
    "migrations": "migraciones DB",
    "seeds": "datos iniciales DB",
    "config": "configuración",
    "docs": "documentación",
    "scripts": "scripts de utilidad",
    "hooks": "hooks del sistema",
    "types": "definiciones de tipos",
    "interfaces": "interfaces TS",
    "dto": "Data Transfer Objects",
    "dtos": "Data Transfer Objects",
    "decorators": "decoradores",
    "guards": "guards de autenticación",
    "pipes": "pipes de transformación",
    "filters": "filtros de excepciones",
    "interceptors": "interceptores",
    "jobs": "tareas programadas",
    "tasks": "tareas",
    "queues": "colas de trabajo",
    "events": "eventos / pub-sub",
    "commands": "comandos CQRS",
    "queries": "queries CQRS",
}

# Indicadores de framework (clave lowercase del paquete → nombre legible)
FRAMEWORK_MAP: dict[str, str] = {
    "flask": "Flask", "django": "Django", "fastapi": "FastAPI",
    "aiohttp": "aiohttp", "tornado": "Tornado", "starlette": "Starlette",
    "sanic": "Sanic", "bottle": "Bottle", "falcon": "Falcon",
    "sqlalchemy": "SQLAlchemy", "peewee": "Peewee", "tortoise-orm": "Tortoise ORM",
    "mongoengine": "MongoEngine", "pymongo": "PyMongo",
    "alembic": "Alembic", "aerich": "Aerich",
    "celery": "Celery", "rq": "RQ", "dramatiq": "Dramatiq",
    "pydantic": "Pydantic", "marshmallow": "Marshmallow",
    "redis": "Redis", "aioredis": "aioredis",
    "tenacity": "Tenacity", "httpx": "httpx", "requests": "requests",
    "twilio": "Twilio", "boto3": "AWS SDK", "stripe": "Stripe",
    "pytest": "pytest", "unittest": "unittest",
    "sentry-sdk": "Sentry", "loguru": "loguru",
    "express": "Express", "fastify": "Fastify", "koa": "Koa",
    "@nestjs/core": "NestJS", "nestjs": "NestJS",
    "next": "Next.js", "nuxt": "Nuxt.js", "gatsby": "Gatsby",
    "typeorm": "TypeORM", "sequelize": "Sequelize",
    "mongoose": "Mongoose", "@prisma/client": "Prisma", "prisma": "Prisma",
    "knex": "Knex", "drizzle-orm": "Drizzle",
    "react": "React", "vue": "Vue", "@angular/core": "Angular",
    "svelte": "Svelte", "solid-js": "Solid",
    "vite": "Vite", "webpack": "Webpack",
    "jest": "Jest", "vitest": "Vitest", "mocha": "Mocha",
}

# Patrones de acceso a DB para query detection
RE_DB_PY = re.compile(
    r'\b(session\.(query|execute|add|commit|delete|merge|flush|scalar)|'
    r'db\.(session|engine)|'
    r'\.filter\(|\.filter_by\(|\.first\(\)|\.all\(\)|\.one\(\)|\.count\(\)|'
    r'cursor\.execute\(|connection\.execute\(|engine\.execute\(|'
    r'text\(|select\(|insert\(|update\(|delete\()\b'
)

RE_DB_JS = re.compile(
    r'\b(repository\.(find|save|update|delete|create|query|upsert)|'
    r'prisma\.\w+\.(find|create|update|delete|upsert|aggregate)|'
    r'Model\.(find|create|update|aggregate|deleteOne)|'
    r'sequelize\.query\(|knex\(|\.where\(|\.select\(|\.from\()\b'
)

# ─── Estructuras de datos ──────────────────────────────────────────────────────

@dataclass
class FileInfo:
    rel_path: str
    language: str
    role: str
    size: int
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    imports_internal: list[str] = field(default_factory=list)
    imports_external: list[str] = field(default_factory=list)
    jsdoc: dict[str, str] = field(default_factory=dict)
    has_db_access: bool = False
    docstring: str = ""          # module-level docstring o JSDoc @description
    query_examples: list[str] = field(default_factory=list)  # patrones ORM/SQL reales
    symbols_with_lines: dict[str, int] = field(default_factory=dict)  # nombre → línea
    function_infos: list = field(default_factory=list)                 # list[FunctionInfo]

@dataclass
class ModelField:
    name: str
    col_type: str = ""

@dataclass
class FunctionInfo:
    name: str
    start_line: int
    end_line: int
    params: list[str] = field(default_factory=list)
    return_type: str = ""
    decorators: list[str] = field(default_factory=list)
    complexity: int = 0   # lines of code (end_line - start_line + 1)
    is_async: bool = False


@dataclass
class ModelInfo:
    name: str
    file: str
    table: str
    fields: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)

@dataclass
class ProjectSummary:
    name: str
    root: Path
    description: str
    stack: dict[str, str]         # display_name → version
    languages: list[str]
    entry_points: list[str]
    folder_structure: dict[str, str]  # rel_folder → role
    files: list[FileInfo] = field(default_factory=list)
    models: list[ModelInfo] = field(default_factory=list)
    git_hotspots: list[tuple[str, int]] = field(default_factory=list)
    git_cochange: dict[str, list[str]] = field(default_factory=dict)
    git_recent_changes: dict[str, int] = field(default_factory=dict)   # file → commits last 30d
    git_ownership: dict[str, str] = field(default_factory=dict)        # file → primary author email
    git_pending: list[str] = field(default_factory=list)               # uncommitted files
    readme_summary: str = ""

# ─── Gate de aprobación ───────────────────────────────────────────────────────

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

# ─── Detección de stack ───────────────────────────────────────────────────────

def detect_stack(root: Path) -> dict[str, str]:
    """
    Extrae paquetes y versiones de manifests.
    Solo incluye paquetes presentes en FRAMEWORK_MAP (frameworks y libs relevantes).
    Retorna {nombre_display: version}.
    """
    stack: dict[str, str] = {}

    # requirements.txt
    req = root / "requirements.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z0-9_\-\.]+)([><=!~^]+(.*))?", line)
            if m:
                pkg = m.group(1).lower().replace("_", "-")
                ver = (m.group(3) or "").strip()
                if pkg in FRAMEWORK_MAP:
                    stack[FRAMEWORK_MAP[pkg]] = ver

    # pyproject.toml / Pipfile (solo regex, sin dependencia toml)
    for toml_path in [root / "pyproject.toml", root / "Pipfile"]:
        if toml_path.exists():
            content = toml_path.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'"([A-Za-z0-9_\-\.]+)"\s*=\s*"([^"]*)"', content):
                pkg = m.group(1).lower().replace("_", "-")
                if pkg in FRAMEWORK_MAP:
                    stack[FRAMEWORK_MAP[pkg]] = m.group(2)

    # package.json
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for pkg, ver in all_deps.items():
                display = FRAMEWORK_MAP.get(pkg.lower(), None)
                if display:
                    stack[display] = ver.lstrip("^~>=")
        except json.JSONDecodeError:
            pass

    return stack

def detect_project_name(root: Path) -> tuple[str, str]:
    """Retorna (nombre, descripcion_breve)."""
    # package.json
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            return data.get("name", root.name), data.get("description", "")
        except json.JSONDecodeError:
            pass

    # pyproject.toml
    toml = root / "pyproject.toml"
    if toml.exists():
        content = toml.read_text(encoding="utf-8", errors="replace")
        m_name = re.search(r'name\s*=\s*"([^"]+)"', content)
        m_desc = re.search(r'description\s*=\s*"([^"]+)"', content)
        if m_name:
            return m_name.group(1), (m_desc.group(1) if m_desc else "")

    # setup.py
    setup = root / "setup.py"
    if setup.exists():
        content = setup.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", content)
        if m:
            return m.group(1), ""

    return root.name, ""

def detect_readme_summary(root: Path) -> str:
    """Extrae la primera línea de contenido real del README."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        readme = root / name
        if readme.exists():
            lines = readme.read_text(encoding="utf-8", errors="replace").splitlines()
            # Busca primera línea no vacía que no sea un encabezado de título
            meaningful = [
                l.strip() for l in lines
                if l.strip() and not l.startswith("#") and not l.startswith("=")
            ]
            return meaningful[0] if meaningful else ""
    return ""

# ─── Scanner de archivos ──────────────────────────────────────────────────────

def classify_role(rel_path: str) -> str:
    filename = Path(rel_path).name.lower()
    for pattern, role in ROLE_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            return role
    return "other"

def should_ignore(path: Path) -> bool:
    for part in path.parts:
        if part in IGNORE_DIRS or part.endswith(".egg-info"):
            return True
    return path.suffix in IGNORE_EXTS

def scan_structure(root: Path) -> dict[str, str]:
    """Retorna {carpeta_relativa: rol} para carpetas de primer y segundo nivel."""
    result: dict[str, str] = {}
    try:
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name in IGNORE_DIRS or entry.name.startswith("."):
                continue
            role = FOLDER_ROLES.get(entry.name.lower(), "")
            result[entry.name] = role
            # Segundo nivel si la carpeta no tiene rol conocido
            if not role:
                for sub in sorted(entry.iterdir()):
                    if sub.is_dir() and sub.name not in IGNORE_DIRS and not sub.name.startswith("."):
                        sub_role = FOLDER_ROLES.get(sub.name.lower(), "")
                        if sub_role:
                            result[f"{entry.name}/{sub.name}"] = sub_role
    except PermissionError:
        pass
    return result

def walk_source_files(root: Path) -> list[Path]:
    """Devuelve todos los archivos de código fuente, respetando IGNORE_DIRS."""
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Modifica en-lugar para que os.walk no entre en carpetas ignoradas
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in IGNORE_DIRS and not d.startswith(".")
            and not d.endswith(".egg-info")
        )
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix in SOURCE_EXTS and not should_ignore(fpath):
                result.append(fpath)
    return result

# ─── Extracción de query examples ────────────────────────────────────────────

RE_QUERY_EXAMPLES = re.compile(
    r'session\.(?:query|execute)\s*\([^)\n]{8,100}\)'
    r'|\.filter(?:_by)?\s*\([^)\n]{5,80}\)'
    r'|\.order_by\s*\([^)\n]{5,60}\)'
    r'|repository\.\w+\s*\([^)\n]{5,80}\)'
    r'|prisma\.\w+\.(?:find\w*|create|update|delete)\s*\([^)\n]{5,80}\)',
    re.MULTILINE,
)

def extract_query_examples(source: str) -> list[str]:
    seen: set[str] = set()
    examples: list[str] = []
    for m in RE_QUERY_EXAMPLES.finditer(source):
        ex = re.sub(r'\s+', ' ', m.group(0).strip())
        if ex not in seen:
            seen.add(ex)
            examples.append(ex)
        if len(examples) >= 4:
            break
    return examples

# ─── Extracción Python (AST) ──────────────────────────────────────────────────

def _ast_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_ast_name(node.value)}.{node.attr}"
    return ""

def _ast_call_name(node: ast.Call) -> str:
    return _ast_name(node.func)

def extract_python(path: Path, project_root: Path) -> FileInfo:
    rel = str(path.relative_to(project_root))
    size = path.stat().st_size
    lang = "python"
    role = classify_role(rel)

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return FileInfo(rel, lang, role, size)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return FileInfo(rel, lang, role, size)

    classes: list[str] = []
    functions: list[str] = []
    imports_int: list[str] = []
    imports_ext: list[str] = []
    models: list[ModelInfo] = []
    symbols_with_lines: dict[str, int] = {}
    has_db = bool(RE_DB_PY.search(source))

    # Docstring de módulo (primer statement si es una cadena literal)
    module_docstring = ""
    if tree.body and isinstance(tree.body[0], ast.Expr):
        val = tree.body[0].value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            raw = val.value.strip()
            # Primera línea no vacía, máx 150 chars
            first = next((l.strip() for l in raw.splitlines() if l.strip()), raw)
            module_docstring = first[:150]

    project_pkg = project_root.name  # heuristic: imports starting with project name are internal

    fn_infos: list[FunctionInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            if node.name not in symbols_with_lines:
                symbols_with_lines[node.name] = node.lineno
            # Params
            params = [a.arg for a in node.args.args if a.arg != "self"]
            # Return type
            ret = ""
            if node.returns:
                try:
                    ret = ast.unparse(node.returns) if hasattr(ast, "unparse") else ""
                except Exception:
                    ret = ""
            # Decorators
            decs = []
            for d in node.decorator_list:
                try:
                    decs.append(ast.unparse(d) if hasattr(ast, "unparse") else "")
                except Exception:
                    pass
            end_ln = getattr(node, "end_lineno", node.lineno)
            fn_infos.append(FunctionInfo(
                name=node.name,
                start_line=node.lineno,
                end_line=end_ln,
                params=params[:8],
                return_type=ret[:60],
                decorators=[d for d in decs if d][:4],
                complexity=max(1, end_ln - node.lineno + 1),
                is_async=isinstance(node, ast.AsyncFunctionDef),
            ))

        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
            if node.name not in symbols_with_lines:
                symbols_with_lines[node.name] = node.lineno
            bases = [_ast_name(b) for b in node.bases]

            # Detectar modelos SQLAlchemy / Django ORM
            is_sqla = any(
                b in ("Base", "db.Model", "Model") or b.endswith("Base") or "Model" in b
                for b in bases
            )
            if is_sqla:
                fields: list[str] = []
                rels: list[str] = []
                table_name = node.name.lower()

                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if not isinstance(target, ast.Name):
                                continue
                            if target.id == "__tablename__" and isinstance(item.value, ast.Constant):
                                table_name = str(item.value.value)
                            elif isinstance(item.value, ast.Call):
                                fn = _ast_call_name(item.value)
                                if "Column" in fn or "mapped_column" in fn:
                                    # Intenta extraer el tipo del primer arg
                                    col_type = ""
                                    if item.value.args:
                                        col_type = _ast_name(item.value.args[0])
                                    fields.append(f"{target.id}:{col_type}" if col_type else target.id)
                                elif "relationship" in fn or "Relationship" in fn:
                                    rels.append(target.id)
                            elif isinstance(item.value, ast.Attribute):
                                # mapped_column via annotation
                                pass
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        # SQLAlchemy 2.0 Mapped[X] style
                        ann = ast.unparse(item.annotation) if hasattr(ast, "unparse") else ""
                        if "Mapped" in ann or "mapped_column" in ann:
                            fields.append(item.target.id)
                        elif "relationship" in ann.lower():
                            rels.append(item.target.id)

                models.append(ModelInfo(node.name, rel, table_name, fields, rels))

        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top == project_pkg:
                    imports_int.append(alias.name)
                else:
                    imports_ext.append(top)

        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                imports_int.append(f".{node.module or ''}")
            elif node.module:
                top = node.module.split(".")[0]
                if top == project_pkg:
                    imports_int.append(node.module)
                else:
                    imports_ext.append(top)

    # Solo top-level functions (no métodos): reparse
    top_functions = [
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    # Aproximación: las funciones de ast.walk incluyen métodos; filtramos startswith("_") menores
    top_functions = [f for f in top_functions if not f.startswith("_")][:20]

    fi = FileInfo(
        rel_path=rel, language=lang, role=role, size=size,
        classes=classes, functions=top_functions,
        imports_internal=list(set(imports_int)),
        imports_external=list(set(imports_ext)),
        has_db_access=has_db,
        docstring=module_docstring,
        query_examples=extract_query_examples(source) if has_db else [],
        symbols_with_lines=symbols_with_lines,
        function_infos=fn_infos,
    )
    fi.__dict__["_models"] = models  # transporte temporal
    return fi

# ─── Extracción JS/TS (Regex) ─────────────────────────────────────────────────

RE_EXPORT     = re.compile(r'export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|type|interface|enum|abstract\s+class)\s+(\w+)')
RE_EXPORT_OBJ = re.compile(r'export\s*\{([^}]+)\}')
RE_IMPORT     = re.compile(r"import\s+(?:type\s+)?(?:\{[^}]*\}|\w+|\*\s+as\s+\w+)\s+from\s+['\"]([^'\"]+)['\"]")
RE_CLASS      = re.compile(r'(?:export\s+)?(?:abstract\s+)?class\s+(\w+)')
RE_FUNCTION   = re.compile(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)')
RE_JSDOC      = re.compile(r'/\*\*([\s\S]*?)\*/')
RE_JSDOC_TAG  = re.compile(r'@(\w+)\s+(.*)')
RE_ENTITY_TS  = re.compile(r'@Entity\(')
RE_SCHEMA_MG  = re.compile(r'new\s+Schema\s*\(')
RE_PRISMA_MDL = re.compile(r'^model\s+(\w+)\s*\{', re.MULTILINE)

def _line_of(source: str, pos: int) -> int:
    """Retorna el número de línea (1-based) para una posición en el texto."""
    return source[:pos].count("\n") + 1


def extract_js_ts(path: Path, project_root: Path) -> FileInfo:
    rel = str(path.relative_to(project_root))
    size = path.stat().st_size
    lang = SOURCE_EXTS.get(path.suffix, "javascript")
    role = classify_role(rel)

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return FileInfo(rel, lang, role, size)

    # JSDoc tags + descripción del primer bloque como docstring
    jsdoc: dict[str, str] = {}
    module_docstring = ""
    first_jsdoc = RE_JSDOC.search(source)
    if first_jsdoc:
        block_text = first_jsdoc.group(1)
        # Líneas sin @ son la descripción libre del bloque
        desc_lines = [
            l.strip().lstrip("* ").strip()
            for l in block_text.splitlines()
            if l.strip() and not l.strip().lstrip("* ").startswith("@")
        ]
        if desc_lines:
            module_docstring = desc_lines[0][:150]
    for block in RE_JSDOC.finditer(source):
        for tag in RE_JSDOC_TAG.finditer(block.group(1)):
            jsdoc[tag.group(1)] = tag.group(2).strip()
    # @description o @purpose sobreescriben la descripción libre
    if jsdoc.get("description") or jsdoc.get("purpose"):
        module_docstring = (jsdoc.get("description") or jsdoc.get("purpose", ""))[:150]

    # Exports
    exports: list[str] = []
    for m in RE_EXPORT.finditer(source):
        exports.append(m.group(1))
    for m in RE_EXPORT_OBJ.finditer(source):
        for name in m.group(1).split(","):
            name = name.strip().split(" as ")[0].strip()
            if name and re.match(r'^\w+$', name):
                exports.append(name)

    # Imports
    imports_int: list[str] = []
    imports_ext: list[str] = []
    for m in RE_IMPORT.finditer(source):
        spec = m.group(1)
        if spec.startswith("."):
            imports_int.append(spec)
        else:
            top = spec.split("/")[0].lstrip("@")
            imports_ext.append(top)

    symbols_with_lines: dict[str, int] = {}
    classes = list(dict.fromkeys(m.group(1) for m in RE_CLASS.finditer(source)))
    for m in RE_CLASS.finditer(source):
        name = m.group(1)
        if name not in symbols_with_lines:
            symbols_with_lines[name] = _line_of(source, m.start())
    functions = list(dict.fromkeys(m.group(1) for m in RE_FUNCTION.finditer(source) if not m.group(1).startswith("_")))
    for m in RE_FUNCTION.finditer(source):
        name = m.group(1)
        if not name.startswith("_") and name not in symbols_with_lines:
            symbols_with_lines[name] = _line_of(source, m.start())
    for m in RE_EXPORT.finditer(source):
        name = m.group(1)
        if name not in symbols_with_lines:
            symbols_with_lines[name] = _line_of(source, m.start())

    # FunctionInfo para JS/TS (limitado: sin tipos completos vía regex)
    fn_infos_js: list[FunctionInfo] = []
    RE_FN_PARAMS = re.compile(
        r'(?:async\s+)?function\s+(\w+)\s*\(([^)]{0,200})\)'
        r'|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]{0,200})\)\s*(?::\s*\w[\w<>[\], ]*?)?\s*=>'
    )
    RE_DEC = re.compile(r'@(\w[\w.]*)\s*(?:\([^)]*\))?\s*\n\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+(\w+)')
    decorators_by_name: dict[str, list[str]] = defaultdict(list)
    for m in RE_DEC.finditer(source):
        decorators_by_name[m.group(2)].append(m.group(1))

    for m in RE_FN_PARAMS.finditer(source):
        fname = m.group(1) or m.group(3)
        raw_params = m.group(2) or m.group(4) or ""
        if not fname or fname.startswith("_"):
            continue
        params = [p.strip().split(":")[0].strip() for p in raw_params.split(",") if p.strip()]
        line = _line_of(source, m.start())
        fn_infos_js.append(FunctionInfo(
            name=fname,
            start_line=line,
            end_line=line,   # end_line no fiable con regex
            params=params[:8],
            decorators=decorators_by_name.get(fname, [])[:4],
            complexity=1,
            is_async="async" in (source[max(0, m.start()-10):m.start()] + m.group(0))[:20],
        ))

    has_db = bool(RE_DB_JS.search(source))

    # Detectar modelos TypeORM / Mongoose
    models: list[ModelInfo] = []
    if RE_ENTITY_TS.search(source):
        for cls in classes:
            models.append(ModelInfo(cls, rel, cls.lower(), [], []))
    if RE_SCHEMA_MG.search(source):
        for cls in classes:
            if "schema" in cls.lower() or "model" in cls.lower():
                models.append(ModelInfo(cls, rel, cls.lower().replace("schema","").replace("model",""), [], []))

    fi = FileInfo(
        rel_path=rel, language=lang, role=role, size=size,
        classes=classes, functions=functions[:20],
        exports=exports[:20],
        imports_internal=list(set(imports_int)),
        imports_external=list(set(imports_ext)),
        jsdoc=jsdoc, has_db_access=has_db,
        docstring=module_docstring,
        query_examples=extract_query_examples(source) if has_db else [],
        symbols_with_lines=symbols_with_lines,
        function_infos=fn_infos_js,
    )
    fi.__dict__["_models"] = models
    return fi

def extract_prisma_models(root: Path) -> list[ModelInfo]:
    models: list[ModelInfo] = []
    for schema_file in root.rglob("schema.prisma"):
        if should_ignore(schema_file):
            continue
        source = schema_file.read_text(encoding="utf-8", errors="replace")
        for m in RE_PRISMA_MDL.finditer(source):
            name = m.group(1)
            # Extrae campos del bloque
            block_start = m.end()
            depth = 1
            block_end = block_start
            for i, ch in enumerate(source[block_start:], block_start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        block_end = i
                        break
            block = source[block_start:block_end]
            fields = [
                line.strip().split()[0]
                for line in block.splitlines()
                if line.strip() and not line.strip().startswith("//") and not line.strip().startswith("@@")
                and len(line.strip().split()) >= 2
            ]
            rel = str(schema_file.relative_to(root))
            models.append(ModelInfo(name, rel, name.lower(), fields, []))
    return models

# ─── Análisis de Git ──────────────────────────────────────────────────────────

def analyze_git(root: Path, max_commits: int = 200) -> tuple[list[tuple[str, int]], dict[str, list[str]]]:
    """
    Retorna:
      hotspots: [(archivo, n_commits)] — archivos más modificados
      cochange: {archivo: [archivos_que_cambian_juntos]} — top 3 por archivo
    """
    try:
        result = subprocess.run(
            ["git", "log", "--name-only", f"--max-count={max_commits}", "--format="],
            cwd=root, capture_output=True, text=True, timeout=15
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return [], {}

    if result.returncode != 0:
        return [], {}

    # Agrupar archivos por commit (separados por línea vacía)
    commits: list[list[str]] = []
    current: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            current.append(line)
        else:
            if current:
                commits.append(current)
                current = []
    if current:
        commits.append(current)

    # Hotspots
    freq: dict[str, int] = defaultdict(int)
    for commit in commits:
        for f in commit:
            freq[f] += 1
    hotspots = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:15]

    # Co-change
    cochange: dict[str, list[str]] = defaultdict(lambda: defaultdict(int))
    for commit in commits:
        if len(commit) < 2:
            continue
        for i, fa in enumerate(commit):
            for fb in commit[i+1:]:
                cochange[fa][fb] += 1
                cochange[fb][fa] += 1

    # Retener solo top 3 co-changes por archivo con >= 3 co-apariciones
    result_cochange: dict[str, list[str]] = {}
    for fa, partners in cochange.items():
        top = sorted(partners.items(), key=lambda x: x[1], reverse=True)
        strong = [f for f, cnt in top[:3] if cnt >= 3]
        if strong:
            result_cochange[fa] = strong

    return hotspots, result_cochange

def analyze_git_extended(root: Path) -> tuple[dict[str, int], dict[str, str], list[str]]:
    """
    Returns:
        recent_changes: {file: commits in last 30 days}
        ownership:      {file: primary author email (most commits)}
        pending:        list of files with uncommitted changes
    """
    recent_changes: dict[str, int] = defaultdict(int)
    ownership_raw: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    pending: list[str] = []

    # Recent changes: last 30 days
    try:
        r = subprocess.run(
            ["git", "log", "--since=30 days ago", "--name-only", "--format=%ae"],
            cwd=root, capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            current_author = ""
            for line in r.stdout.splitlines():
                line = line.strip()
                if not line:
                    current_author = ""
                    continue
                if "@" in line or "." in line and "/" not in line:
                    current_author = line
                else:
                    recent_changes[line] += 1
                    if current_author:
                        ownership_raw[line][current_author] += 1
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Full ownership from all history (merge with recent)
    try:
        r = subprocess.run(
            ["git", "log", "--name-only", "--format=%ae", "--max-count=500"],
            cwd=root, capture_output=True, text=True, timeout=20,
        )
        if r.returncode == 0:
            current_author = ""
            for line in r.stdout.splitlines():
                line = line.strip()
                if not line:
                    current_author = ""
                    continue
                if "@" in line or ("." in line and "/" not in line and len(line) < 80):
                    current_author = line
                else:
                    if current_author:
                        ownership_raw[line][current_author] += 1
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Resolve ownership: primary author per file
    ownership: dict[str, str] = {}
    for fpath, authors in ownership_raw.items():
        if authors:
            ownership[fpath] = max(authors, key=lambda a: authors[a])

    # Pending uncommitted changes
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if len(line) > 3:
                    pending.append(line[3:].strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return dict(recent_changes), ownership, pending


# ─── Construcción del modelo del proyecto ─────────────────────────────────────

def build_project(root: Path, stack: dict[str, str]) -> ProjectSummary:
    name, description = detect_project_name(root)
    if not description:
        description = detect_readme_summary(root)

    langs_seen: dict[str, int] = defaultdict(int)
    all_files: list[FileInfo] = []
    all_models: list[ModelInfo] = []

    source_files = walk_source_files(root)
    print(f"  Escaneando {len(source_files)} archivos fuente...")

    for fpath in source_files:
        ext = fpath.suffix
        lang = SOURCE_EXTS.get(ext, "other")
        langs_seen[lang] += 1

        if lang == "python":
            fi = extract_python(fpath, root)
        elif lang in ("typescript", "javascript", "vue", "svelte"):
            fi = extract_js_ts(fpath, root)
        else:
            rel = str(fpath.relative_to(root))
            fi = FileInfo(rel, lang, classify_role(rel), fpath.stat().st_size)

        all_files.append(fi)
        all_models.extend(fi.__dict__.pop("_models", []))

    # Prisma schemas
    all_models.extend(extract_prisma_models(root))
    # Deduplicar modelos por nombre
    seen_models: set[str] = set()
    unique_models: list[ModelInfo] = []
    for m in all_models:
        if m.name not in seen_models:
            seen_models.add(m.name)
            unique_models.append(m)

    languages = [lang for lang, _ in sorted(langs_seen.items(), key=lambda x: x[1], reverse=True)
                 if lang not in ("html", "sql", "other")]

    entry_points = [f.rel_path for f in all_files if f.role == "entry_point"]
    folder_structure = scan_structure(root)

    hotspots, cochange = analyze_git(root)
    recent_changes, ownership, pending = analyze_git_extended(root)

    return ProjectSummary(
        name=name, root=root, description=description,
        stack=stack, languages=languages,
        entry_points=entry_points,
        folder_structure=folder_structure,
        files=all_files, models=unique_models,
        git_hotspots=hotspots, git_cochange=cochange,
        git_recent_changes=recent_changes,
        git_ownership=ownership,
        git_pending=pending,
        readme_summary=description,
    )

# ─── Inferencia de arquitectura ───────────────────────────────────────────────

def infer_architecture(proj: ProjectSummary) -> str:
    """Infiere la cadena de capas a partir de carpetas detectadas."""
    folders = {k.split("/")[0].lower() for k in proj.folder_structure}

    layers: list[str] = []
    if folders & {"blueprints", "routes", "routers", "api", "endpoints", "controllers", "handlers"}:
        sample = next(iter(folders & {"blueprints", "routes", "routers", "api", "endpoints", "controllers", "handlers"}))
        layers.append(sample.upper())
    if folders & {"controllers", "handlers"} and layers:
        if "CONTROLLERS" not in layers[0].upper() and "HANDLERS" not in layers[0].upper():
            layers.append("CONTROLLERS")
    if folders & {"services", "adapters", "providers"}:
        layers.append("SERVICES")
    if folders & {"managers", "repositories", "repos", "dao"}:
        sample = next(iter(folders & {"managers", "repositories", "repos", "dao"}))
        layers.append(sample.upper())
    if folders & {"models", "entities", "domain"}:
        layers.append("MODELS")

    if not layers:
        return "Arquitectura no inferida — revisar estructura de carpetas"

    # Externos detectados
    externals: list[str] = []
    stack_keys = set(proj.stack.keys())
    if stack_keys & {"SQLAlchemy", "Django ORM", "TypeORM", "Prisma", "Mongoose", "Sequelize", "Drizzle"}:
        externals.append("DB")
    if stack_keys & {"Redis", "aioredis"}:
        externals.append("Redis")
    if stack_keys & {"Twilio", "httpx", "requests"}:
        externals.append("APIs externas")

    chain = " → ".join(layers)
    if externals:
        chain += f" → [{' | '.join(externals)}]"
    return chain

def detect_code_smells(proj: ProjectSummary) -> list[str]:
    """Detecta god objects, archivos grandes y otros smells básicos."""
    smells: list[str] = []
    # Archivos > 50 KB en código fuente
    large = sorted(
        [f for f in proj.files if f.size > 50_000 and f.language in ("python", "typescript", "javascript")],
        key=lambda x: x.size, reverse=True
    )[:5]
    for f in large:
        kb = f.size // 1024
        smells.append(f"`{f.rel_path}` ({kb} KB) — archivo sobredimensionado, posible God Object")

    # Archivos con muchas clases
    multi_class = [f for f in proj.files if len(f.classes) > 8]
    for f in multi_class:
        if not any(f.rel_path in s for s in smells):
            smells.append(f"`{f.rel_path}` — {len(f.classes)} clases en un archivo")

    return smells

# ─── Enriquecimiento semántico ────────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "py", "ts", "js", "mjs", "test", "tests", "spec", "the", "for", "is",
    "get", "set", "add", "del", "run", "use", "new", "old", "base", "init",
    "by", "to", "of", "in", "my", "do", "on", "at",
})

# Stems demasiado genéricos para aportar valor en related_to
_GENERIC_STEMS = frozenset({
    "index", "main", "app", "base", "init", "utils", "helpers", "common",
    "config", "types", "constants", "shared", "core",
})

_ROLE_VERBS: dict[str, str] = {
    "entry_point":   "Punto de entrada de la aplicación",
    "controller":    "Define rutas HTTP para",
    "service":       "Adapta el servicio externo de",
    "data_access":   "Gestiona acceso a datos de",
    "model":         "Define los modelos ORM de",
    "schema":        "Valida el esquema de entrada para",
    "utility":       "Utilidades para",
    "config":        "Configuración de",
    "state_machine": "Define la máquina de estados de",
    "db_connection": "Gestiona la conexión a la base de datos",
    "migration":     "Migración de esquema de",
    "middleware":    "Middleware para",
    "component":     "Componente UI de",
    "template":      "Plantilla HTML de",
}

def extract_keywords(fi: FileInfo) -> list[str]:
    """
    Extrae términos de búsqueda semánticos (para que los readers encuentren el archivo)
    y nombres completos de símbolos (para que el planner pueda hacer grep directo).
    """
    seen: set[str] = set()
    result: list[str] = []

    def add(token: str) -> None:
        t = token.strip()
        if len(t) > 2 and t.lower() not in _STOP_WORDS and t not in seen:
            seen.add(t)
            result.append(t)

    # 1. Fragmentos del nombre del archivo (búsqueda semántica)
    stem = Path(fi.rel_path).stem
    for part in re.split(r"[_\-\.]", stem):
        add(part.lower())

    # 2. Nombres completos de clases (greppables) + sus fragmentos CamelCase
    for cls in fi.classes[:5]:
        add(cls)  # nombre completo, ej: "AuthController"
        for part in re.findall(r"[A-Z][a-z]+|[a-z]+", cls):
            add(part.lower())

    # 3. Nombres completos de funciones públicas (greppables)
    for fn in (fi.functions or fi.exports)[:8]:
        add(fn)  # nombre completo, ej: "authenticate"
        for part in re.split(r"_", fn):
            add(part.lower())

    # 4. Palabras clave del docstring (máx 3 sustantivos relevantes)
    if fi.docstring:
        doc_words = re.findall(r"[a-zA-Z]{4,}", fi.docstring)
        for w in doc_words[:6]:
            if w.lower() not in _STOP_WORDS:
                add(w.lower())

    return result[:15]

def infer_purpose(fi: FileInfo) -> str:
    """Infiere el propósito del módulo en este orden: docstring → JSDoc → heurística."""
    if fi.docstring:
        sentence = fi.docstring.split(".")[0].strip()
        if len(sentence) > 10:
            return sentence
    desc = fi.jsdoc.get("description") or fi.jsdoc.get("purpose")
    if desc:
        return desc.split(".")[0].strip()[:120]
    # Heurística por rol + nombre
    stem = Path(fi.rel_path).stem
    parts = [k for k in re.split(r"[_\-]", stem) if len(k) > 2]
    verb = _ROLE_VERBS.get(fi.role, "Módulo de")
    subject = " ".join(parts[1:]) if len(parts) > 1 else (parts[0] if parts else stem)
    return f"{verb} {subject}"

def find_related(
    fi: FileInfo,
    all_files: list[FileInfo],
    cochange: dict[str, list[str]],
) -> list[str]:
    """Encuentra módulos relacionados desde imports internos + git co-change."""
    stem = Path(fi.rel_path).stem
    stems_by_path = {f.rel_path: Path(f.rel_path).stem for f in all_files}
    related: list[str] = []

    # Desde imports internos: busca archivos cuyo stem coincide con el import
    for imp in fi.imports_internal:
        imp_stem = imp.rstrip("/").replace(".", "/").split("/")[-1]
        if imp_stem and imp_stem != stem and imp_stem not in related:
            if any(s == imp_stem for s in stems_by_path.values()):
                related.append(imp_stem)

    # Desde co-change git (excluye stems genéricos)
    for cochanged_path in cochange.get(fi.rel_path, []):
        co_stem = Path(cochanged_path).stem
        if co_stem != stem and co_stem not in related and co_stem not in _GENERIC_STEMS:
            related.append(co_stem)

    return related[:5]

def build_symbols(fi: FileInfo) -> list[dict]:
    """Devuelve lista de {name, line, end_line, kind, params, return_type, decorators, complexity} para los símbolos."""
    # Index FunctionInfo by name for fast lookup
    fn_by_name: dict[str, FunctionInfo] = {f.name: f for f in fi.function_infos}
    result = []
    for name, line in sorted(fi.symbols_with_lines.items(), key=lambda x: x[1]):
        kind = "class" if name in fi.classes else "function"
        entry: dict = {"name": name, "line": line, "kind": kind}
        if name in fn_by_name:
            fn = fn_by_name[name]
            entry["end_line"] = fn.end_line
            entry["complexity"] = fn.complexity
            if fn.params:
                entry["params"] = fn.params
            if fn.return_type:
                entry["return_type"] = fn.return_type
            if fn.decorators:
                entry["decorators"] = fn.decorators
            if fn.is_async:
                entry["is_async"] = True
        result.append(entry)
    return result[:15]


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
    }

def build_query_entry(
    fi: FileInfo,
    all_files: list[FileInfo],
    cochange: dict[str, list[str]],
) -> dict:
    """Construye el objeto enriquecido para un archivo en QUERY_MAP.json."""
    return {
        "path":            fi.rel_path,
        "role":            fi.role,
        "purpose":         infer_purpose(fi),
        "search_keywords": extract_keywords(fi),
        "related_to":      find_related(fi, all_files, cochange),
        "functions":       (fi.functions or fi.exports)[:8],
        "symbols":         build_symbols(fi),
        "query_examples":  fi.query_examples,
    }


def resolve_dependencies(files: list[FileInfo]) -> dict:
    """
    Construye grafo de dependencias bidireccional:
    {"forward": {file: [dep_paths]}, "reverse": {file: [dependent_paths]}}

    Estrategias de resolución (orden descendente de precisión):
    1. Ruta completa sin extensión  → by_full_no_ext
    2. Claves multi-segmento (2-4)  → by_segments
    3. Directorio index (index/__init__) → by_index
    4. Stem (último segmento)       → by_stem
    """
    # ── Construir índices ──────────────────────────────────────────────────────
    by_stem:         dict[str, str] = {}   # "views" → rel_path
    by_segments:     dict[str, str] = {}   # "auth/views" → rel_path
    by_full_no_ext:  dict[str, str] = {}   # "src/auth/views" → rel_path
    by_index:        dict[str, str] = {}   # "src/auth" → "src/auth/index.ts"

    for f in files:
        p = Path(f.rel_path)
        # Ruta completa sin extensión (lowercase, forward slashes)
        no_ext = str(p.with_suffix("")).lower().replace("\\", "/")
        by_full_no_ext[no_ext] = f.rel_path

        stem = p.stem.lower()
        if stem not in by_stem:
            by_stem[stem] = f.rel_path

        # Multi-segmento: keys de 2 a 4 componentes del path sin extensión
        parts = p.with_suffix("").parts
        for n in range(2, min(len(parts) + 1, 5)):
            key = "/".join(parts[-n:]).lower()
            if key not in by_segments:
                by_segments[key] = f.rel_path

        # Index files: __init__.py / index.ts / index.js
        if stem in ("__init__", "index"):
            dir_key = str(p.parent).lower().replace("\\", "/")
            if dir_key not in by_index:
                by_index[dir_key] = f.rel_path

    # ── Resolvers por lenguaje ─────────────────────────────────────────────────

    def _lookup(parts_list: list[str]) -> str | None:
        """Intenta resolver una lista de segmentos usando los índices, de más específico a menos."""
        if not parts_list:
            return None
        # 1. Ruta completa normalizada
        full_key = "/".join(p.lower() for p in parts_list)
        if full_key in by_full_no_ext:
            return by_full_no_ext[full_key]
        # 2. Multi-segmento (decreciente)
        for n in range(min(len(parts_list), 4), 1, -1):
            key = "/".join(p.lower() for p in parts_list[-n:])
            if key in by_segments:
                return by_segments[key]
        # 3. Index del directorio
        dir_key = "/".join(p.lower() for p in parts_list)
        if dir_key in by_index:
            return by_index[dir_key]
        # 4. Stem del último segmento
        last_stem = Path(parts_list[-1]).stem.lower()
        if last_stem and last_stem not in ("index", "__init__") and last_stem in by_stem:
            return by_stem[last_stem]
        return None

    def resolve_python(imp: str, file_path: str) -> str | None:
        p_file = Path(file_path)
        if imp.startswith("."):
            # Import relativo: ".module", "..pkg.module"
            level = len(imp) - len(imp.lstrip("."))
            module_part = imp.lstrip(".")
            base = p_file.parent
            for _ in range(level - 1):
                base = base.parent
            if not module_part:
                # "from . import X" → __init__.py del directorio actual
                dir_key = str(base).lower().replace("\\", "/")
                return by_index.get(dir_key)
            module_path = module_part.replace(".", "/")
            target_parts = list(base.parts) + module_path.split("/")
            return _lookup(target_parts)
        else:
            # Import absoluto interno: "myapp.auth.views"
            parts_list = imp.split(".")
            return _lookup(parts_list)

    def resolve_js(imp: str, file_path: str) -> str | None:
        # Normaliza separadores
        imp_clean = imp.replace("\\", "/")
        file_dir_parts = file_path.replace("\\", "/").split("/")[:-1]

        # Resuelve el path relativo manualmente (sin acceso al filesystem real)
        out: list[str] = list(file_dir_parts)
        for segment in imp_clean.split("/"):
            if segment in ("", "."):
                continue
            elif segment == "..":
                if out:
                    out.pop()
            else:
                out.append(segment)

        if not out:
            return None

        # Elimina extensión si el último segmento ya la trae
        last = out[-1]
        for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            if last.lower().endswith(ext):
                out[-1] = last[: -len(ext)]
                break

        return _lookup(out)

    # ── Construir grafo forward ────────────────────────────────────────────────
    forward: dict[str, list[str]] = {}

    for f in files:
        seen: set[str] = set()
        for imp in f.imports_internal:
            resolved = (
                resolve_python(imp, f.rel_path)
                if f.language == "python"
                else resolve_js(imp, f.rel_path)
            )
            if resolved and resolved != f.rel_path and resolved not in seen:
                seen.add(resolved)
        if seen:
            forward[f.rel_path] = sorted(seen)

    # ── Construir grafo reverse ────────────────────────────────────────────────
    reverse: dict[str, list[str]] = {}
    for src, deps in forward.items():
        for dep in deps:
            reverse.setdefault(dep, [])
            if src not in reverse[dep]:
                reverse[dep].append(src)
    for k in reverse:
        reverse[k].sort()

    return {"forward": forward, "reverse": reverse}

# ─── Constructores de MAP (producen dicts → serializados a JSON) ──────────────

def build_project_map(proj: ProjectSummary) -> dict:
    # Agrupa archivos por rol, enriqueciendo cada entrada
    modules: dict[str, list[dict]] = defaultdict(list)
    for f in proj.files:
        if f.role not in ("other", "test", "template", "component") and \
           f.language in ("python", "typescript", "javascript"):
            modules[f.role].append(
                build_module_entry(f, proj.files, proj.git_cochange)
            )

    problems = []
    for s in detect_code_smells(proj):
        parts = s.split(" — ", 1)
        file_part = parts[0].strip("`")
        desc = parts[1] if len(parts) > 1 else ""
        problems.append({"file": file_part, "issue": desc})

    dependencies = resolve_dependencies(proj.files)

    # Recent hotspots: top 10 files changed in last 30 days
    recent_top = sorted(proj.git_recent_changes.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "name": proj.name,
        "description": proj.description,
        "languages": proj.languages,
        "stack": proj.stack,
        "structure": proj.folder_structure,
        "architecture": infer_architecture(proj),
        "entry_points": proj.entry_points,
        "modules": dict(modules),
        "hotspots": [{"file": f, "commits": c} for f, c in proj.git_hotspots[:10]],
        "recent_changes": [{"file": f, "commits_30d": c} for f, c in recent_top],
        "ownership": proj.git_ownership,
        "pending_changes": proj.git_pending,
        "cochange": {f: p for f, p in list(proj.git_cochange.items())[:20]},
        "dependencies": dependencies,
        "problems": problems,
    }


def build_db_map(proj: ProjectSummary) -> dict:
    db_techs = [t for t in proj.stack if t in (
        "SQLAlchemy", "Django ORM", "TypeORM", "Prisma", "Mongoose",
        "Sequelize", "Drizzle", "Peewee", "Tortoise ORM", "MongoEngine", "PyMongo", "Knex",
    )]
    db_infra = [t for t in proj.stack if any(k in t for k in (
        "SQL", "Postgres", "MySQL", "Mongo", "Redis", "SQLite", "Dynamo",
    ))]
    migrations = [f.rel_path for f in proj.files if f.role == "migration"]
    seeds = [m for m in migrations if "seed" in m.lower()]
    pure_migrations = [m for m in migrations if "seed" not in m.lower()]
    db_conn = [f.rel_path for f in proj.files if f.role == "db_connection"]

    # Solo modelos que provienen de archivos de modelos reales (excluir schemas Pydantic)
    real_models = [
        m for m in proj.models
        if any(k in m.file for k in ("model", "entit", "domain", "schema.prisma"))
        or m.file in ("models.py", "model.py")
        or (m.fields and len(m.fields) >= 2)
    ]

    return {
        "orm": db_techs[0] if db_techs else None,
        "database": db_infra[0] if db_infra else None,
        "connection_files": db_conn,
        "models": [
            {
                "name": m.name,
                "table": m.table,
                "file": m.file,
                "fields": m.fields,
                "relationships": m.relationships,
            }
            for m in sorted(real_models, key=lambda x: x.name)
        ],
        "migrations": pure_migrations,
        "seeds": seeds,
    }


def build_query_map(proj: ProjectSummary) -> dict:
    db_files = [f for f in proj.files if f.has_db_access and f.role != "test"]
    da_files = [f for f in proj.files if f.role == "data_access"]
    all_query = list({f.rel_path: f for f in db_files + da_files}.values())
    all_query.sort(key=lambda f: f.rel_path)

    has_repo = any(f.role == "data_access" for f in all_query)
    pattern = "Manager / Repository" if has_repo else "Direct DB access"

    model_files = {m.file for m in proj.models}
    cochange_with_models = []
    for f in all_query:
        partners = proj.git_cochange.get(f.rel_path, [])
        model_partners = [p for p in partners if p in model_files]
        if model_partners:
            cochange_with_models.append({"file": f.rel_path, "cochanges": model_partners})

    return {
        "pattern": pattern,
        "files": [
            build_query_entry(f, proj.files, proj.git_cochange)
            for f in all_query[:25]
        ],
        "cochange_with_models": cochange_with_models[:10],
    }


def build_ui_map(proj: ProjectSummary) -> dict:
    ui_techs = [t for t in proj.stack if t in (
        "React", "Vue", "Angular", "Svelte", "Solid", "Next.js", "Nuxt.js", "Gatsby"
    )]
    template_techs = [t for t in proj.stack if t in ("Jinja2", "Handlebars", "Nunjucks")]

    ui_files = [f for f in proj.files if f.role in ("template", "component")]

    by_folder: dict[str, list[str]] = defaultdict(list)
    for f in ui_files:
        folder = str(Path(f.rel_path).parent)
        by_folder[folder].append(Path(f.rel_path).name)

    route_files = [
        f.rel_path for f in proj.files
        if f.role == "controller" and f.language in ("python", "typescript", "javascript")
    ]

    static_dir = next(
        (k for k in proj.folder_structure if k in ("static", "public", "assets")), None
    )

    return {
        "framework": ui_techs[0] if ui_techs else None,
        "template_engine": template_techs[0] if template_techs else None,
        "views": {folder: sorted(files)[:12] for folder, files in sorted(by_folder.items())},
        "routers": route_files[:15],
        "static": static_dir,
    }


# ─── Validación de calidad del análisis ───────────────────────────────────────

def detect_dependency_cycles(deps: dict) -> list[list[str]]:
    """Acepta tanto el grafo forward plano como el objeto {forward, reverse}."""
    if isinstance(deps, dict) and "forward" in deps:
        deps = deps["forward"]
    """Detecta ciclos en el grafo de dependencias mediante DFS."""
    visited: set[str] = set()
    in_stack: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        in_stack.add(node)
        for neighbor in deps.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path + [neighbor])
            elif neighbor in in_stack and len(cycles) < 5:
                try:
                    idx = path.index(neighbor)
                    cycles.append(path[idx:] + [neighbor])
                except ValueError:
                    cycles.append([neighbor])
        in_stack.discard(node)

    for node in list(deps.keys()):
        if node not in visited:
            dfs(node, [node])

    return cycles


def validate_maps(proj: ProjectSummary, project_map: dict) -> list[dict]:
    """
    Valida coherencia del análisis. Retorna lista de issues con tipo, path y descripción.
    """
    issues: list[dict] = []

    # 1. Archivos referenciados en modules que no existen en disco
    for role, module_list in project_map.get("modules", {}).items():
        for module in module_list:
            fpath = proj.root / module["path"]
            if not fpath.exists():
                issues.append({
                    "type": "missing_file",
                    "path": module["path"],
                    "detail": f"En modules.{role} pero no existe en disco",
                })

    # 2. Módulos sin símbolos en archivos de código no triviales (> 500 bytes)
    for fi in proj.files:
        if (fi.role not in ("other", "test", "template", "migration", "config")
                and fi.language in ("python", "typescript", "javascript")
                and not fi.functions and not fi.classes
                and fi.size > 500):
            issues.append({
                "type": "empty_module",
                "path": fi.rel_path,
                "detail": f"Archivo de {fi.size} bytes sin funciones ni clases detectadas",
            })

    # 3. Ciclos de dependencia
    dep_graph = project_map.get("dependencies", {})
    forward_graph = dep_graph.get("forward", dep_graph) if isinstance(dep_graph, dict) else {}
    cycles = detect_dependency_cycles(forward_graph)
    for cycle in cycles:
        issues.append({
            "type": "dependency_cycle",
            "path": cycle[0],
            "detail": f"Ciclo: {' → '.join(cycle)}",
        })

    # 4. Archivos con imports internos que no resolvieron a ningún archivo conocido
    # Usa el grafo forward: archivos con imports pero sin ninguna resolución exitosa
    resolved_sources = set(forward_graph.keys())
    for fi in proj.files:
        if fi.imports_internal and fi.rel_path not in resolved_sources:
            # Al menos un import no pudo resolverse
            unresolved = [
                imp for imp in fi.imports_internal
                if len(imp.strip().lstrip("./").replace(".", "/").split("/")[-1]) > 3
            ]
            if unresolved:
                issues.append({
                    "type": "broken_import",
                    "path": fi.rel_path,
                    "detail": f"Ningún import interno resolvió: {unresolved[:3]}",
                })

    # Deduplica broken_import (mismo archivo puede tener muchos)
    seen_broken: set[str] = set()
    deduped: list[dict] = []
    for issue in issues:
        key = f"{issue['type']}:{issue['path']}"
        if key not in seen_broken:
            seen_broken.add(key)
            deduped.append(issue)

    return deduped


# ─── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Genera MAP.json para el plugin de Claude.")
    p.add_argument("--root", default=None,
                   help="Raíz del repositorio a analizar (default: directorio que contiene .claude/)")
    p.add_argument("--maps", default="project,db,query,ui",
                   help="MAPs a generar, coma-separados. Opciones: project,db,query,ui")
    p.add_argument("--force", action="store_true",
                   help="Omitir verificación de aprobación")
    return p.parse_args()


def write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    check_approval(args.force)

    root = Path(args.root).resolve() if args.root else PLUGIN_DIR.parent
    maps_to_gen = {m.strip().lower() for m in args.maps.split(",")}

    print(f"Analizando repositorio: {root}")

    print("  Detectando stack...")
    stack = detect_stack(root)

    print("  Construyendo modelo del proyecto...")
    proj = build_project(root, stack)

    print(f"  Proyecto:        {proj.name}")
    print(f"  Lenguajes:       {', '.join(proj.languages)}")
    print(f"  Archivos fuente: {len(proj.files)}")
    print(f"  Modelos ORM:     {len(proj.models)}")
    print(f"  Stack:           {len(proj.stack)} paquetes relevantes")

    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    project_map_data: Optional[dict] = None
    if "project" in maps_to_gen:
        path = MAPS_DIR / "PROJECT_MAP.json"
        project_map_data = build_project_map(proj)
        write_json(path, project_map_data)
        written.append("PROJECT_MAP.json")
        print(f"  ✓ {path.relative_to(PLUGIN_DIR.parent)}")

    if "db" in maps_to_gen:
        path = MAPS_DIR / "DB_MAP.json"
        write_json(path, build_db_map(proj))
        written.append("DB_MAP.json")
        print(f"  ✓ {path.relative_to(PLUGIN_DIR.parent)}")

    if "query" in maps_to_gen:
        path = MAPS_DIR / "QUERY_MAP.json"
        write_json(path, build_query_map(proj))
        written.append("QUERY_MAP.json")
        print(f"  ✓ {path.relative_to(PLUGIN_DIR.parent)}")

    if "ui" in maps_to_gen:
        path = MAPS_DIR / "UI_MAP.json"
        write_json(path, build_ui_map(proj))
        written.append("UI_MAP.json")
        print(f"  ✓ {path.relative_to(PLUGIN_DIR.parent)}")

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

    # Validación de calidad
    if project_map_data:
        print()
        print("  Validando coherencia del análisis...")
        issues = validate_maps(proj, project_map_data)
        if issues:
            print(f"  ⚠ {len(issues)} issue(s) detectados:")
            for iss in issues[:10]:
                print(f"    [{iss['type']}] {iss['path']}: {iss['detail']}")
            if len(issues) > 10:
                print(f"    ... y {len(issues) - 10} más.")
        else:
            print("  ✓ Análisis coherente — sin issues detectados.")

    print()
    print(f"MAPs generados: {', '.join(written)}")
    print("Próximo paso: reinicia el ciclo del reader.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
