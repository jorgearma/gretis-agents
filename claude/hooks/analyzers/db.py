#!/usr/bin/env python3
"""analyzers/db.py — Genera DB_MAP.json."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from analyzers.core import (
    FileInfo, ModelInfo, detect_stack, walk_repo,
    _walk_repo_models_cache,
)

DB_ORMS = {
    "SQLAlchemy", "Django ORM", "TypeORM", "Prisma", "Mongoose",
    "Sequelize", "Drizzle", "Peewee", "Tortoise ORM", "MongoEngine", "PyMongo", "Knex",
}
DB_INFRA = ("SQL", "Postgres", "MySQL", "Mongo", "Redis", "SQLite", "Dynamo")


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    models: list[ModelInfo] = list(_walk_repo_models_cache)
    db_techs = [t for t in stack if t in DB_ORMS]
    db_infra = [t for t in stack if any(k in t for k in DB_INFRA)]
    migrations = [f.rel_path for f in files if f.role == "migration"]
    seeds = [m for m in migrations if "seed" in m.lower()]
    pure_migrations = [m for m in migrations if "seed" not in m.lower()]
    db_conn = [f.rel_path for f in files if f.role == "db_connection"]

    real_models = [
        m for m in models
        if any(k in m.file for k in ("model", "entit", "domain", "schema.prisma"))
        or m.file in ("models.py", "model.py")
        or (m.fields and len(m.fields) >= 2)
    ]

    result = {
        "orm": db_techs[0] if db_techs else None,
        "database": db_infra[0] if db_infra else None,
        "connection_files": db_conn,
        "models": [
            {"name": m.name, "table": m.table, "file": m.file,
             "fields": m.fields, "relationships": m.relationships}
            for m in sorted(real_models, key=lambda x: x.name)
        ],
        "migrations": pure_migrations,
        "seeds": seeds,
    }
    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "DB_MAP.json").write_text(
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
    print("DB_MAP.json generado.")
