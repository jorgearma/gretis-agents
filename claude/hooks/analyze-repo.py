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

# Importaciones de analyzers (después de sys.path)
from analyzers import core
from analyzers.project     import run as run_project
from analyzers.db          import run as run_db
from analyzers.query       import run as run_query
from analyzers.ui          import run as run_ui
from analyzers.api         import run as run_api
from analyzers.services    import run as run_services
from analyzers.jobs        import run as run_jobs
from analyzers.dependency  import run as run_dependency

ANALYZER_MAP = {
    "project":    run_project,
    "db":         run_db,
    "query":      run_query,
    "ui":         run_ui,
    "api":        run_api,
    "services":   run_services,
    "jobs":       run_jobs,
    "dependency": run_dependency,
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
    p.add_argument("--maps", default="project,db,query,ui,api,services,jobs,dependency",
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

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    for map_name in ["project", "db", "query", "ui", "api", "services", "jobs", "dependency"]:
        if map_name not in maps_to_gen:
            continue
        print(f"  Generando {map_name.upper()}_MAP.json...")
        ANALYZER_MAP[map_name](root, files, stack)
        print(f"  OK {map_name.upper()}_MAP.json")

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
