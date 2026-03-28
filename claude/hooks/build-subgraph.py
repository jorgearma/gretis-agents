#!/usr/bin/env python3
"""
build-subgraph.py — Pre-loader: enriquece reader-context.json con el subgrafo real de dependencias.

Corre entre el reader y el planner. Lee:
  - .claude/runtime/reader-context.json    (seeds: files_to_open)
  - .claude/maps/DEPENDENCY_MAP.json       (grafo resuelto de imports reales)

Escribe de vuelta en reader-context.json:
  - dependency_graph: subgrafo BFS desde los seeds (forward depth-2, reverse depth-1)
  - files_to_review: expandido con nodos descubiertos que aún no estaban listados

El planner recibe así el contexto exacto: qué usan los seeds y quién los consume,
sin leer el repositorio completo y sin que el reader LLM infiera conexiones.
"""

from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
RUNTIME    = PLUGIN_DIR / "runtime"
MAPS_DIR   = PLUGIN_DIR / "maps"

READER_CONTEXT_PATH = RUNTIME / "reader-context.json"
DEPENDENCY_MAP_PATH = MAPS_DIR / "DEPENDENCY_MAP.json"

# BFS forward depth-2: seeds → sus imports → imports de esos imports
# BFS reverse depth-1: quién importa directamente a los seeds (callers inmediatos)
FORWARD_DEPTH = 2
REVERSE_DEPTH = 1

# Roles que se excluyen de files_to_review (mucho ruido, poco valor)
_SKIP_ROLES = frozenset({"test", "migration", "config", "other"})


def bfs(graph: dict[str, list[str]], seeds: set[str], depth: int) -> dict[str, list[str]]:
    """
    BFS en el grafo hasta `depth` saltos desde los seeds.
    Retorna el subgrafo {src: [vecinos]} con solo las aristas recorridas.
    """
    subgraph: dict[str, list[str]] = {}
    visited: set[str] = set(seeds)
    queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)

    while queue:
        node, level = queue.popleft()
        neighbors = graph.get(node, [])
        if neighbors:
            subgraph[node] = neighbors
        if level < depth:
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, level + 1))

    return subgraph


def main() -> int:
    # ── Cargar reader-context ──────────────────────────────────────────────────
    if not READER_CONTEXT_PATH.exists():
        print("build-subgraph: reader-context.json no encontrado, omitiendo.", file=sys.stderr)
        return 0

    try:
        ctx = json.loads(READER_CONTEXT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"build-subgraph: error leyendo reader-context.json: {e}", file=sys.stderr)
        return 1

    # ── Cargar DEPENDENCY_MAP ──────────────────────────────────────────────────
    if not DEPENDENCY_MAP_PATH.exists():
        print("build-subgraph: DEPENDENCY_MAP.json no encontrado — omitiendo.", file=sys.stderr)
        return 0

    try:
        dep_map = json.loads(DEPENDENCY_MAP_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"build-subgraph: error leyendo DEPENDENCY_MAP.json: {e}", file=sys.stderr)
        return 1

    forward: dict[str, list[str]] = dep_map.get("forward", {})
    reverse: dict[str, list[str]] = dep_map.get("reverse", {})
    nodes:   dict[str, dict]      = dep_map.get("nodes", {})

    # ── Seeds desde files_to_open ──────────────────────────────────────────────
    seeds = {item["path"] for item in ctx.get("files_to_open", []) if "path" in item}
    if not seeds:
        print("build-subgraph: no hay seeds en files_to_open, omitiendo.", file=sys.stderr)
        return 0

    # ── BFS ────────────────────────────────────────────────────────────────────
    fwd_subgraph = bfs(forward, seeds, FORWARD_DEPTH)   # qué usan los seeds
    rev_subgraph = bfs(reverse, seeds, REVERSE_DEPTH)   # quién los consume

    # ── Construir dependency_graph (forward) ───────────────────────────────────
    # Formato del schema: A → [B,C] significa "A importa/usa B y C"
    dependency_graph: dict[str, list[str]] = {}

    # Aristas forward directas y de nivel-2
    for src, deps in fwd_subgraph.items():
        dependency_graph[src] = deps

    # Callers de los seeds: caller → seed (el caller depende del seed)
    for seed, callers in rev_subgraph.items():
        for caller in callers:
            existing = dependency_graph.setdefault(caller, [])
            if seed not in existing:
                existing.append(seed)

    # ── Descubrir nodos nuevos para files_to_review ────────────────────────────
    already_listed = (
        {item["path"] for item in ctx.get("files_to_open", [])} |
        {item["path"] for item in ctx.get("files_to_review", [])}
    )

    all_connected: set[str] = set()
    for deps in fwd_subgraph.values():
        all_connected.update(deps)
    for callers in rev_subgraph.values():
        all_connected.update(callers)

    new_entries: list[dict] = []
    for path in sorted(all_connected - seeds - already_listed):
        node_meta = nodes.get(path, {})
        role      = node_meta.get("role", "other")
        if role in _SKIP_ROLES:
            continue

        symbols     = node_meta.get("symbols", [])
        top_symbols = [s["name"] for s in symbols[:3] if "name" in s]

        entry: dict = {
            "path": path,
            "hint": f"Descubierto via grafo de dependencias (role: {role})",
            "test_file": None,
        }
        if top_symbols:
            entry["key_symbols"] = top_symbols
        new_entries.append(entry)

    # ── Escribir reader-context.json enriquecido ───────────────────────────────
    ctx["dependency_graph"] = dependency_graph
    if new_entries:
        ctx.setdefault("files_to_review", [])
        ctx["files_to_review"].extend(new_entries)

    READER_CONTEXT_PATH.write_text(
        json.dumps(ctx, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # ── Reporte ────────────────────────────────────────────────────────────────
    n_edges = sum(len(v) for v in dependency_graph.values())
    print(f"  Subgrafo: {len(dependency_graph)} nodos, {n_edges} aristas "
          f"(fwd-depth={FORWARD_DEPTH}, rev-depth={REVERSE_DEPTH})")
    if new_entries:
        print(f"  Nodos nuevos en files_to_review: {len(new_entries)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
