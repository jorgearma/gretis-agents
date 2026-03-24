#!/usr/bin/env python3
"""Hook simple de pre-commit para verificar la estructura minima del plugin de Claude."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]

# These files must always exist (versioned)
REQUIRED_PATHS = [
    ROOT / "CLAUDE.md",
    ROOT / "claude" / "plugin.json",
    ROOT / "claude" / "agents" / "readers" / "reader.md",
    ROOT / "claude" / "agents" / "readers" / "project-reader.md",
    ROOT / "claude" / "agents" / "readers" / "db-reader.md",
    ROOT / "claude" / "agents" / "readers" / "query-reader.md",
    ROOT / "claude" / "agents" / "readers" / "ui-reader.md",
    ROOT / "claude" / "agents" / "planner.md",
    ROOT / "claude" / "agents" / "writer.md",
    ROOT / "claude" / "agents" / "frontend.md",
    ROOT / "claude" / "agents" / "backend.md",
    ROOT / "claude" / "agents" / "reviewer.md",
    ROOT / "claude" / "maps" / "PROJECT_MAP.md",
    ROOT / "claude" / "maps" / "DB_MAP.md",
    ROOT / "claude" / "maps" / "QUERY_MAP.md",
    ROOT / "claude" / "maps" / "UI_MAP.md",
    ROOT / "claude" / "schemas" / "reader-context.json",
    ROOT / "claude" / "schemas" / "plan.json",
    ROOT / "claude" / "schemas" / "execution-brief.json",
    ROOT / "claude" / "schemas" / "execution-dispatch.json",
    ROOT / "claude" / "schemas" / "operator-approval.json",
    ROOT / "claude" / "schemas" / "result.json",
    ROOT / "claude" / "schemas" / "review.json",
    ROOT / "claude" / "runtime" / "operator-approval.json",
    ROOT / "claude" / "hooks" / "approve-plan.py",
    ROOT / "claude" / "hooks" / "execute-plan.py",
    ROOT / "claude" / "hooks" / "dispatch-reviewer.py",
    ROOT / "claude" / "hooks" / "recover-cycle.py",
    ROOT / "claude" / "schemas" / "reviewer-dispatch.json",
    ROOT / "claude" / "commands" / "start-cycle.md",
    ROOT / "claude" / "commands" / "implement-feature.md",
    ROOT / "claude" / "commands" / "review-change.md",
]

# Runtime JSON files that exist only after a cycle runs (gitignored — check only if present)
RUNTIME_JSON_FILES = [
    ROOT / "claude" / "runtime" / "execution-brief.json",
    ROOT / "claude" / "runtime" / "plan.json",
    ROOT / "claude" / "runtime" / "execution-dispatch.json",
    ROOT / "claude" / "runtime" / "reviewer-dispatch.json",
    ROOT / "claude" / "runtime" / "result.json",
]

JSON_FILES = [
    ROOT / "claude" / "plugin.json",
    ROOT / "claude" / "schemas" / "reader-context.json",
    ROOT / "claude" / "schemas" / "plan.json",
    ROOT / "claude" / "schemas" / "execution-brief.json",
    ROOT / "claude" / "schemas" / "execution-dispatch.json",
    ROOT / "claude" / "schemas" / "operator-approval.json",
    ROOT / "claude" / "schemas" / "result.json",
    ROOT / "claude" / "schemas" / "review.json",
    ROOT / "claude" / "schemas" / "reviewer-dispatch.json",
    ROOT / "claude" / "runtime" / "operator-approval.json",
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
