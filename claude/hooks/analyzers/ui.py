#!/usr/bin/env python3
"""analyzers/ui.py — Genera UI_MAP.json."""
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path
from analyzers.core import FileInfo, detect_stack, walk_repo, scan_structure

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

    folder_structure = scan_structure(root)
    static_dir = next(
        (k for k in folder_structure if k in ("static", "public", "assets")), None
    )

    result = {
        "framework": ui_techs[0] if ui_techs else None,
        "template_engine": template_techs[0] if template_techs else None,
        "views": {folder: sorted(flist)[:12] for folder, flist in sorted(by_folder.items())},
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
