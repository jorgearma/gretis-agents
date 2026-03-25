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

# These files must always exist (versioned)
REQUIRED_PATHS = [
    ROOT / "CLAUDE.md",
    PLUGIN_DIR / "plugin.json",
    PLUGIN_DIR / "agents" / "readers" / "reader.md",
    PLUGIN_DIR / "agents" / "readers" / "project-reader.md",
    PLUGIN_DIR / "agents" / "readers" / "db-reader.md",
    PLUGIN_DIR / "agents" / "readers" / "query-reader.md",
    PLUGIN_DIR / "agents" / "readers" / "ui-reader.md",
    PLUGIN_DIR / "agents" / "planner.md",
    PLUGIN_DIR / "agents" / "writer.md",
    PLUGIN_DIR / "agents" / "frontend.md",
    PLUGIN_DIR / "agents" / "backend.md",
    PLUGIN_DIR / "agents" / "reviewer.md",
    PLUGIN_DIR / "maps" / "PROJECT_MAP.json",
    PLUGIN_DIR / "maps" / "DB_MAP.json",
    PLUGIN_DIR / "maps" / "QUERY_MAP.json",
    PLUGIN_DIR / "maps" / "UI_MAP.json",
    PLUGIN_DIR / "schemas" / "reader-context.json",
    PLUGIN_DIR / "schemas" / "plan.json",
    PLUGIN_DIR / "schemas" / "execution-brief.json",
    PLUGIN_DIR / "schemas" / "execution-dispatch.json",
    PLUGIN_DIR / "schemas" / "operator-approval.json",
    PLUGIN_DIR / "schemas" / "result.json",
    PLUGIN_DIR / "schemas" / "review.json",
    PLUGIN_DIR / "schemas" / "reviewer-dispatch.json",
    PLUGIN_DIR / "runtime" / "operator-approval.json",
    PLUGIN_DIR / "runtime" / "map-scan-approval.json",
    PLUGIN_DIR / "agents" / "map-scanner.md",
    PLUGIN_DIR / "hooks" / "approve-plan.py",
    PLUGIN_DIR / "hooks" / "approve-map-scan.py",
    PLUGIN_DIR / "hooks" / "analyze-repo.py",
    PLUGIN_DIR / "hooks" / "execute-plan.py",
    PLUGIN_DIR / "hooks" / "dispatch-reviewer.py",
    PLUGIN_DIR / "hooks" / "recover-cycle.py",
    PLUGIN_DIR / "commands" / "start-cycle.md",
    PLUGIN_DIR / "commands" / "implement-feature.md",
    PLUGIN_DIR / "commands" / "review-change.md",
    PLUGIN_DIR / "maps" / "API_MAP.json",
    PLUGIN_DIR / "maps" / "SERVICES_MAP.json",
    PLUGIN_DIR / "maps" / "JOBS_MAP.json",
    PLUGIN_DIR / "agents" / "readers" / "api-reader.md",
    PLUGIN_DIR / "agents" / "readers" / "services-reader.md",
    PLUGIN_DIR / "agents" / "readers" / "jobs-reader.md",
    PLUGIN_DIR / "schemas" / "api-map.json",
    PLUGIN_DIR / "schemas" / "services-map.json",
    PLUGIN_DIR / "schemas" / "jobs-map.json",
]

# Runtime JSON files that exist only after a cycle runs (gitignored — check only if present)
RUNTIME_JSON_FILES = [
    PLUGIN_DIR / "runtime" / "execution-brief.json",
    PLUGIN_DIR / "runtime" / "plan.json",
    PLUGIN_DIR / "runtime" / "execution-dispatch.json",
    PLUGIN_DIR / "runtime" / "reviewer-dispatch.json",
    PLUGIN_DIR / "runtime" / "result.json",
]

JSON_FILES = [
    PLUGIN_DIR / "plugin.json",
    PLUGIN_DIR / "schemas" / "reader-context.json",
    PLUGIN_DIR / "schemas" / "plan.json",
    PLUGIN_DIR / "schemas" / "execution-brief.json",
    PLUGIN_DIR / "schemas" / "execution-dispatch.json",
    PLUGIN_DIR / "schemas" / "operator-approval.json",
    PLUGIN_DIR / "schemas" / "result.json",
    PLUGIN_DIR / "schemas" / "review.json",
    PLUGIN_DIR / "schemas" / "reviewer-dispatch.json",
    PLUGIN_DIR / "schemas" / "project-map.json",
    PLUGIN_DIR / "schemas" / "db-map.json",
    PLUGIN_DIR / "schemas" / "query-map.json",
    PLUGIN_DIR / "schemas" / "ui-map.json",
    PLUGIN_DIR / "runtime" / "operator-approval.json",
    PLUGIN_DIR / "runtime" / "map-scan-approval.json",
    PLUGIN_DIR / "schemas" / "api-map.json",
    PLUGIN_DIR / "schemas" / "services-map.json",
    PLUGIN_DIR / "schemas" / "jobs-map.json",
    PLUGIN_DIR / "maps" / "PROJECT_MAP.json",
    PLUGIN_DIR / "maps" / "DB_MAP.json",
    PLUGIN_DIR / "maps" / "QUERY_MAP.json",
    PLUGIN_DIR / "maps" / "UI_MAP.json",
    PLUGIN_DIR / "maps" / "API_MAP.json",
    PLUGIN_DIR / "maps" / "SERVICES_MAP.json",
    PLUGIN_DIR / "maps" / "JOBS_MAP.json",
]


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
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_PATHS if not path.exists()]
    if missing:
        print("Missing required Claude plugin files:")
        for path in missing:
            print(f"- {path}")
        return 1

    invalid_json = [error for path in JSON_FILES if (error := validate_json_file(path))]
    if invalid_json:
        print("Invalid JSON files detected:")
        for error in invalid_json:
            print(f"- {error}")
        return 1

    # Validar maps/*.json contra sus schemas
    MAP_ARTIFACTS = {
        "PROJECT_MAP.json":  PLUGIN_DIR / "maps" / "PROJECT_MAP.json",
        "DB_MAP.json":       PLUGIN_DIR / "maps" / "DB_MAP.json",
        "QUERY_MAP.json":    PLUGIN_DIR / "maps" / "QUERY_MAP.json",
        "UI_MAP.json":       PLUGIN_DIR / "maps" / "UI_MAP.json",
        "API_MAP.json":      PLUGIN_DIR / "maps" / "API_MAP.json",
        "SERVICES_MAP.json": PLUGIN_DIR / "maps" / "SERVICES_MAP.json",
        "JOBS_MAP.json":     PLUGIN_DIR / "maps" / "JOBS_MAP.json",
    }
    map_schema_errors: list[str] = []
    for artifact_name, map_path in MAP_ARTIFACTS.items():
        try:
            with map_path.open("r", encoding="utf-8") as fh:
                map_data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue  # already detected in invalid_json
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

    # Validate runtime JSON files only if they exist (gitignored, generated at runtime)
    runtime_errors = [
        error
        for path in RUNTIME_JSON_FILES
        if path.exists() and (error := validate_json_file(path))
    ]
    if runtime_errors:
        print("Invalid runtime JSON files detected:")
        for error in runtime_errors:
            print(f"- {error}")
        return 1

    print("Claude plugin structure ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
