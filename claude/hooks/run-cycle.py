#!/usr/bin/env python3
"""Orquestador del ciclo de planificacion — invoca agentes por CLI sin overhead de tokens."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PLUGIN_DIR.parent
RUNTIME = PLUGIN_DIR / "runtime"
READER_CONTEXT = RUNTIME / "reader-context.json"
PLAN_PATH = RUNTIME / "plan.json"
BRIEF_PATH = RUNTIME / "execution-brief.json"
SESSION_DIR = Path.home() / ".claude" / "projects" / str(PROJECT_ROOT).replace("/", "-").replace("\\", "-")

PRICE_INPUT = 3.00
PRICE_CACHE_W = 3.75
PRICE_CACHE_R = 0.30
PRICE_OUTPUT = 15.00

READER_PROMPT_TEMPLATE = """RESTRICCIONES: PROHIBIDO Bash, Glob, Grep, Search, ls. Solo Read y Write. NO planifiques, NO propongas soluciones, NO escribas texto — solo escribe el JSON.

Lee estos archivos en este orden:
1. .claude/maps/PROJECT_MAP.md
2. .claude/maps/PROJECT_MAP.json
3. Solo los domain MAPs relevantes para la petición:
   - .claude/maps/DB_MAP.json (si toca modelos/tablas)
   - .claude/maps/API_MAP.json (si toca endpoints)
   - .claude/maps/UI_MAP.json (si toca vistas)
   - .claude/maps/QUERY_MAP.json (si toca queries)
   - .claude/maps/SERVICES_MAP.json (si toca integraciones)
   - .claude/maps/JOBS_MAP.json (si toca tareas)

Después escribe .claude/runtime/reader-context.json siguiendo el formato de tu prompt de agente.

REGLAS: Solo paths que existan en los MAPs. Nunca inventes rutas. key_symbols extraídos de search_keywords o functions del MAP cuando existan.

Petición del operador: {petition}"""

# ── Colores para terminal ──────────────────────────────────────────────────

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def log(msg: str, color: str = "") -> None:
    print(f"{color}{msg}{RESET}")


def log_header(title: str) -> None:
    print(f"\n{CYAN}{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}{RESET}\n")


def log_step(step: int, total: int, msg: str) -> None:
    print(f"{BOLD}[{step}/{total}]{RESET} {msg}")


def log_detail(label: str, value: str) -> None:
    print(f"  {DIM}{label}:{RESET} {value}")


def log_json_summary(path: Path, keys: list[str]) -> None:
    """Muestra campos clave de un JSON generado."""
    data = load_json(path)
    if not data:
        return
    log(f"\n  {path.name}:", DIM)
    for key in keys:
        val = data.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            log(f"    {key}: [{len(val)} items]", DIM)
            for item in val[:5]:
                if isinstance(item, dict) and "path" in item:
                    log(f"      - {item['path']}", DIM)
                elif isinstance(item, dict) and "id" in item:
                    log(f"      - {item['id']}: {item.get('description', item.get('title', ''))[:60]}", DIM)
                elif isinstance(item, str):
                    log(f"      - {item}", DIM)
            if len(val) > 5:
                log(f"      ... y {len(val) - 5} mas", DIM)
        elif isinstance(val, str) and len(val) > 80:
            log(f"    {key}: {val[:80]}...", DIM)
        else:
            log(f"    {key}: {val}", DIM)


def usd(tokens: int, price_per_mtok: float) -> float:
    return tokens / 1_000_000 * price_per_mtok


def snapshot_sessions(session_dir: Path) -> dict[Path, float]:
    """Captura mtime de los jsonl de sesiones para detectar la última invocación."""
    if not session_dir.exists():
        return {}

    snapshot: dict[Path, float] = {}
    for path in session_dir.glob("*.jsonl"):
        try:
            snapshot[path] = path.stat().st_mtime
        except OSError:
            continue
    return snapshot


def parse_session_usage(path: Path) -> dict | None:
    """Extrae consumo de tokens de un archivo de sesión de Claude Code."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    if not lines:
        return None

    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_creation_tokens = 0
    n_messages = 0

    for raw in lines:
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if entry.get("type") != "assistant":
            continue

        usage = entry.get("message", {}).get("usage", {})
        if not usage:
            continue

        n_messages += 1
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        cache_read_tokens += usage.get("cache_read_input_tokens", 0)
        cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)

        cache_creation = usage.get("cache_creation", {})
        if isinstance(cache_creation, dict):
            for value in cache_creation.values():
                if isinstance(value, int):
                    cache_creation_tokens += value

    if n_messages == 0:
        return None

    return {
        "session_id": path.stem,
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "output_tokens": output_tokens,
        "cost_usd": (
            usd(input_tokens, PRICE_INPUT)
            + usd(cache_creation_tokens, PRICE_CACHE_W)
            + usd(cache_read_tokens, PRICE_CACHE_R)
            + usd(output_tokens, PRICE_OUTPUT)
        ),
    }


