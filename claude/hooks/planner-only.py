#!/usr/bin/env python3
"""Planner standalone — lee reader-context.json, crea plan.json. Sin confirmaciones."""

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
PLAN_JSON = RUNTIME / "plan.json"
PLANNER_AGENT = PLUGIN_DIR / "agents" / "planner.md"
SESSION_DIR = Path.home() / ".claude" / "projects" / str(PROJECT_ROOT).replace("/", "-").replace("\\", "-")


def load_planner_prompt() -> str | None:
	"""Lee planner.md y quita el frontmatter YAML (--- ... ---)."""
	try:
		content = PLANNER_AGENT.read_text(encoding="utf-8")
	except OSError:
		return None
	# Quitar frontmatter YAML
	if content.startswith("---"):
		end = content.find("---", 3)
		if end != -1:
			content = content[end + 3:].lstrip("\n")
	return content


def validate_reader_context() -> dict | None:
	"""Valida que reader-context.json exista y sea válido."""
	if not READER_CONTEXT.exists():
		return None
	try:
		ctx = json.loads(READER_CONTEXT.read_text(encoding="utf-8"))
		return ctx
	except (json.JSONDecodeError, OSError):
		return None


# Precios Sonnet 4.6 (USD por millón de tokens)
PRICE_INPUT   = 3.00
PRICE_CACHE_W = 3.75
PRICE_CACHE_R = 0.30
PRICE_OUTPUT  = 15.00

# ── Colores ────────────────────────────────────────────────────────────────────

CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RED    = "\033[31m"
RESET  = "\033[0m"


# ── Sesiones / tokens ──────────────────────────────────────────────────────────

def snapshot_sessions(session_dir: Path) -> set[Path]:
	"""Captura qué archivos .jsonl existen ANTES de lanzar el agente."""
	if not session_dir.exists():
		return set()
	return set(session_dir.glob("*.jsonl"))


def find_new_session(before: set[Path], session_dir: Path) -> Path | None:
	"""Encuentra el .jsonl que NO existía antes — ese es el del agente que acabamos de lanzar."""
	if not session_dir.exists():
		return None
	after = set(session_dir.glob("*.jsonl"))
	new_files = after - before
	if not new_files:
		return None
	# Si hay más de uno (raro), tomar el más reciente
	return max(new_files, key=lambda p: p.stat().st_mtime)


def parse_session_tokens(path: Path) -> dict | None:
	"""Lee el .jsonl y suma tokens de todos los mensajes assistant.

	Cada mensaje assistant es una llamada a la API de Anthropic.
	Los campos de usage son POR REQUEST (no acumulativos):
	  - input_tokens: tokens nuevos enviados (sin cache)
	  - cache_read_input_tokens: tokens leídos de cache
	  - cache_creation_input_tokens: tokens escritos a cache
	  - output_tokens: tokens generados por el modelo

	NOTA: El campo anidado "cache_creation" (con ephemeral_5m/1h) es solo
	el DESGLOSE del cache_creation_input_tokens — NO se suma por separado.
	"""
	try:
		lines = path.read_text(encoding="utf-8").splitlines()
	except OSError:
		return None
	if not lines:
		return None

	input_tokens = 0
	output_tokens = 0
	cache_read = 0
	cache_write = 0
	n_turns = 0
	tools_used: list[str] = []

	for raw in lines:
		try:
			entry = json.loads(raw)
		except json.JSONDecodeError:
			continue

		if entry.get("type") != "assistant":
			continue

		msg = entry.get("message", {})
		usage = msg.get("usage", {})
		if not usage:
			continue

		n_turns += 1
		input_tokens  += usage.get("input_tokens", 0)
		output_tokens += usage.get("output_tokens", 0)
		cache_read    += usage.get("cache_read_input_tokens", 0)
		cache_write   += usage.get("cache_creation_input_tokens", 0)

		# Extraer herramientas usadas (para mostrar qué hizo)
		for block in msg.get("content", []):
			if isinstance(block, dict) and block.get("type") == "tool_use":
				name = block.get("name", "")
				fp = block.get("input", {}).get("file_path", "")
				if fp:
					short = "/".join(Path(fp).parts[-3:])  # últimos 3 segmentos
					tools_used.append(f"{name}({short})")
				elif name:
					tools_used.append(name)

	if n_turns == 0:
		return None

	total_in = input_tokens + cache_read + cache_write
	cost = (
		input_tokens  / 1_000_000 * PRICE_INPUT
		+ cache_write / 1_000_000 * PRICE_CACHE_W
		+ cache_read  / 1_000_000 * PRICE_CACHE_R
		+ output_tokens / 1_000_000 * PRICE_OUTPUT
	)

	return {
		"session_id":    path.stem,
		"session_file":  str(path),
		"turns":         n_turns,
		"input_tokens":  input_tokens,
		"cache_read":    cache_read,
		"cache_write":   cache_write,
		"output_tokens": output_tokens,
		"total_in":      total_in,
		"total_tokens":  total_in + output_tokens,
		"cost_usd":      cost,
		"tools_used":    tools_used,
	}


def fmt_tokens(n: int) -> str:
	if n >= 1_000_000:
		return f"{n / 1_000_000:.1f}M"
	if n >= 1_000:
		return f"{n / 1_000:.1f}k"
	return str(n)


def fmt_time(s: float) -> str:
	if s < 60:
		return f"{s:.1f}s"
	return f"{int(s // 60)}m {s % 60:.0f}s"


