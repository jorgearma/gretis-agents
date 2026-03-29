#!/usr/bin/env python3
"""
analyzers/domain_index.py — Helper compartido para construir DOMAIN_INDEX_<domain>.json.

Todos los dominios emiten la misma estructura candidates[] usando build_candidate().
Eso hace que el reader sea determinista: siempre sabe qué campos esperar.
"""
from __future__ import annotations

import json
from pathlib import Path

from analyzers.core import (
    FileInfo,
    build_symbols,
    extract_keywords,
    find_related,
    find_test_file,
    infer_purpose,
)


def build_candidate(
    fi: FileInfo,
    all_files: list[FileInfo],
    cochange: dict[str, list[str]],
    dep_forward: dict[str, list[str]] | None = None,
    contracts: list[str] | None = None,
    open_priority: str = "review",
    confidence_signals: list[str] | None = None,
) -> dict:
    """
    Construye un candidato uniforme para DOMAIN_INDEX_<domain>.json.

    open_priority:
        "seed"   — archivo primario, el reader debe abrirlo siempre.
        "review" — archivo secundario, abrirlo si el seed apunta a él
                   o si la petición lo menciona explícitamente.

    confidence_signals: indicadores de por qué este archivo es candidato
        (e.g. "has_route_decorators", "is_data_access_role", "has_sdk_import").
    """
    test = find_test_file(fi.rel_path, all_files)
    return {
        "path": fi.rel_path,
        "role": fi.role,
        "purpose": infer_purpose(fi),
        "keywords": extract_keywords(fi),
        "key_symbols": (fi.functions or fi.exports)[:4],
        "symbols": build_symbols(fi),
        "test_files": [test] if test else [],
        "related_paths": find_related(fi, all_files, cochange, dep_forward),
        "contracts": contracts or [],
        "open_priority": open_priority,
        "confidence_signals": confidence_signals or [],
    }


def write_domain_index(root: Path, domain: str, candidates: list[dict]) -> dict:
    """Serializa candidates[] en DOMAIN_INDEX_<domain>.json y devuelve el dict."""
    result: dict = {"domain": domain, "candidates": candidates}
    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / f"DOMAIN_INDEX_{domain}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result
