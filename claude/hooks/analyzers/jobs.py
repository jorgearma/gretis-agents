#!/usr/bin/env python3
"""
analyzers/jobs.py — Genera JOBS_MAP.json.

Detecta scheduler (Celery, RQ, APScheduler, cron), jobs y queues.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from analyzers.core import FileInfo, detect_stack, walk_repo, find_test_file

RE_CRON = re.compile(r'\d+\s+\d+\s+\*\s+\*\s+\*|\*/\d+|\bcron\b', re.IGNORECASE)
RE_INTERVAL = re.compile(r'every\s+\d+|interval\s*=|countdown\s*=', re.IGNORECASE)
RE_CELERY_TASK = re.compile(r'@\w+\.task|@shared_task|@app\.task')


def _detect_scheduler(files: list[FileInfo], stack: dict) -> str | None:
    for stack_name in stack:
        key = stack_name.lower()
        if "celery" in key:
            return "celery"
        if key == "rq":
            return "rq"
        if "apscheduler" in key:
            return "apscheduler"
    for fi in files:
        for imp in fi.imports_external:
            if imp.lower() == "celery":
                return "celery"
            if imp.lower() == "rq":
                return "rq"
            if imp.lower() == "apscheduler":
                return "apscheduler"
    return None


def _extract_celery_jobs(fi: FileInfo, root: Path) -> list[dict]:
    """Extrae tareas Celery de un archivo."""
    jobs = []
    try:
        source = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return jobs

    if not RE_CELERY_TASK.search(source):
        return jobs

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return jobs

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        is_task = False
        schedule_str = None
        trigger = "manual"

        for dec in node.decorator_list:
            try:
                dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else str(dec)
            except Exception:
                dec_str = ""
            if "task" in dec_str.lower() or "shared_task" in dec_str.lower():
                is_task = True
            if RE_CRON.search(dec_str):
                trigger = "cron"
                schedule_str = dec_str
            elif RE_INTERVAL.search(dec_str):
                trigger = "interval"
                schedule_str = dec_str

        if not is_task:
            continue

        # Docstring as description
        desc = ""
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)):
            desc = str(node.body[0].value.value).strip().split(".")[0][:100]

        jobs.append({
            "file": fi.rel_path,
            "function": node.name,
            "trigger": trigger,
            "schedule": schedule_str,
            "description": desc,
        })

    return jobs


def _extract_manual_jobs(fi: FileInfo, root: Path) -> list[dict]:
    """Scripts manuales de jobs (carpeta jobs/ o nombre con 'job'). Excluye scripts/."""
    parts = Path(fi.rel_path).parts
    # Archivos en scripts/ son utilidades del día a día, no jobs del sistema
    if any(p.lower() == "scripts" for p in parts[:-1]):
        return []
    if "job" not in fi.rel_path.lower():
        return []
    if "main" not in fi.functions and "run" not in fi.functions:
        return []

    fn_name = "main" if "main" in fi.functions else "run"
    desc = fi.docstring[:100] if fi.docstring else f"Script manual en {fi.rel_path}"

    return [{
        "file": fi.rel_path,
        "function": fn_name,
        "trigger": "manual",
        "schedule": None,
        "description": desc,
    }]


def _extract_rq_jobs(fi: FileInfo, root: Path) -> list[dict]:
    """Extrae jobs RQ de un archivo (decorator @job o q.enqueue)."""
    jobs = []
    try:
        source = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return jobs

    if "@job" not in source and "q.enqueue" not in source and "enqueue" not in source:
        return jobs

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return jobs

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_job = any(
            "job" in (ast.unparse(dec) if hasattr(ast, "unparse") else "").lower()
            for dec in node.decorator_list
        )
        if not is_job:
            continue
        desc = ""
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)):
            desc = str(node.body[0].value.value).strip().split(".")[0][:100]
        jobs.append({
            "file": fi.rel_path,
            "function": node.name,
            "trigger": "manual",
            "schedule": None,
            "description": desc,
        })
    return jobs


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera JOBS_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""
    scheduler = _detect_scheduler(files, stack)

    jobs: list[dict] = []
    queues: list[str] = []  # populated only if explicit queue names found in task decorators

    if scheduler == "celery":
        for fi in files:
            jobs.extend(_extract_celery_jobs(fi, root))
    elif scheduler == "rq":
        for fi in files:
            if fi.language == "python":
                jobs.extend(_extract_rq_jobs(fi, root))

    # Manual scripts in all cases
    for fi in files:
        if fi.language == "python":
            jobs.extend(_extract_manual_jobs(fi, root))

    # Deduplicate by (file, function)
    seen: set[tuple[str, str]] = set()
    unique_jobs: list[dict] = []
    for j in jobs:
        key = (j["file"], j["function"])
        if key not in seen:
            seen.add(key)
            unique_jobs.append(j)

    # Add test_file to each job
    for job in unique_jobs:
        job["test_file"] = find_test_file(job["file"], files)

    if not scheduler and not unique_jobs:
        result: dict = {"scheduler": None, "jobs": [], "queues": []}
    else:
        result = {
            "scheduler": scheduler,
            "jobs": unique_jobs,
            "queues": queues,
        }

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "JOBS_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera JOBS_MAP.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd()
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("JOBS_MAP.json generado.")
