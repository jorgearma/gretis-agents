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
from analyzers.core import FileInfo, detect_stack, walk_repo

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


def _is_webhook(route: str, func_name: str) -> bool:
    return (
        "webhook" in route.lower()
        or "callback" in route.lower()
        or "webhook" in func_name.lower()
        or "callback" in func_name.lower()
    )


def _analyze_flask_file_regex(source: str, rel: str, bp_vars: dict) -> dict:
    """Fallback regex para archivos con SyntaxError."""
    for m in RE_ROUTE.finditer(source):
        bp_var = m.group(1)
        route_path = m.group(2)
        methods_raw = m.group(3) or '"GET"'
        methods = RE_METHODS.findall(methods_raw)
        pos = m.end()
        rest = source[pos:]
        fn_match = re.search(r'def\s+(\w+)\s*\(', rest[:200])
        if not fn_match:
            continue
        func_name = fn_match.group(1)
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


def _analyze_flask_file(path: Path, root: Path) -> dict | None:
    """Analiza un archivo Python buscando blueprints Flask y sus rutas."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if "Blueprint" not in source and ".route" not in source:
        return None

    rel = str(path.relative_to(root))
    bp_vars: dict[str, dict] = {}

    # Detectar blueprints definidos en este archivo
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
        return _analyze_flask_file_regex(source, rel, bp_vars)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        func_name = node.name
        route_info = None
        auth_req = False

        for dec in node.decorator_list:
            try:
                dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else ""
            except Exception:
                dec_str = ""

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
                    # dec_str is like "bp.route('/path', methods=['GET'])"
                    # extract the variable name before ".route("
                    before_route = dec_str.split(".route(")[0]
                    parts = before_route.split(".")
                    bp_var = parts[-1] if parts else list(bp_vars.keys())[0]
                    # fallback to first bp_var if not found in known blueprints
                    if bp_var not in bp_vars:
                        bp_var = list(bp_vars.keys())[0]
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
            target_bp = bp_vars.get(bp_var) or list(bp_vars.values())[0]
            target_bp["endpoints"].append(endpoint)

    return bp_vars


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera API_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""
    framework = next(
        (FRAMEWORK_KEYS[k] for k in FRAMEWORK_KEYS if k in stack),
        None
    )

    middleware_files = [
        f.rel_path for f in files
        if f.role == "middleware" or any(
            kw in f.rel_path.lower()
            for kw in ("auth", "middleware", "decorator", "guard")
        )
    ]

    blueprints_result = []
    webhooks_result = []

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
