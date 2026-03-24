#!/usr/bin/env python3
"""Despacha la ejecucion simple a frontend y backend segun el plan aprobado."""

from __future__ import annotations

import json
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
PLAN_PATH = PLUGIN_DIR / "runtime" / "plan.json"
BRIEF_PATH = PLUGIN_DIR / "runtime" / "execution-brief.json"
APPROVAL_PATH = PLUGIN_DIR / "runtime" / "operator-approval.json"
REVIEW_PATH = PLUGIN_DIR / "runtime" / "plan-review.json"
DISPATCH_PATH = PLUGIN_DIR / "runtime" / "execution-dispatch.json"
ALLOWED_AGENTS = {"frontend", "backend", "test-runner"}

# Campos requeridos mínimos por archivo (subset crítico del schema)
_REQUIRED_FIELDS: dict[str, list[str]] = {
    "operator-approval.json": ["status", "approved_by"],
    "plan.json":               ["task", "steps", "done_criteria", "context_inputs"],
    "execution-brief.json":   ["task", "approval_status", "target_agents", "implementation_steps"],
    "plan-review.json":       ["verdict"],
}


def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} tiene JSON inválido: {exc}") from exc


def validate_fields(data: dict, filename: str) -> list[str]:
    """Devuelve lista de campos requeridos ausentes."""
    required = _REQUIRED_FIELDS.get(filename, [])
    return [f for f in required if f not in data]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _block(task: str, reason: str, *, approved: bool = False) -> dict:
    return {
        "status": "blocked",
        "approved": approved,
        "task": task,
        "selected_agents": [],
        "step_ids": [],
        "reason": reason,
    }


def main() -> int:
    # --- Carga y validación de schemas de entrada ---
    for path in (APPROVAL_PATH, PLAN_PATH):
        if not path.exists():
            print(f"Error: {path.name} no existe.")
            return 1
        try:
            load_json(path)  # valida JSON bien formado
        except ValueError as exc:
            print(str(exc))
            return 1

    try:
        approval = load_json(APPROVAL_PATH)
        plan = load_json(PLAN_PATH)
    except ValueError as exc:
        print(str(exc))
        return 1

    for obj, name in ((approval, "operator-approval.json"), (plan, "plan.json")):
        missing = validate_fields(obj, name)
        if missing:
            write_json(DISPATCH_PATH, _block(plan.get("task", "") if name != "plan.json" else "",
                                             f"{name} incompleto: faltan campos {missing}"))
            print(f"Ejecucion bloqueada: {name} no tiene los campos requeridos: {missing}")
            return 1

    # --- Validacion plan-review.json ---
    task = plan.get("task", "")

    if not REVIEW_PATH.exists():
        write_json(DISPATCH_PATH, _block(task, "plan-review.json no encontrado. El plan-reviewer debe ejecutarse antes de despachar."))
        print("Ejecucion bloqueada: plan-review.json no existe.")
        print("Ejecuta el flujo completo desde el writer para generar la revision.")
        return 1

    try:
        review = load_json(REVIEW_PATH)
    except ValueError as exc:
        write_json(DISPATCH_PATH, _block(task, str(exc)))
        print(str(exc))
        return 1

    missing_review = validate_fields(review, "plan-review.json")
    if missing_review:
        write_json(DISPATCH_PATH, _block(task, f"plan-review.json incompleto: faltan {missing_review}"))
        print(f"Ejecucion bloqueada: plan-review.json no tiene los campos requeridos: {missing_review}")
        return 1

    verdict = review.get("verdict")

    if verdict == "blocked":
        errors = [i for i in review.get("issues", []) if i.get("severity") == "error"]
        write_json(DISPATCH_PATH, _block(task, f"Plan-reviewer bloqueo la ejecucion: {review.get('summary', '')}"))
        print("=" * 60)
        print("EJECUCION BLOQUEADA — El plan-reviewer encontro errores criticos")
        print("=" * 60)
        print(f"Resumen: {review.get('summary', '')}")
        print()
        for issue in errors:
            print(f"  [{issue.get('id', '?')}] {issue.get('location', '?')}")
            print(f"  Categoria: {issue.get('category', '?')}")
            print(f"  Problema:  {issue.get('description', '')}")
            if issue.get("suggestion"):
                print(f"  Sugerido:  {issue['suggestion']}")
            print()
        print("Para reiniciar el flujo desde cero:")
        print("  python3 .claude/hooks/approve-plan.py reset")
        print("=" * 60)
        return 1

    if verdict == "warning":
        warnings = [i for i in review.get("issues", []) if i.get("severity") == "warning"]
        print(f"ADVERTENCIA — El plan-reviewer detecto {len(warnings)} riesgo(s): {review.get('summary', '')}")
        for w in warnings:
            print(f"  [{w.get('id', '?')}] {w.get('location', '?')}: {w.get('description', '')}")
        print()

    if approval.get("status") != "approved":
        write_json(DISPATCH_PATH, _block(task, "El plan no esta aprobado por el operador."))
        print("Ejecucion bloqueada: el plan no esta aprobado.")
        return 1

    if not BRIEF_PATH.exists():
        write_json(DISPATCH_PATH, _block(task, "execution-brief.json no existe. Ejecuta el writer primero.", approved=True))
        print("Ejecucion bloqueada: execution-brief.json no existe.")
        return 1

    try:
        brief = load_json(BRIEF_PATH)
    except ValueError as exc:
        write_json(DISPATCH_PATH, _block(task, str(exc), approved=True))
        print(str(exc))
        return 1

    missing_brief = validate_fields(brief, "execution-brief.json")
    if missing_brief:
        write_json(DISPATCH_PATH, _block(task, f"execution-brief.json incompleto: faltan {missing_brief}", approved=True))
        print(f"Ejecucion bloqueada: execution-brief.json no tiene los campos requeridos: {missing_brief}")
        return 1

    if not task:
        write_json(DISPATCH_PATH, _block("", "El plan no define una tarea.", approved=True))
        print("Ejecucion bloqueada: el plan no tiene tarea.")
        return 1

    selected_agents: list[str] = []
    step_ids: list[str] = []

    for step in plan.get("steps", []):
        owner = step.get("owner")
        if owner in ALLOWED_AGENTS:
            if owner not in selected_agents:
                selected_agents.append(owner)
            step_id = step.get("id")
            if step_id:
                step_ids.append(step_id)

    if not selected_agents:
        payload = {
            "status": "blocked",
            "approved": True,
            "task": plan.get("task", ""),
            "selected_agents": [],
            "step_ids": [],
            "reason": "Plan has no executable frontend or backend steps.",
        }
        write_json(DISPATCH_PATH, payload)
        print("Execution blocked: no frontend/backend steps found.")
        return 1

    payload = {
        "status": "ready",
        "approved": True,
        "task": plan.get("task", ""),
        "selected_agents": selected_agents,
        "step_ids": step_ids,
        "reason": "Execution can proceed for the selected specialized agents.",
    }
    if "rollback_plan" in plan:
        payload["rollback_plan"] = plan["rollback_plan"]
    write_json(DISPATCH_PATH, payload)

    print("Execution ready")
    print(f"Selected agents: {', '.join(selected_agents) if selected_agents else 'none'}")
    print(f"Step ids: {', '.join(step_ids) if step_ids else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
