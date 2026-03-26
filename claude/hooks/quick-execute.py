#!/usr/bin/env python3
"""
quick-execute.py — Fast track para tareas simples que no necesitan planner ni writer.

Uso:
    python3 .claude/hooks/quick-execute.py "Cambiar color boton a rojo"
    python3 .claude/hooks/quick-execute.py "Implementar auth JWT" --full-plan
    python3 .claude/hooks/quick-execute.py --status

El script evalua la complejidad de la tarea, detecta el agente objetivo, escribe
quick-dispatch.json y auto-aprueba. Si la tarea parece compleja, advierte y sugiere
el flujo completo.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_artifact

# ─── Rutas ────────────────────────────────────────────────────────────────────

PLUGIN_DIR     = Path(__file__).resolve().parents[1]
DISPATCH_PATH  = PLUGIN_DIR / "runtime" / "quick-dispatch.json"
APPROVAL_PATH  = PLUGIN_DIR / "runtime" / "operator-approval.json"
PROJECT_MAP    = PLUGIN_DIR / "maps"    / "PROJECT_MAP.json"

# ─── Clasificacion de complejidad ─────────────────────────────────────────────

# Palabras que indican tarea compleja — suben el score
COMPLEX_KEYWORDS: list[str] = [
    "implementar", "implement", "refactor", "refactorizar", "migrar", "migrate",
    "rediseñar", "redesign", "arquitectura", "architecture", "sistema", "system",
    "integrar", "integrate", "autenticacion", "authentication", "autorizar",
    "authorize", "oauth", "jwt", "permisos", "permissions", "roles",
    "migracion", "migration", "schema", "database", "base de datos",
    "modulo", "module", "servicio", "service", "api completa", "full api",
    "pipeline", "workflow", "reemplazar", "replace entire",
]

# Palabras que indican tarea simple — bajan el score
SIMPLE_KEYWORDS: list[str] = [
    "cambiar", "change", "color", "texto", "text", "label", "boton", "button",
    "icono", "icon", "imagen", "image", "padding", "margin", "font",
    "tamaño", "size", "borde", "border", "fondo", "background",
    "renombrar", "rename", "mover", "move", "copiar", "copy",
    "agregar campo", "add field", "quitar campo", "remove field",
    "mensaje de error", "error message", "placeholder", "tooltip",
    "comentario", "comment", "typo", "ortografia", "spelling",
    "log", "print", "console",
]

# Keywords para detectar el agente objetivo
FRONTEND_KEYWORDS: list[str] = [
    "boton", "button", "color", "estilo", "style", "css", "html", "template",
    "vista", "view", "pagina", "page", "componente", "component", "modal",
    "formulario", "form", "input", "label", "menu", "navbar", "sidebar",
    "layout", "icono", "icon", "imagen", "image", "font", "padding", "margin",
    "borde", "border", "fondo", "background", "texto", "text", "ui", "ux",
    "dropdown", "tabla", "table", "card", "banner", "tooltip", "placeholder",
    "animacion", "animation", "responsive", "mobile", "desktop",
]

BACKEND_KEYWORDS: list[str] = [
    "endpoint", "api", "ruta", "route", "query", "consulta", "base de datos",
    "database", "modelo", "model", "campo", "field", "columna", "column",
    "migracion", "migration", "servicio", "service", "autenticacion",
    "authentication", "token", "password", "contrasena", "email", "validar",
    "validate", "middleware", "controlador", "controller", "manager",
    "repositorio", "repository", "cache", "redis", "cola", "queue",
    "job", "tarea", "task", "cron", "webhook", "log", "audit",
]


def compute_complexity(task: str) -> tuple[int, list[str]]:
    """
    Retorna (score, reasons).
    score 0-4:  simple → fast track OK
    score 5-7:  borderline → advertencia
    score 8+:   complejo → recomendar flujo completo
    """
    task_low = task.lower()
    score = 0
    reasons: list[str] = []

    # Longitud de la descripcion
    word_count = len(task.split())
    if word_count > 20:
        score += 2
        reasons.append(f"descripcion larga ({word_count} palabras)")
    elif word_count > 12:
        score += 1

    # Keywords complejas — se acumulan (max 3 hits para no saturar)
    # Usa word-boundary para evitar que "implement" matchee dentro de "implementar"
    complex_hits = [
        kw for kw in COMPLEX_KEYWORDS
        if re.search(r'\b' + re.escape(kw) + r'\b', task_low)
    ][:3]
    for kw in complex_hits:
        score += 3
        reasons.append(f"keyword compleja: '{kw}'")

    # Multiples acciones (and / y conectando tareas distintas)
    multi = re.search(r'\b(y ademas|y tambien|and also|and then|, y |, and )\b', task_low)
    if multi:
        score += 2
        reasons.append("multiples acciones encadenadas")

    # Muchas palabras tecnicas distintas en la misma tarea (señal de complejidad)
    tech_words = re.findall(r'\b[a-z]{5,}\b', task_low)
    unique_tech = len(set(tech_words))
    if unique_tech >= 8:
        score += 2
        reasons.append(f"{unique_tech} conceptos tecnicos distintos")

    # Scope masivo: "all/every/todos N+ entidades" indica impacto amplio
    scope_mass = re.search(
        r'\b(all|every|todos|todas|cada)\s+(component|archivo|file|route|ruta|model|tabla|table|endpoint|view|vista)\w*',
        task_low,
    )
    if scope_mass:
        score += 5
        reasons.append(f"scope masivo ({scope_mass.group(0)!r})")
    elif re.search(r'\b\d{2,}\s+(component|archivo|file|route|ruta|model|tabla|table|endpoint|view|vista)\w*', task_low):
        m = re.search(r'\b\d{2,}\s+\w+', task_low)
        score += 5
        reasons.append(f"scope masivo ({m.group(0)!r})" if m else "scope masivo (N+ entidades)")

    # Keywords simples (reducen score — max -2)
    # No aplican si ya se detecto scope masivo: N+ entidades invalida cualquier simpleza
    if not scope_mass and not re.search(
        r'\b\d{2,}\s+(component|archivo|file|route|ruta|model|tabla|table|endpoint|view|vista)\w*', task_low
    ):
        simple_hits = sum(1 for kw in SIMPLE_KEYWORDS if kw in task_low)
        if simple_hits > 0:
            reduction = min(simple_hits, 2)
            score = max(0, score - reduction)

    return score, reasons


def detect_agent(task: str) -> str:
    """Infiere el agente objetivo: 'frontend', 'backend' o 'both'."""
    task_low = task.lower()
    fe_hits = sum(1 for kw in FRONTEND_KEYWORDS if kw in task_low)
    be_hits = sum(1 for kw in BACKEND_KEYWORDS if kw in task_low)

    if fe_hits > be_hits:
        return "frontend"
    if be_hits > fe_hits:
        return "backend"
    # Empate o sin hits: pide al operador que especifique, default frontend
    return "frontend"


def load_map_hints(task: str) -> tuple[list[str], list[str]]:
    """
    Lee PROJECT_MAP.json y devuelve (stack_hint, files_hint).
    stack_hint: lista de frameworks del proyecto.
    files_hint: hasta 3 archivos cuyas search_keywords coincidan con la tarea.
    """
    if not PROJECT_MAP.exists():
        return [], []

    try:
        data = json.loads(PROJECT_MAP.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], []

    stack_hint = list(data.get("stack", {}).keys())[:6]

    task_low = task.lower()
    task_words = set(re.split(r"[\s_\-]+", task_low))

    files_hint: list[str] = []
    for role_files in data.get("modules", {}).values():
        for mod in role_files:
            keywords = mod.get("search_keywords", [])
            if any(kw in task_words or kw in task_low for kw in keywords):
                files_hint.append(mod["path"])
            if len(files_hint) >= 4:
                break
        if len(files_hint) >= 4:
            break

    return stack_hint, files_hint


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def show_status() -> int:
    """Muestra el estado del ultimo quick-dispatch."""
    if not DISPATCH_PATH.exists():
        print("No hay quick-dispatch activo.")
        return 0
    data = json.loads(DISPATCH_PATH.read_text(encoding="utf-8"))
    if data.get("mode") != "quick":
        print("El dispatch actual no es de modo quick.")
        return 0
    print(f"Task:         {data.get('task', '')}")
    print(f"Status:       {data.get('status', '')}")
    print(f"Agent:        {data.get('target_agent', '')}")
    print(f"Complexity:   {data.get('complexity_score', '?')}/10")
    if data.get("files_hint"):
        print(f"Files hint:   {', '.join(data['files_hint'])}")
    if data.get("stack_hint"):
        print(f"Stack:        {', '.join(data['stack_hint'])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fast track para tareas simples. Omite planner, writer y plan-reviewer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python3 .claude/hooks/quick-execute.py "Cambiar color boton a rojo"
  python3 .claude/hooks/quick-execute.py "Validar email en endpoint signup" --agent backend
  python3 .claude/hooks/quick-execute.py "Refactorizar modulo auth" --full-plan
  python3 .claude/hooks/quick-execute.py --status
        """,
    )
    parser.add_argument("task", nargs="?", help="Descripcion de la tarea a ejecutar.")
    parser.add_argument("--full-plan", action="store_true",
                        help="Forzar flujo completo (reader → planner → writer → execute-plan).")
    parser.add_argument("--agent", choices=["frontend", "backend", "both"],
                        help="Forzar agente objetivo. Si no se indica, se infiere de la tarea.")
    parser.add_argument("--force", action="store_true",
                        help="Ejecutar en modo quick aunque la tarea parezca compleja.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra el score y las razones sin escribir el dispatch ni el approval.")
    parser.add_argument("--status", action="store_true",
                        help="Ver estado del ultimo quick-dispatch.")
    args = parser.parse_args()

    if args.status:
        return show_status()

    if not args.task:
        parser.print_help()
        return 1

    task = args.task.strip()

    # ── Flujo completo solicitado explicitamente ───────────────────────────────
    if args.full_plan:
        print("Modo flujo completo.")
        print("Pasos a seguir:")
        print("  1. Invoca el agente reader")
        print("  2. Revisa reader-context.json")
        print("  3. python3 .claude/hooks/approve-plan.py approve --by 'tu nombre'")
        print("  4. python3 .claude/hooks/execute-plan.py")
        return 0

    # ── Evaluacion de complejidad ──────────────────────────────────────────────
    score, reasons = compute_complexity(task)

    THRESHOLD_WARN  = 5   # advertir pero dejar ejecutar con confirmacion
    THRESHOLD_BLOCK = 8   # bloquear — muy probablemente necesita flujo completo

    if args.dry_run:
        print(f"Score:   {score}/10")
        if reasons:
            print("Razones:")
            for r in reasons:
                print(f"  - {r}")
        else:
            print("Razones: ninguna (tarea simple)")
        inferred = args.agent or detect_agent(task)
        print(f"Agente:  {inferred}")
        if score >= THRESHOLD_BLOCK:
            print("Resultado: BLOQUEADO — necesita flujo completo (o --force para ignorar)")
        elif score >= THRESHOLD_WARN:
            print("Resultado: ADVERTENCIA — ejecutable en quick con posible friccion")
        else:
            print("Resultado: OK para fast track")
        return 0

    if score >= THRESHOLD_BLOCK and not args.force:
        print("=" * 60)
        print("TAREA COMPLEJA — Se recomienda el flujo completo")
        print("=" * 60)
        print(f"Complejidad estimada: {score}/10")
        print("Razones:")
        for r in reasons:
            print(f"  - {r}")
        print()
        print("Opciones:")
        print("  Flujo completo (recomendado):")
        print("    Invoca el agente reader, luego execute-plan.py")
        print()
        print("  Forzar fast track igualmente:")
        print(f"    python3 .claude/hooks/quick-execute.py \"{task}\" --force")
        # Escribe dispatch bloqueado para trazabilidad
        write_json(DISPATCH_PATH, {
            "mode": "quick",
            "status": "blocked",
            "task": task,
            "target_agent": args.agent or detect_agent(task),
            "scope_constraint": "",
            "complexity_score": score,
            "reason": f"Complejidad {score}/10 supera el umbral. Razones: {'; '.join(reasons)}",
        })
        return 1

    if score >= THRESHOLD_WARN and not args.force:
        print(f"Advertencia: complejidad estimada {score}/10 ({'; '.join(reasons)}).")
        print("Continuando en modo quick. Usa --full-plan si prefieres el flujo completo.")
        print()

    # ── Deteccion de agente ────────────────────────────────────────────────────
    target_agent = args.agent or detect_agent(task)

    # ── Hints del MAP ──────────────────────────────────────────────────────────
    stack_hint, files_hint = load_map_hints(task)

    # ── Escribir quick-dispatch.json ───────────────────────────────────────────
    dispatch = {
        "mode": "quick",
        "status": "ready",
        "task": task,
        "target_agent": target_agent,
        "scope_constraint": (
            "Implementa SOLO el cambio descrito en 'task'. "
            "No refactorices, no agregues abstracciones, no toques archivos fuera del scope. "
            "Si el cambio requiere mas de 3 archivos o logica de negocio nueva, escala con status='escalated'."
        ),
        "complexity_score": score,
    }
    if stack_hint:
        dispatch["stack_hint"] = stack_hint
    if files_hint:
        dispatch["files_hint"] = files_hint

    write_json(DISPATCH_PATH, dispatch)
    vr = validate_artifact("quick-dispatch.json", dispatch)
    if not vr.ok:
        print(vr.format())
        return 1
    if vr.warnings:
        print(vr.format_warnings())

    # ── Auto-aprobar ───────────────────────────────────────────────────────────
    write_json(APPROVAL_PATH, {
        "status": "approved",
        "approved_by": "quick-execute (auto)",
        "notes": f"Auto-aprobado en modo quick. Complejidad: {score}/10.",
    })

    # ── Output ────────────────────────────────────────────────────────────────
    print("=" * 60)
    print("FAST TRACK listo")
    print("=" * 60)
    print(f"Tarea:        {task}")
    print(f"Agente:       {target_agent}")
    print(f"Complejidad:  {score}/10")
    if files_hint:
        print(f"Files hint:   {', '.join(files_hint)}")
    if stack_hint:
        print(f"Stack:        {', '.join(stack_hint[:4])}")
    print()
    print("Siguiente paso:")
    if target_agent == "both":
        print("  Invoca el agente backend y despues el agente frontend.")
        print("  Ambos leeran quick-dispatch.json.")
    else:
        print(f"  Invoca el agente {target_agent}.")
        print(f"  Leera .claude/runtime/quick-dispatch.json directamente.")
    print()
    print("Si el agente devuelve status='escalated', usa el flujo completo:")
    print("  Invoca reader, luego execute-plan.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
