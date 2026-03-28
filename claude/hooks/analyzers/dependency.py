"""
analyzers/dependency.py — Genera DEPENDENCY_MAP.json con el grafo completo de dependencias.

El grafo tiene tres capas:
  - forward:  {archivo → [archivos que importa]}   (qué usa cada módulo)
  - reverse:  {archivo → [archivos que lo importan]} (quién consume cada módulo)
  - nodes:    {archivo → {role, symbols[{name,line,end_line,kind}]}} (símbolos con rangos)

El reader usa este MAP para hacer BFS desde los archivos semilla y entregar al planner
el subgrafo exacto relevante a la petición, incluyendo puntos de entrada y consumidores.
"""
from __future__ import annotations

import json
from pathlib import Path

from analyzers.core import (
    FileInfo,
    resolve_dependencies,
    detect_dependency_cycles,
)


def _build_node(fi: FileInfo) -> dict:
    """Construye el nodo enriquecido para un archivo: role + símbolos con rangos de línea."""
    fn_info_map = {fn.name: fn for fn in fi.function_infos}
    symbols = []
    for name, line in sorted(fi.symbols_with_lines.items(), key=lambda x: x[1]):
        kind = "class" if name in fi.classes else "function"
        entry: dict = {"name": name, "line": line, "kind": kind}
        if name in fn_info_map:
            entry["end_line"] = fn_info_map[name].end_line
        symbols.append(entry)
    return {
        "role":    fi.role,
        "symbols": symbols[:20],
    }


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera DEPENDENCY_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""

    # ── Grafo bidireccional ────────────────────────────────────────────────────
    graph   = resolve_dependencies(files)
    forward = graph["forward"]   # {src: [dep, ...]}
    reverse = graph["reverse"]   # {dep: [src, ...]}

    # ── Entry points ──────────────────────────────────────────────────────────
    entry_points = [f.rel_path for f in files if f.role == "entry_point"]

    # ── Nodos enriquecidos (solo archivos que participan en el grafo) ──────────
    graph_paths = set(forward.keys()) | set(reverse.keys()) | set(entry_points)
    file_map    = {f.rel_path: f for f in files}

    nodes: dict[str, dict] = {}
    for path in sorted(graph_paths):
        fi = file_map.get(path)
        if fi:
            nodes[path] = _build_node(fi)

    # ── Ciclos de dependencia ─────────────────────────────────────────────────
    raw_cycles = detect_dependency_cycles(forward)
    cycles     = [" → ".join(c) for c in raw_cycles[:10]]

    # ── Stats ─────────────────────────────────────────────────────────────────
    stats = {
        "total_files":     len(files),
        "connected_files": len(graph_paths),
        "edges":           sum(len(v) for v in forward.values()),
        "cycles_found":    len(raw_cycles),
    }

    result = {
        "entry_points": entry_points,
        "forward":      forward,
        "reverse":      reverse,
        "nodes":        nodes,
        "cycles":       cycles,
        "stats":        stats,
    }

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    out_path = maps_dir / "DEPENDENCY_MAP.json"
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result
