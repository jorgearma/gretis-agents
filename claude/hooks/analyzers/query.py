#!/usr/bin/env python3
"""analyzers/query.py — Genera QUERY_MAP.json."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from analyzers.core import (
    FileInfo, detect_stack, walk_repo, git_cochange,
    build_query_entry, _walk_repo_models_cache,
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
