#!/usr/bin/env python3
"""Genera reviewer-dispatch.json tras la ejecucion de agentes frontend/backend."""

from __future__ import annotations

import json
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
RESULT_PATH = PLUGIN_DIR / "runtime" / "result.json"
DISPATCH_PATH = PLUGIN_DIR / "runtime" / "execution-dispatch.json"
REVIEWER_DISPATCH_PATH = PLUGIN_DIR / "runtime" / "reviewer-dispatch.json"


def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} tiene JSON inválido: {exc}") from exc


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _block(reason: str, agents: list[str] | None = None) -> dict:
    return {
        "status": "blocked",
        "result_available": False,
        "agents_completed": agents or [],
        "reason": reason,
    }


def main() -> int:
    if not RESULT_PATH.exists():
        write_json(REVIEWER_DISPATCH_PATH, _block("result.json no existe. Los agentes ejecutores no han terminado."))
        print("Reviewer dispatch bloqueado: result.json no encontrado.")
        return 1

    try:
        result = load_json(RESULT_PATH)
    except ValueError as exc:
        write_json(REVIEWER_DISPATCH_PATH, _block(str(exc)))
        print(str(exc))
        return 1

    if not result:
        write_json(REVIEWER_DISPATCH_PATH, _block("result.json esta vacio. Ningun agente produjo salida."))
        print("Reviewer dispatch bloqueado: result.json vacio.")
        return 1

    # Determina qué agentes debían ejecutarse según el dispatch original
    expected_agents: list[str] = []
    if DISPATCH_PATH.exists():
        try:
            dispatch = load_json(DISPATCH_PATH)
            expected_agents = [a for a in dispatch.get("selected_agents", []) if a in ("frontend", "backend")]
        except ValueError:
            pass  # Si dispatch está corrupto, inferimos desde result.json

    agents_in_result = [a for a in ("frontend", "backend") if a in result]
    agents_completed = agents_in_result  # presentes en result.json

    agents_partial = [a for a in agents_completed if result[a].get("status") == "partial"]
    agents_blocked  = [a for a in agents_completed if result[a].get("status") == "blocked"]
    agents_success  = [a for a in agents_completed if result[a].get("status") == "success"]

    # Si todos los agentes esperados terminaron bloqueados → no hay nada que revisar
    agents_to_check = expected_agents or agents_completed
    all_blocked = bool(agents_to_check) and all(
        result.get(a, {}).get("status") == "blocked" for a in agents_to_check
    )

    if all_blocked:
        blocked_reasons = {
            a: result[a].get("reason", "sin motivo") for a in agents_blocked
        }
        detail = "; ".join(f"{a}: {r}" for a, r in blocked_reasons.items())
        write_json(REVIEWER_DISPATCH_PATH, _block(
            f"Todos los agentes ejecutores terminaron bloqueados. No hay cambios que revisar. {detail}",
            agents_completed,
        ))
        print("=" * 60)
        print("REVIEWER DISPATCH BLOQUEADO — ningun agente produjo cambios")
        print("=" * 60)
        for agent, reason in blocked_reasons.items():
            print(f"  {agent}: {reason}")
        print()
        print("Opciones:")
        print("  1. Corrige el error reportado y vuelve a ejecutar los agentes.")
        print("  2. Si existe rollback_plan: python3 .claude/hooks/recover-cycle.py rollback")
        print("  3. Para reiniciar desde cero: python3 .claude/hooks/approve-plan.py reset")
        print("=" * 60)
        return 1

    notes = []
    if agents_partial:
        notes.append(f"Ejecucion parcial en: {', '.join(agents_partial)}.")
    if agents_blocked:
        notes.append(f"Bloqueados con salida parcial: {', '.join(agents_blocked)}.")
    if not agents_success and not agents_partial:
        notes.append("Advertencia: ningun agente reporto status 'success'.")

    payload = {
        "status": "ready",
        "result_available": True,
        "agents_completed": agents_completed,
        "agents_success": agents_success,
        "agents_partial": agents_partial,
        "agents_blocked": agents_blocked,
        "reason": " ".join(notes) if notes else "Ejecucion completada. Revision disponible.",
    }
    write_json(REVIEWER_DISPATCH_PATH, payload)

    print("Reviewer dispatch listo.")
    print(f"Agentes completados: {', '.join(agents_completed) if agents_completed else 'ninguno'}")
    if notes:
        print(f"Notas: {' '.join(notes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
