#!/usr/bin/env python3
"""Gestiona la aprobacion del escaneo del repositorio para poblar los MAPs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
APPROVAL_PATH = PLUGIN_DIR / "runtime" / "map-scan-approval.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aprueba, rechaza o reinicia la aprobacion del escaneo de repositorio."
    )
    parser.add_argument(
        "action",
        choices=["approve", "reject", "reset"],
        help="Estado que quieres aplicar al escaneo.",
    )
    parser.add_argument(
        "--by",
        default="operator",
        help="Nombre de la persona que autoriza el escaneo.",
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
    else:
        status = "pending"

    return {
        "status": status,
        "approved_by": approved_by if status != "pending" else "",
        "notes": notes,
    }


def main() -> int:
    args = parse_args()
    payload = build_payload(args.action, args.by, args.notes)

    APPROVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPROVAL_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    print(f"Map scan approval status: {payload['status']}")
    if payload["approved_by"]:
        print(f"Approved by: {payload['approved_by']}")
    if payload["notes"]:
        print(f"Notes: {payload['notes']}")

    if payload["status"] == "approved":
        print("Puedes ahora ejecutar el agente map-scanner para poblar los MAPs.")
        print("Ver: claude/agents/map-scanner.md")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
