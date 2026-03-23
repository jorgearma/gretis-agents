#!/usr/bin/env python3
"""Hook simple de pre-commit para verificar la estructura minima del plugin de Claude."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PATHS = [
    ROOT / "CLAUDE.md",
    ROOT / ".claude" / "plugin.json",
    ROOT / ".claude" / "agents" / "readers" / "reader.md",
    ROOT / ".claude" / "agents" / "readers" / "project-reader.md",
    ROOT / ".claude" / "agents" / "readers" / "db-reader.md",
    ROOT / ".claude" / "agents" / "readers" / "query-reader.md",
    ROOT / ".claude" / "agents" / "readers" / "ui-reader.md",
    ROOT / ".claude" / "agents" / "orchestrator.md",
    ROOT / ".claude" / "agents" / "planner.md",
    ROOT / ".claude" / "agents" / "writer.md",
    ROOT / ".claude" / "agents" / "frontend.md",
    ROOT / ".claude" / "agents" / "backend.md",
    ROOT / ".claude" / "agents" / "reviewer.md",
    ROOT / ".claude" / "maps" / "PROJECT_MAP.md",
    ROOT / ".claude" / "maps" / "DB_MAP.md",
    ROOT / ".claude" / "maps" / "QUERY_MAP.md",
    ROOT / ".claude" / "maps" / "UI_MAP.md",
    ROOT / ".claude" / "schemas" / "reader-context.json",
    ROOT / ".claude" / "schemas" / "plan.json",
    ROOT / ".claude" / "schemas" / "execution-brief.json",
    ROOT / ".claude" / "schemas" / "execution-dispatch.json",
    ROOT / ".claude" / "schemas" / "operator-approval.json",
    ROOT / ".claude" / "schemas" / "result.json",
    ROOT / ".claude" / "schemas" / "review.json",
    ROOT / ".claude" / "runtime" / "execution-brief.md",
    ROOT / ".claude" / "runtime" / "plan.json",
    ROOT / ".claude" / "runtime" / "execution-dispatch.json",
    ROOT / ".claude" / "runtime" / "operator-approval.json",
    ROOT / ".claude" / "hooks" / "approve-plan.py",
    ROOT / ".claude" / "hooks" / "execute-plan.py",
    ROOT / ".claude" / "commands" / "implement-feature.md",
    ROOT / ".claude" / "commands" / "review-change.md",
]


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_PATHS if not path.exists()]
    if missing:
        print("Missing required Claude plugin files:")
        for path in missing:
            print(f"- {path}")
        return 1

    print("Claude plugin structure ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