def detect_latest_session_usage(before: dict[Path, float], after: dict[Path, float]) -> dict | None:
    """Devuelve el consumo de la sesión jsonl tocada por la última invocación."""
    changed = [
        path for path, mtime in after.items()
        if path not in before or mtime > before[path]
    ]
    if not changed:
        return None

    latest = max(changed, key=lambda path: after[path])
    return parse_session_usage(latest)


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def log_agent_token_usage(agent: str, usage: dict | None) -> None:
    """Muestra el consumo de tokens del agente recién ejecutado."""
    if not usage:
        log(f"  Tokens {agent}: no disponibles.", YELLOW)
        return

    session_short = usage["session_id"][:8]
    log(
        "  "
        f"Tokens {agent}: "
        f"in={fmt_tokens(usage['input_tokens'])} "
        f"cache_r={fmt_tokens(usage['cache_read_tokens'])} "
        f"cache_w={fmt_tokens(usage['cache_creation_tokens'])} "
        f"out={fmt_tokens(usage['output_tokens'])} "
        f"usd=${usage['cost_usd']:.3f} "
        f"session={session_short}",
        DIM,
    )


def log_token_summary(agent_runs: list[tuple[str, dict | None]]) -> None:
    rows = [(agent, usage) for agent, usage in agent_runs if usage]
    if not rows:
        log("Consumo de tokens: no disponible.", YELLOW)
        return

    total_input = sum(usage["input_tokens"] for _, usage in rows)
    total_cache_r = sum(usage["cache_read_tokens"] for _, usage in rows)
    total_cache_w = sum(usage["cache_creation_tokens"] for _, usage in rows)
    total_output = sum(usage["output_tokens"] for _, usage in rows)
    total_usd = sum(usage["cost_usd"] for _, usage in rows)

    log("\nConsumo de tokens (ultima sesion detectada por agente):", BOLD)
    for agent, usage in rows:
        session_short = usage["session_id"][:8]
        log(
            "  "
            f"{agent:<7} "
            f"in={fmt_tokens(usage['input_tokens'])} "
            f"cache_r={fmt_tokens(usage['cache_read_tokens'])} "
            f"cache_w={fmt_tokens(usage['cache_creation_tokens'])} "
            f"out={fmt_tokens(usage['output_tokens'])} "
            f"usd=${usage['cost_usd']:.3f} "
            f"session={session_short}",
            DIM,
        )

    log(
        "  "
        f"{'TOTAL':<7} "
        f"in={fmt_tokens(total_input)} "
        f"cache_r={fmt_tokens(total_cache_r)} "
        f"cache_w={fmt_tokens(total_cache_w)} "
        f"out={fmt_tokens(total_output)} "
        f"usd=${total_usd:.3f}",
        DIM,
    )


def run_agent(agent: str, prompt: str | None = None, verbose: bool = False) -> tuple[int, float, dict | None]:
    """Invoca un agente de Claude Code via CLI en modo print. Retorna (exit_code, segundos, tokens)."""
    cmd = ["claude", "--agent", agent, "--print", "--dangerously-skip-permissions"]
    if prompt:
        cmd.append(prompt)

    if verbose:
        safe_cmd = cmd.copy()
        if prompt:
            safe_cmd[-1] = f"'{prompt[:60]}...'"
        log(f"  $ {' '.join(safe_cmd)}", DIM)

    sessions_before = snapshot_sessions(SESSION_DIR)
    start = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - start
    sessions_after = snapshot_sessions(SESSION_DIR)

    return result.returncode, elapsed, detect_latest_session_usage(sessions_before, sessions_after)


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}m {secs:.0f}s"


