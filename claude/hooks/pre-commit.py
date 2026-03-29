#!/usr/bin/env python3
"""Hook simple de pre-commit para verificar la estructura minima del plugin de Claude."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_artifact


PLUGIN_DIR = Path(__file__).resolve().parents[1]
ROOT = PLUGIN_DIR.parent

# Archivos que siempre deben existir (versionados)
REQUIRED_PATHS = [
    ROOT / "CLAUDE.md",
    PLUGIN_DIR / "plugin.json",
    # Agentes
    PLUGIN_DIR / "agents" / "reader.md",
    PLUGIN_DIR / "agents" / "planner.md",
    PLUGIN_DIR / "agents" / "writer.md",
    PLUGIN_DIR / "agents" / "frontend.md",
    PLUGIN_DIR / "agents" / "backend.md",
    # MAPs generados (deben existir después de analyze-repo.py)
    PLUGIN_DIR / "maps" / "ROUTING_MAP.json",
    PLUGIN_DIR / "maps" / "DOMAIN_INDEX_api.json",
    PLUGIN_DIR / "maps" / "DOMAIN_INDEX_data.json",
    PLUGIN_DIR / "maps" / "CONTRACT_MAP.json",
    PLUGIN_DIR / "maps" / "DEPENDENCY_MAP.json",
    # Schemas de runtime
    PLUGIN_DIR / "schemas" / "reader-context.json",
    PLUGIN_DIR / "schemas" / "plan.json",
    PLUGIN_DIR / "schemas" / "execution-brief.json",
    PLUGIN_DIR / "schemas" / "execution-dispatch.json",
    PLUGIN_DIR / "schemas" / "operator-approval.json",
    PLUGIN_DIR / "schemas" / "result.json",
    # Schemas de maps
    PLUGIN_DIR / "schemas" / "routing-map.json",
    PLUGIN_DIR / "schemas" / "domain-index.json",
    PLUGIN_DIR / "schemas" / "contract-map.json",
    PLUGIN_DIR / "schemas" / "dependency-map.json",
    # Runtime obligatorio
    PLUGIN_DIR / "runtime" / "operator-approval.json",
    PLUGIN_DIR / "runtime" / "map-scan-approval.json",
    # Hooks
    PLUGIN_DIR / "hooks" / "approve-plan.py",
    PLUGIN_DIR / "hooks" / "approve-map-scan.py",
    PLUGIN_DIR / "hooks" / "analyze-repo.py",
    PLUGIN_DIR / "hooks" / "execute-plan.py",
    PLUGIN_DIR / "hooks" / "recover-cycle.py",
    # Comandos
    PLUGIN_DIR / "commands" / "start-cycle.md",
    PLUGIN_DIR / "commands" / "implement-feature.md",
]

# Runtime generado en cada ciclo (gitignored — validar solo si existe)
RUNTIME_JSON_FILES = [
    PLUGIN_DIR / "runtime" / "execution-brief.json",
    PLUGIN_DIR / "runtime" / "plan.json",
    PLUGIN_DIR / "runtime" / "execution-dispatch.json",
    PLUGIN_DIR / "runtime" / "reviewer-dispatch.json",
    PLUGIN_DIR / "runtime" / "result.json",
]

# JSON estáticos que siempre deben ser JSON válido
STATIC_JSON_FILES = [
    PLUGIN_DIR / "plugin.json",
    PLUGIN_DIR / "schemas" / "reader-context.json",
    PLUGIN_DIR / "schemas" / "plan.json",
    PLUGIN_DIR / "schemas" / "execution-brief.json",
    PLUGIN_DIR / "schemas" / "execution-dispatch.json",
    PLUGIN_DIR / "schemas" / "operator-approval.json",
    PLUGIN_DIR / "schemas" / "result.json",
    PLUGIN_DIR / "schemas" / "routing-map.json",
    PLUGIN_DIR / "schemas" / "domain-index.json",
    PLUGIN_DIR / "schemas" / "contract-map.json",
    PLUGIN_DIR / "schemas" / "dependency-map.json",
    PLUGIN_DIR / "runtime" / "operator-approval.json",
    PLUGIN_DIR / "runtime" / "map-scan-approval.json",
]

# Maps que se validan contra su schema (artifact_name → path)
MAP_ARTIFACTS = {
    "ROUTING_MAP.json":           PLUGIN_DIR / "maps" / "ROUTING_MAP.json",
    "DOMAIN_INDEX_api.json":      PLUGIN_DIR / "maps" / "DOMAIN_INDEX_api.json",
    "DOMAIN_INDEX_data.json":     PLUGIN_DIR / "maps" / "DOMAIN_INDEX_data.json",
    "DOMAIN_INDEX_ui.json":       PLUGIN_DIR / "maps" / "DOMAIN_INDEX_ui.json",
    "DOMAIN_INDEX_services.json": PLUGIN_DIR / "maps" / "DOMAIN_INDEX_services.json",
    "DOMAIN_INDEX_jobs.json":     PLUGIN_DIR / "maps" / "DOMAIN_INDEX_jobs.json",
    "CONTRACT_MAP.json":          PLUGIN_DIR / "maps" / "CONTRACT_MAP.json",
    "DEPENDENCY_MAP.json":        PLUGIN_DIR / "maps" / "DEPENDENCY_MAP.json",
}


def validate_json_file(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            json.load(fh)
    except json.JSONDecodeError as exc:
        return f"{path.relative_to(ROOT)}: invalid JSON at line {exc.lineno} column {exc.colno}"
    except OSError as exc:
        return f"{path.relative_to(ROOT)}: cannot be read ({exc})"
    return None


def main() -> int:
    # 1. Archivos requeridos
    missing = [str(p.relative_to(ROOT)) for p in REQUIRED_PATHS if not p.exists()]
    if missing:
        print("Missing required Claude plugin files:")
        for p in missing:
            print(f"  - {p}")
        return 1

    # 2. JSON estático válido
    invalid_json = [err for p in STATIC_JSON_FILES if (err := validate_json_file(p))]
    if invalid_json:
        print("Invalid JSON files detected:")
        for err in invalid_json:
            print(f"  - {err}")
        return 1

    # 3. Maps contra schema
    schema_errors: list[str] = []
    for artifact_name, map_path in MAP_ARTIFACTS.items():
        if not map_path.exists():
            continue  # ya detectado en REQUIRED_PATHS si es obligatorio
        try:
            with map_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue  # ya detectado en invalid_json
        vr = validate_artifact(artifact_name, data)
        if not vr.ok:
            schema_errors.append(
                f"{map_path.relative_to(ROOT)}: schema violations\n{vr.format()}"
            )

    if schema_errors:
        print("Map files with schema violations:")
        for err in schema_errors:
            print(f"  - {err}")
        return 1

    # 4. Runtime JSON (solo si existe)
    runtime_errors = [
        err for p in RUNTIME_JSON_FILES
        if p.exists() and (err := validate_json_file(p))
    ]
    if runtime_errors:
        print("Invalid runtime JSON files detected:")
        for err in runtime_errors:
            print(f"  - {err}")
        return 1

    print("Claude plugin structure ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
