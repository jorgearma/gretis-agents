#!/usr/bin/env python3
"""
analyzers/project.py — Genera PROJECT_MAP.json como routing index.

El MAP resultante tiene `domains` con trigger_keywords para routing dinámico
en reader.md. No incluye `modules` archivo por archivo.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from analyzers.core import (
    FileInfo, detect_stack, git_hotspots, git_cochange,
    walk_repo, detect_project_name, detect_readme_summary,
    infer_architecture, scan_structure,
    build_module_entry, detect_problems,
)

# Dominios fijos — siempre se incluyen todos en el PROJECT_MAP.
# El reader usa trigger_keywords para decidir cuáles activar por petición.
DOMAIN_KEYWORDS: dict[str, dict] = {
    "db": {
        "map": "DB_MAP.json",
        "reader": "db-reader",
        "trigger_keywords": [
            "modelo", "tabla", "migración", "campo", "relación",
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
    raise ValueError(f"No summary handler for domain: {domain}")


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera PROJECT_MAP.json como routing index. Escribe en .claude/maps/. Devuelve el dict."""
    name, description = detect_project_name(root)
    if not description:
        description = detect_readme_summary(root)

    folder_structure = scan_structure(root)

    class _MinProj:
        def __init__(self):
            self.folder_structure = folder_structure
            self.stack = stack

    architecture = infer_architecture(_MinProj())

    entry_points = [f.rel_path for f in files if f.role == "entry_point"]

    lang_counts = Counter(f.language for f in files if f.language not in ("html", "sql", "other"))
    languages = [lang for lang, _ in lang_counts.most_common()]

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

    domains: dict[str, dict] = {}
    for domain_name, meta in DOMAIN_KEYWORDS.items():
        domains[domain_name] = {
            "map": meta["map"],
            "reader": meta["reader"],
            "summary": _build_domain_summary(domain_name, root),
            "trigger_keywords": meta["trigger_keywords"],
        }

    # Build modules dict grouped by role
    from collections import defaultdict
    modules: dict[str, list] = defaultdict(list)
    for fi in files:
        if fi.role in ("entry_point", "other", None):
            continue
        entry = build_module_entry(fi, files, cochange_raw)
        modules[fi.role].append(entry)

    problems = detect_problems(files)

    result = {
        "name": name,
        "description": description,
        "languages": languages,
        "architecture": architecture,
        "stack": stack,
        "entry_points": entry_points,
        "domains": domains,
        "modules": dict(modules),
        "problems": problems,
        "cochange": cochange,
        "hotspots": hotspots,
    }

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
    args = p.parse_args()

    if args.root:
        repo_root = Path(args.root).resolve()
    else:
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
