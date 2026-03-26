#!/usr/bin/env python3
"""
Recuperacion del ciclo tras un fallo de ejecucion.

Acciones:
  status     — Muestra el estado actual del runtime sin modificar nada.
  rollback   — Genera rollback-dispatch.json desde el rollback_plan del plan.
               Limpia artefactos de ejecucion. Requiere rollback_plan.enabled=true.
  reset      — Limpia artefactos de ejecucion. Conserva plan y brief para re-ejecutar.
  full-reset — Elimina todo el runtime. El ciclo debe reiniciarse desde el reader.

Uso:
    python3 .claude/hooks/recover-cycle.py status
    python3 .claude/hooks/recover-cycle.py rollback --by "nombre"
    python3 .claude/hooks/recover-cycle.py reset --by "nombre"
    python3 .claude/hooks/recover-cycle.py full-reset --by "nombre"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_artifact, SCHEMA_MAP


PLUGIN_DIR = Path(__file__).resolve().parents[1]
RUNTIME    = PLUGIN_DIR / "runtime"

PLAN_PATH              = RUNTIME / "plan.json"
APPROVAL_PATH          = RUNTIME / "operator-approval.json"
DISPATCH_PATH          = RUNTIME / "execution-dispatch.json"
ROLLBACK_DISPATCH_PATH = RUNTIME / "rollback-dispatch.json"

# Artefactos generados durante la ejecucion de agentes
EXECUTION_ARTIFACTS = [
    RUNTIME / "result.json",
    RUNTIME / "reviewer-dispatch.json",
    RUNTIME / "review.json",
    RUNTIME / "rollback-dispatch.json",
    RUNTIME / "execution-brief.md",
]

# Artefactos de planificacion (anteriores a la ejecucion)
PLANNING_ARTIFACTS = [
    RUNTIME / "plan.json",
    RUNTIME / "execution-brief.json",
    RUNTIME / "execution-dispatch.json",
    RUNTIME / "files-read.json",
]

# Artefactos del reader (inicio del ciclo)
READER_ARTIFACTS = [
    RUNTIME / "reader-context.json",
    RUNTIME / "clarifications.json",
    RUNTIME / "operator-approval.json",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _clean(artifacts: list[Path]) -> list[str]:
    """Elimina los artefactos que existen. Devuelve lista de nombres eliminados."""
    removed = []
    for p in artifacts:
        if p.exists():
            p.unlink()
            removed.append(p.name)
    return removed


def _reset_approval(notes: str = "") -> None:
    write_json(APPROVAL_PATH, {"status": "pending", "approved_by": "", "notes": notes})


def _reset_dispatch(reason: str) -> None:
    write_json(DISPATCH_PATH, {
        "status": "blocked",
        "approved": False,
        "task": "",
        "selected_agents": [],
        "step_ids": [],
        "reason": reason,
    })


# ── Comandos ──────────────────────────────────────────────────────────────────

def cmd_status() -> int:
    print("Estado del runtime")
    print("=" * 52)
    all_files = EXECUTION_ARTIFACTS + PLANNING_ARTIFACTS + READER_ARTIFACTS
    seen: set[str] = set()
    for f in all_files:
        if f.name in seen:
            continue
        seen.add(f.name)
        if f.exists():
            data = load_json(f)
            if not data:
                print(f"  [CORRUPT] {f.name:<34} (JSON inválido o vacío)")
                continue
            status_val = data.get("status") or data.get("verdict") or "—"
            task_val   = data.get("task", "")
            extra      = f" task={task_val[:40]!r}" if task_val else ""
            if f.name in SCHEMA_MAP:
                vr = validate_artifact(f.name, data)
                if not vr.ok:
                    print(f"  [INVALID] {f.name:<34} {status_val}{extra}")
                    for e in vr.errors:
                        print(f"            ERROR: {e}")
                elif vr.warnings:
                    print(f"  [WARN]    {f.name:<34} {status_val}{extra}")
                else:
                    print(f"  [OK]      {f.name:<34} {status_val}{extra}")
            else:
                print(f"  [OK]      {f.name:<34} {status_val}{extra}")
        else:
            print(f"  [--]      {f.name}")

    print()
    plan = load_json(PLAN_PATH)
    rollback = plan.get("rollback_plan", {})
    if rollback.get("enabled"):
        n = len(rollback.get("steps", []))
        owners = list(dict.fromkeys(s.get("owner", "?") for s in rollback.get("steps", [])))
        print(f"  Rollback disponible: {n} paso(s) — agentes: {', '.join(owners)}")
    else:
        print("  Rollback: no definido en el plan actual")
    return 0


def cmd_rollback(approved_by: str) -> int:
    plan = load_json(PLAN_PATH)
    if not plan:
        print("Error: plan.json no existe o está vacío. No hay rollback_plan que ejecutar.")
        return 1

    if PLAN_PATH.name in SCHEMA_MAP:
        vr = validate_artifact(PLAN_PATH.name, plan)
        if not vr.ok:
            print(f"Error: plan.json es inválido:\n{vr.format()}")
            return 1

    rollback = plan.get("rollback_plan", {})
    if not rollback.get("enabled"):
        print("Error: rollback_plan.enabled=false (o no definido).")
        print("Usa 'reset' para volver al estado pre-ejecución.")
        return 1

    steps = rollback.get("steps", [])
    if not steps:
        print("Error: rollback_plan.enabled=true pero steps está vacío.")
        return 1

    rollback_agents = list(dict.fromkeys(s["owner"] for s in steps if "owner" in s))

    write_json(ROLLBACK_DISPATCH_PATH, {
        "status": "ready",
        "approved": True,
        "mode": "rollback",
        "task": f"ROLLBACK: {plan.get('task', '')}",
        "selected_agents": rollback_agents,
        "rollback_steps": steps,
        "reason": "Rollback activado por el operador tras fallo de ejecucion.",
    })

    # Limpia artefactos de ejecucion fallida (excepto el dispatch de rollback recién escrito)
    to_clean = [p for p in EXECUTION_ARTIFACTS if p != ROLLBACK_DISPATCH_PATH]
    removed = _clean(to_clean)

    _reset_approval(notes="Rollback en progreso.")

    print("Rollback dispatch generado.")
    print(f"  Agentes: {', '.join(rollback_agents)}")
    print(f"  Pasos:   {len(steps)}")
    if removed:
        print(f"  Limpiados: {', '.join(removed)}")
    print()
    print("Siguiente paso: invoca los agentes listados en rollback-dispatch.json.")
    return 0


def cmd_reset(approved_by: str) -> int:
    """Limpia solo artefactos de ejecucion. Plan y brief se conservan para re-ejecutar."""
    removed = _clean(EXECUTION_ARTIFACTS)
    _reset_approval()
    _reset_dispatch("Ciclo reseteado. Re-aprueba y vuelve a ejecutar con execute-plan.py.")

    plan = load_json(PLAN_PATH)
    if plan and PLAN_PATH.name in SCHEMA_MAP:
        vr = validate_artifact(PLAN_PATH.name, plan)
        if vr.errors:
            print(f"Advertencia: plan.json tiene errores de schema (se conserva de todas formas):")
            print(vr.format())
    task = plan.get("task", "")

    print("Reset completado (artefactos de ejecucion eliminados).")
    if removed:
        print(f"  Eliminados: {', '.join(removed)}")
    if task:
        print(f"  Plan conservado: {task[:70]}")
    print()
    print("Siguiente paso:")
    print("  1. python3 .claude/hooks/approve-plan.py approve --by \"nombre\"")
    print("  2. python3 .claude/hooks/execute-plan.py")
    return 0


def cmd_full_reset(approved_by: str) -> int:
    """Elimina todos los artefactos de runtime. El ciclo reinicia desde cero."""
    all_artifacts = list(dict.fromkeys(
        EXECUTION_ARTIFACTS + PLANNING_ARTIFACTS + READER_ARTIFACTS
    ))
    removed = _clean(all_artifacts)
    _reset_approval()

    print(f"Full-reset completado. Runtime limpio ({len(removed)} archivos eliminados).")
    if removed:
        print(f"  Eliminados: {', '.join(removed)}")
    print()
    print("Siguiente paso: invoca el reader con la nueva peticion del usuario.")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recuperacion del ciclo tras fallo de ejecucion.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "action",
        choices=["status", "rollback", "reset", "full-reset"],
    )
    parser.add_argument(
        "--by",
        default="operator",
        help="Nombre del operador que activa la recuperacion.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dispatch = {
        "status":     cmd_status,
        "rollback":   lambda: cmd_rollback(args.by),
        "reset":      lambda: cmd_reset(args.by),
        "full-reset": lambda: cmd_full_reset(args.by),
    }
    return dispatch[args.action]()


if __name__ == "__main__":
    raise SystemExit(main())
