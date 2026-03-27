#!/usr/bin/env python3
"""
token-usage.py — Cuántos tokens consume cada agente del plugin.

Lee los .jsonl de sesiones de Claude Code para este proyecto e infiere
qué agente ejecutó cada sesión según los archivos de runtime que escribió.

Uso:
    python3 .claude/hooks/token-usage.py
    python3 .claude/hooks/token-usage.py --days 7
    python3 .claude/hooks/token-usage.py --session <uuid-prefix>
    python3 .claude/hooks/token-usage.py --json
    python3 .claude/hooks/token-usage.py --all        # incluye sesiones sin agente identificado
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# ─── Rutas ────────────────────────────────────────────────────────────────────

PLUGIN_DIR   = pathlib.Path(__file__).resolve().parents[1]
PROJECT_ROOT = PLUGIN_DIR.parent
# Claude Code guarda sesiones en ~/.claude/projects/<sanitized-cwd>/
_sanitized   = str(PROJECT_ROOT).replace("/", "-").replace("\\", "-")
SESSION_DIR  = pathlib.Path.home() / ".claude" / "projects" / _sanitized

# ─── Mapeo archivo runtime → agente ───────────────────────────────────────────

# Cada agente es el "owner" canónico del archivo que produce.
# Si una sesión escribe varios de estos archivos, se elige el más específico.
RUNTIME_FILE_TO_AGENT: dict[str, str] = {
    "reader-context.json":   "reader",
    "plan.json":             "planner",
    "execution-brief.json":  "writer",
    "result.json":           "frontend/backend",   # se refina con execution-dispatch
    "review.json":           "reviewer",
    "quick-dispatch.json":   "quick-agent",
    # hooks (no son agentes pero pueden tener tokens si se editan desde sesión)
    "operator-approval.json": "_hook:approve-plan",
    "execution-dispatch.json": "_hook:execute-plan",
    "map-scan-approval.json":  "_hook:approve-map-scan",
    "review.json":             "_archived",
    "reviewer-dispatch.json":  "_archived",
}

# Prioridad cuando hay varios matches en la misma sesión (mayor = más específico)
AGENT_PRIORITY: dict[str, int] = {
    "reader":            10,
    "planner":           10,
    "writer":            10,
    "frontend/backend":  10,
    "reviewer":          10,
    "quick-agent":       10,
    "_hook:approve-plan":   5,
    "_hook:execute-plan":   5,
    "_hook:approve-map-scan": 5,
}


# ─── Precios aproximados (USD por millón de tokens) ───────────────────────────
# Sonnet 4.6 — fuente: anthropic.com/pricing (aproximados)
PRICE_INPUT    = 3.00   # $/MTok input (sin cache)
PRICE_CACHE_W  = 3.75   # $/MTok cache write (ephemeral 5m o 1h)
PRICE_CACHE_R  = 0.30   # $/MTok cache read
PRICE_OUTPUT   = 15.00  # $/MTok output


def usd(tokens: int, price_per_mtok: float) -> float:
    return tokens / 1_000_000 * price_per_mtok


# ─── Parseo de sesiones ────────────────────────────────────────────────────────

class SessionStats:
    __slots__ = (
        "session_id", "agent", "ts_first", "ts_last",
        "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_creation_tokens",
        "n_messages", "runtime_files_written",
    )

    def __init__(self, session_id: str) -> None:
        self.session_id            = session_id
        self.agent                 = "_unknown"
        self.ts_first: str | None  = None
        self.ts_last: str | None   = None
        self.input_tokens          = 0
        self.output_tokens         = 0
        self.cache_read_tokens     = 0
        self.cache_creation_tokens = 0
        self.n_messages            = 0
        self.runtime_files_written: set[str] = set()

    @property
    def total_input(self) -> int:
        """Input real (sin cache) + cache creation + cache read."""
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens

    @property
    def cost_usd(self) -> float:
        return (
            usd(self.input_tokens,          PRICE_INPUT)
            + usd(self.cache_creation_tokens, PRICE_CACHE_W)
            + usd(self.cache_read_tokens,     PRICE_CACHE_R)
            + usd(self.output_tokens,         PRICE_OUTPUT)
        )


def parse_session(jsonl_path: pathlib.Path) -> SessionStats | None:
    session_id = jsonl_path.stem
    stats = SessionStats(session_id)

    try:
        with jsonl_path.open(encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    if not lines:
        return None

    for raw in lines:
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue

        ts = entry.get("timestamp")
        if ts:
            if stats.ts_first is None:
                stats.ts_first = ts
            stats.ts_last = ts

        if entry.get("type") != "assistant":
            continue

        msg = entry.get("message", {})
        usage = msg.get("usage", {})
        if usage:
            stats.n_messages          += 1
            stats.input_tokens        += usage.get("input_tokens", 0)
            stats.output_tokens       += usage.get("output_tokens", 0)
            stats.cache_read_tokens   += usage.get("cache_read_input_tokens", 0)
            # cache_creation puede venir en dos lugares según versión de CC
            stats.cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
            cache_creation = usage.get("cache_creation", {})
            if isinstance(cache_creation, dict):
                for v in cache_creation.values():
                    if isinstance(v, int):
                        stats.cache_creation_tokens += v

        # Detectar archivos de runtime escritos en esta sesión
        for block in msg.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            if block.get("name") not in ("Write", "Edit"):
                continue
            fp = block.get("input", {}).get("file_path", "")
            if fp:
                fname = pathlib.Path(fp).name
                if fname in RUNTIME_FILE_TO_AGENT:
                    stats.runtime_files_written.add(fname)

    # Sin tokens → sesión vacía
    if stats.n_messages == 0:
        return None

    # Inferir agente por los archivos escritos
    if not stats.runtime_files_written:
        stats.agent = "_unknown"
        return stats

    # Contar cuántos archivos aporta cada agente
    agent_file_count: dict[str, int] = defaultdict(int)
    for fname in stats.runtime_files_written:
        agent = RUNTIME_FILE_TO_AGENT[fname]
        agent_file_count[agent] += 1

    real_agents = [a for a in agent_file_count if not a.startswith("_")]

    # Sesión de desarrollo: mezcla archivos de 3+ agentes distintos
    if len(real_agents) >= 3:
        stats.agent = "_dev"
        return stats

    # Elegir el agente con más archivos propios;
    # en empate: mayor prioridad; en empate: nombre lexicográfico (determinista)
    best_agent = max(
        agent_file_count,
        key=lambda a: (agent_file_count[a], AGENT_PRIORITY.get(a, 1), a),
    )
    stats.agent = best_agent
    return stats


def collect_sessions(
    session_dir: pathlib.Path,
    days: int | None = None,
    session_prefix: str | None = None,
) -> list[SessionStats]:
    if not session_dir.exists():
        return []

    cutoff: datetime | None = None
    if days is not None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

    results: list[SessionStats] = []
    for jl in sorted(session_dir.glob("*.jsonl"), key=lambda x: x.stat().st_mtime):
        if session_prefix and not jl.stem.startswith(session_prefix):
            continue
        if cutoff:
            mtime = datetime.fromtimestamp(jl.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                continue
        s = parse_session(jl)
        if s:
            results.append(s)

    return results


# ─── Agregación por agente ─────────────────────────────────────────────────────

class AgentAggregate:
    __slots__ = (
        "agent", "sessions",
        "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_creation_tokens",
        "cost_usd",
    )

    def __init__(self, agent: str) -> None:
        self.agent                 = agent
        self.sessions              = 0
        self.input_tokens          = 0
        self.output_tokens         = 0
        self.cache_read_tokens     = 0
        self.cache_creation_tokens = 0
        self.cost_usd              = 0.0

    def add(self, s: SessionStats) -> None:
        self.sessions              += 1
        self.input_tokens          += s.input_tokens
        self.output_tokens         += s.output_tokens
        self.cache_read_tokens     += s.cache_read_tokens
        self.cache_creation_tokens += s.cache_creation_tokens
        self.cost_usd              += s.cost_usd

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens


def aggregate(sessions: list[SessionStats]) -> dict[str, AgentAggregate]:
    aggs: dict[str, AgentAggregate] = defaultdict(lambda: AgentAggregate("?"))
    for s in sessions:
        key = s.agent
        if key not in aggs:
            aggs[key] = AgentAggregate(key)
        aggs[key].add(s)
    return dict(aggs)


# ─── Formateo ─────────────────────────────────────────────────────────────────

def fmt_k(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def print_table(aggs: dict[str, AgentAggregate], show_unknown: bool = False) -> None:
    rows = [
        a for k, a in sorted(aggs.items(), key=lambda x: -x[1].total_input)
        if show_unknown or not k.startswith("_")
    ]

    if not rows:
        print("No hay datos de sesiones con agentes identificados.")
        if not show_unknown:
            print("Usa --all para ver también sesiones sin agente identificado.")
        return

    # Totales
    total_in  = sum(r.total_input    for r in rows)
    total_out = sum(r.output_tokens  for r in rows)
    total_usd = sum(r.cost_usd       for r in rows)

    col_agent = max(len(r.agent) for r in rows)
    col_agent = max(col_agent, 5)

    sep = "-" * (col_agent + 58)
    hdr = f"{'AGENTE':<{col_agent}}  {'SESIONES':>7}  {'INPUT':>8}  {'CACHE_R':>8}  {'CACHE_W':>8}  {'OUTPUT':>8}  {'USD':>7}"

    print()
    print(hdr)
    print(sep)

    for r in rows:
        print(
            f"{r.agent:<{col_agent}}"
            f"  {r.sessions:>7}"
            f"  {fmt_k(r.input_tokens):>8}"
            f"  {fmt_k(r.cache_read_tokens):>8}"
            f"  {fmt_k(r.cache_creation_tokens):>8}"
            f"  {fmt_k(r.output_tokens):>8}"
            f"  ${r.cost_usd:>6.3f}"
        )

    print(sep)
    print(
        f"{'TOTAL':<{col_agent}}"
        f"  {sum(r.sessions for r in rows):>7}"
        f"  {fmt_k(sum(r.input_tokens for r in rows)):>8}"
        f"  {fmt_k(sum(r.cache_read_tokens for r in rows)):>8}"
        f"  {fmt_k(sum(r.cache_creation_tokens for r in rows)):>8}"
        f"  {fmt_k(total_out):>8}"
        f"  ${total_usd:>6.3f}"
    )
    print()
    print(f"INPUT = tokens nuevos  |  CACHE_R = cache read  |  CACHE_W = cache write  |  OUTPUT = tokens generados")
    print(f"Precios aprox. Sonnet 4.6: input ${PRICE_INPUT}/MTok  cache_r ${PRICE_CACHE_R}/MTok  cache_w ${PRICE_CACHE_W}/MTok  output ${PRICE_OUTPUT}/MTok")
    print()


def print_sessions(sessions: list[SessionStats], show_unknown: bool = False) -> None:
    filtered = [
        s for s in sessions
        if show_unknown or not s.agent.startswith("_")
    ]
    if not filtered:
        print("No hay sesiones con agentes identificados.")
        return

    col_agent = max(len(s.agent) for s in filtered)
    col_agent = max(col_agent, 5)
    print()
    print(f"{'AGENTE':<{col_agent}}  {'SESIÓN':>8}  {'INPUT':>8}  {'CACHE_R':>8}  {'OUTPUT':>8}  {'USD':>7}  FECHA")
    print("-" * (col_agent + 70))
    for s in sorted(filtered, key=lambda x: x.ts_first or ""):
        date = (s.ts_first or "")[:10]
        print(
            f"{s.agent:<{col_agent}}"
            f"  {s.session_id[:8]:>8}"
            f"  {fmt_k(s.input_tokens):>8}"
            f"  {fmt_k(s.cache_read_tokens):>8}"
            f"  {fmt_k(s.output_tokens):>8}"
            f"  ${s.cost_usd:>6.3f}"
            f"  {date}"
        )
    print()


def print_json_output(aggs: dict[str, AgentAggregate], sessions: list[SessionStats]) -> None:
    out = {
        "by_agent": {
            k: {
                "sessions":              a.sessions,
                "input_tokens":          a.input_tokens,
                "cache_read_tokens":     a.cache_read_tokens,
                "cache_creation_tokens": a.cache_creation_tokens,
                "output_tokens":         a.output_tokens,
                "cost_usd":              round(a.cost_usd, 6),
            }
            for k, a in sorted(aggs.items(), key=lambda x: -x[1].total_input)
        },
        "sessions": [
            {
                "session_id":            s.session_id,
                "agent":                 s.agent,
                "ts_first":              s.ts_first,
                "ts_last":               s.ts_last,
                "input_tokens":          s.input_tokens,
                "cache_read_tokens":     s.cache_read_tokens,
                "cache_creation_tokens": s.cache_creation_tokens,
                "output_tokens":         s.output_tokens,
                "cost_usd":              round(s.cost_usd, 6),
                "runtime_files_written": sorted(s.runtime_files_written),
            }
            for s in sorted(sessions, key=lambda x: x.ts_first or "")
        ],
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Muestra cuántos tokens consume cada agente del plugin.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python3 .claude/hooks/token-usage.py
  python3 .claude/hooks/token-usage.py --days 7
  python3 .claude/hooks/token-usage.py --session a8a84732
  python3 .claude/hooks/token-usage.py --verbose
  python3 .claude/hooks/token-usage.py --json
  python3 .claude/hooks/token-usage.py --all
        """,
    )
    parser.add_argument("--days",    type=int, metavar="N",
                        help="Solo sesiones de los últimos N días.")
    parser.add_argument("--session", metavar="UUID",
                        help="Filtrar por prefijo de session UUID.")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Mostrar tabla detallada por sesión además del resumen.")
    parser.add_argument("--json",    action="store_true",
                        help="Salida en JSON.")
    parser.add_argument("--all",     action="store_true",
                        help="Incluir sesiones sin agente identificado (_unknown).")
    parser.add_argument("--dir",     metavar="PATH",
                        help=f"Directorio de sesiones (default: {SESSION_DIR}).")
    args = parser.parse_args()

    session_dir = pathlib.Path(args.dir) if args.dir else SESSION_DIR

    if not session_dir.exists():
        print(f"No se encontró el directorio de sesiones: {session_dir}", file=sys.stderr)
        print("¿Está configurado correctamente el proyecto en Claude Code?", file=sys.stderr)
        return 1

    sessions = collect_sessions(
        session_dir,
        days=args.days,
        session_prefix=args.session,
    )

    if not sessions:
        print("No se encontraron sesiones con datos de tokens.")
        print(f"Directorio buscado: {session_dir}")
        return 0

    aggs = aggregate(sessions)

    if args.json:
        print_json_output(aggs, sessions)
        return 0

    total_sessions = len(sessions)
    known = sum(1 for s in sessions if not s.agent.startswith("_"))
    print(f"\nDirectorio: {session_dir}")
    print(f"Sesiones totales: {total_sessions}  |  Con agente identificado: {known}")
    if args.days:
        print(f"Filtro: últimos {args.days} días")

    if args.verbose:
        print_sessions(sessions, show_unknown=args.all)

    print_table(aggs, show_unknown=args.all)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