def print_usage(usage: dict, elapsed: float | None = None) -> None:
	"""Muestra el consumo de tokens de forma clara."""
	sid = usage["session_id"][:8]
	n_tools = len(usage["tools_used"])

	print(f"\n{CYAN}{'─'*60}")
	print(f"  CONSUMO DE TOKENS (SONNET) — sesión {sid}")
	print(f"{'─'*60}{RESET}")

	print(f"\n  {BOLD}Turnos API:{RESET}       {usage['turns']}")
	print()
	print(f"  {BOLD}Entrada:{RESET}")
	print(f"    Tokens nuevos:   {usage['input_tokens']:>10,}  ({fmt_tokens(usage['input_tokens'])})  $3.00/M")
	print(f"    Cache leído:     {usage['cache_read']:>10,}  ({fmt_tokens(usage['cache_read'])})     $0.30/M")
	print(f"    Cache escrito:   {usage['cache_write']:>10,}  ({fmt_tokens(usage['cache_write'])})  $3.75/M")
	print(f"    {'─'*40}")
	print(f"    Total entrada:   {usage['total_in']:>10,}  ({fmt_tokens(usage['total_in'])})")

	print()
	print(f"  {BOLD}Salida:{RESET}")
	print(f"    Tokens output:   {usage['output_tokens']:>10,}  ({fmt_tokens(usage['output_tokens'])})  $15.00/M")

	print()
	print(f"  {BOLD}Total tokens:{RESET}     {usage['total_tokens']:>10,}  ({fmt_tokens(usage['total_tokens'])})")
	print(f"  {BOLD}Costo estimado:{RESET}   ${usage['cost_usd']:.4f} USD  ✅ Sonnet = barato")

	if usage["tools_used"]:
		print(f"\n  {BOLD}Operaciones:{RESET}")
		for tool in usage["tools_used"]:
			print(f"    → {tool}")

	# Línea resumen estilo CLI
	useful = usage["input_tokens"] + usage["output_tokens"]
	time_str = fmt_time(elapsed) if elapsed else "?"
	print(f"\n  {GREEN}Done ({n_tools} tool uses · "
		  f"{fmt_tokens(useful)} tokens · {time_str}){RESET}")

	print(f"\n{DIM}  Archivo: {usage['session_file']}{RESET}")
	print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
	parser = argparse.ArgumentParser(description="Planner standalone — genera plan.json desde reader-context.json.")
	parser.add_argument("--skip-validation", action="store_true", help="Saltarse validación de reader-context.json")
	args = parser.parse_args()

	print(f"\n{CYAN}{'='*60}")
	print(f"  PLANNER — generando plan.json")
	print(f"{'='*60}{RESET}\n")

	# Validar que reader-context.json existe y es válido
	if not args.skip_validation:
		ctx = validate_reader_context()
		if not ctx:
			print(f"{RED}Error: {READER_CONTEXT} no existe o no es válido JSON.{RESET}")
			print(f"{DIM}(Ejecuta reader-only.py primero o usa --skip-validation){RESET}")
			return 1
		print(f"{GREEN}✓ reader-context.json validado{RESET}")
		print(f"  - Tarea: {ctx.get('improved_prompt', '?')[:60]}...")
		print(f"  - Archivos a abrir: {len(ctx.get('files_to_open', []))}")
		print(f"  - Archivos a revisar: {len(ctx.get('files_to_review', []))}\n")
	else:
		print(f"{YELLOW}⚠  Validación saltada (--skip-validation){RESET}\n")

	# Cargar planner.md (sin frontmatter) + contexto del reader
	planner_prompt = load_planner_prompt()
	if not planner_prompt:
		print(f"{RED}Error: no se encontró {PLANNER_AGENT}{RESET}")
		return 1

	# Inyectar contexto del reader en el mensaje del usuario
	ctx_str = ""
	if not args.skip_validation:
		ctx_str = READER_CONTEXT.read_text(encoding="utf-8")

	user_message = f"Contexto del reader:\n\n{ctx_str}\n\nGenera plan.json según tus instrucciones."

	# --system-prompt inyecta planner.md como system prompt
	cmd = [
		"claude",
		"--model", "claude-sonnet-4-6",
		"--system-prompt", planner_prompt,
		user_message,
	]

	print(f"{BOLD}Ejecutando planner (Opus 4.6)...{RESET}\n")

	before = snapshot_sessions(SESSION_DIR)
	start  = time.time()

	result = subprocess.run(cmd)

	elapsed = time.time() - start

	if result.returncode != 0:
		print(f"\n{RED}Planner terminó con error (código {result.returncode}).{RESET}")
		return result.returncode

	print(f"\n{GREEN}Completado en {fmt_time(elapsed)}{RESET}")

	# Verificar que plan.json fue escrito
	if PLAN_JSON.exists():
		try:
			plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
			n_steps = len(plan.get("steps", []))
			print(f"\n{GREEN}plan.json: {n_steps} pasos identificados{RESET}")
		except (json.JSONDecodeError, OSError) as e:
			print(f"\n{RED}plan.json existe pero no es JSON válido: {e}{RESET}")
	else:
		print(f"\n{RED}El planner no escribió plan.json.{RESET}")

	# Buscar la sesión NUEVA (no la modificada, la que no existía antes)
	session_path = find_new_session(before, SESSION_DIR)
	if session_path:
		usage = parse_session_tokens(session_path)
		if usage:
			print_usage(usage, elapsed)
		else:
			print(f"\n{YELLOW}Sesión encontrada pero sin datos de tokens.{RESET}")
	else:
		print(f"\n{YELLOW}No se detectó sesión nueva en {SESSION_DIR}{RESET}")
		print(f"{DIM}(Sesiones existentes: {len(before)}){RESET}")

	return 0


if __name__ == "__main__":
	sys.exit(main())