def main() -> int:
    parser = argparse.ArgumentParser(description="Orquesta el ciclo reader → planner → writer sin overhead de tokens.")
    parser.add_argument("petition", help="Peticion del usuario en texto libre.")
    parser.add_argument("--skip-reader", action="store_true", help="Saltar reader si reader-context.json ya existe.")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar comandos sin ejecutar.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Mostrar detalle: comandos, archivos leidos, JSONs generados, tiempos.")
    args = parser.parse_args()

    verbose = args.verbose
    total_start = time.time()
    token_runs: list[tuple[str, dict | None]] = []

    log_header("CICLO DE PLANIFICACION")
    log(f"Tarea: {args.petition}", BOLD)
    if verbose:
        log(f"Modo: {'dry-run' if args.dry_run else 'ejecucion real'} | verbose: on", DIM)

    # --- Paso 1: Reader ---
    log_step(1, 3, "Reader (Sonnet) — extraer contexto de MAPs")

    if args.skip_reader and READER_CONTEXT.exists():
        log("  Saltando — reader-context.json ya existe.", YELLOW)
    else:
        prompt = READER_PROMPT_TEMPLATE.format(petition=args.petition)
        if args.dry_run:
            log(f"  [dry-run] claude --agent reader --print '...'", DIM)
        else:
            rc, elapsed, usage = run_agent("reader", prompt, verbose)
            if rc != 0:
                log(f"  Reader fallo con codigo {rc}.", RED)
                return 1
            token_runs.append(("reader", usage))
            log(f"  Completado en {fmt_time(elapsed)}", GREEN)

        ctx = load_json(READER_CONTEXT)
        if not ctx:
            log("  Error: reader-context.json no fue generado.", RED)
            return 1
        if ctx.get("status") == "blocked_no_maps":
            log("  Reader bloqueado: no hay MAPs. Ejecuta:", RED)
            log("    python3 .claude/hooks/analyze-repo.py", YELLOW)
            return 1

        if not args.dry_run:
            log_agent_token_usage("reader", usage)

        if verbose:
            log_json_summary(READER_CONTEXT, [
                "status", "improved_prompt", "primary_reader",
                "maps_used", "files_to_open", "files_to_review",
            ])

    # --- Paso 2: Planner ---
    log_step(2, 3, "Planner (Opus) — leer codigo y generar plan")

    if args.dry_run:
        log(f"  [dry-run] claude --agent planner --print", DIM)
    else:
        rc, elapsed, usage = run_agent("planner", verbose=verbose)
        if rc != 0:
            log(f"  Planner fallo con codigo {rc}.", RED)
            return 1
        token_runs.append(("planner", usage))
        log(f"  Completado en {fmt_time(elapsed)}", GREEN)

    plan = load_json(PLAN_PATH)
    if not plan:
        log("  Error: plan.json no fue generado.", RED)
        return 1

    steps = plan.get("steps", [])
    if not args.dry_run:
        log_agent_token_usage("planner", usage)
    if verbose:
        log_json_summary(PLAN_PATH, ["task", "steps", "target_agents", "risks", "done_criteria"])
    else:
        log(f"  {len(steps)} paso(s) generados.", DIM)

    # --- Paso 3: Writer ---
    log_step(3, 3, "Writer (Sonnet) — generar instrucciones de ejecucion")

    if args.dry_run:
        log(f"  [dry-run] claude --agent writer --print", DIM)
    else:
        rc, elapsed, usage = run_agent("writer", verbose=verbose)
        if rc != 0:
            log(f"  Writer fallo con codigo {rc}.", RED)
            return 1
        token_runs.append(("writer", usage))
        log(f"  Completado en {fmt_time(elapsed)}", GREEN)

    brief = load_json(BRIEF_PATH)
    if not brief:
        log("  Error: execution-brief.json no fue generado.", RED)
        return 1

    if not args.dry_run:
        log_agent_token_usage("writer", usage)

    if verbose:
        log_json_summary(BRIEF_PATH, ["task", "agents", "steps"])

    # --- Resumen ---
    total_elapsed = time.time() - total_start

    log_header("CICLO COMPLETO — Plan listo para aprobacion")
    log(f"Tarea: {plan.get('task', '?')}", BOLD)
    log(f"Pasos: {len(steps)}")
    agents = sorted({s.get("owner", "?") for s in steps})
    log(f"Agentes: {', '.join(agents)}")
    if not args.dry_run:
        log_token_summary(token_runs)
    if verbose:
        log(f"Tiempo total: {fmt_time(total_elapsed)}", DIM)
        for step in steps:
            log(f"  [{step.get('id', '?')}] {step.get('owner', '?')}: {step.get('description', step.get('title', ''))[:70]}", DIM)

    log(f"\n{GREEN}Proximos pasos:{RESET}")
    log(f'  python3 .claude/hooks/approve-plan.py approve --by "tu nombre"')
    log(f"  python3 .claude/hooks/execute-plan.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
