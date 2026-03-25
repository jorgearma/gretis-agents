#!/usr/bin/env python3
"""Actualiza el estado de aprobacion del plan del plugin de Claude."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_artifact


PLUGIN_DIR = Path(__file__).resolve().parents[1]
APPROVAL_PATH = PLUGIN_DIR / "runtime" / "operator-approval.json"
DISPATCH_PATH = PLUGIN_DIR / "runtime" / "execution-dispatch.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aprueba, rechaza o reinicia la aprobacion del plan."
    )
    parser.add_argument(
        "action",
        choices=["approve", "reject", "reset", "replantear"],
        help="Estado que quieres aplicar al plan.",
    )
    parser.add_argument(
        "--by",
        default="operator",
        help="Nombre de la persona que revisa el plan.",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Notas opcionales sobre la decision.",
    )
    return parser.parse_args()


def build_payload(action: str, approved_by: str, notes: str) -> dict[str, str]:
    if action == "approve":
        status = "approved"
    elif action == "reject":
        status = "rejected"
    elif action == "replantear":
        status = "replanning"
    else:
        status = "pending"

    return {
        "status": status,
        "approved_by": approved_by if status not in ("pending", "replanning") else "",
        "notes": notes,
    }


def write_payload(payload: dict[str, str]) -> None:
    APPROVAL_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def write_dispatch_reset(reason: str) -> None:
    payload = {
        "status": "blocked",
        "approved": False,
        "task": "",
        "selected_agents": [],
        "step_ids": [],
        "reason": reason,
    }
    DISPATCH_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    payload = build_payload(args.action, args.by, args.notes)
    vr = validate_artifact("operator-approval.json", payload)
    if not vr.ok:
        print(vr.format())
        return 1
    write_payload(payload)
    if payload["status"] == "replanning":
        write_dispatch_reset("Plan enviado a replantear. Invoca el planner con el contexto de plan-review.json.")
    elif payload["status"] != "approved":
        write_dispatch_reset("Execution requires a newly approved plan.")

    print(f"Plan approval status: {payload['status']}")
    if payload["approved_by"]:
        print(f"Approved by: {payload['approved_by']}")
    if payload["notes"]:
        print(f"Notes: {payload['notes']}")
    if payload["status"] == "replanning":
        print()
        print("El plan volvera al planner con los warnings del plan-reviewer como contexto.")
        print("Invoca el agente planner para generar un nuevo plan.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
