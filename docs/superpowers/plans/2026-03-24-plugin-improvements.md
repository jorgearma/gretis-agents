# Plugin Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce token cost per pipeline cycle by slimming reader.md, removing the orchestrator agent, fixing per-agent result tracking, and gitignoring runtime state files.

**Architecture:** Thirteen files change across agents, schemas, hooks, and config. Each task is independent — schemas first (other files reference them), then agents, then infrastructure. No new files are created.

**Tech Stack:** Markdown agent definitions, JSON Schema (draft 2020-12), Python 3 hooks, git.

---

### Task 1: Add `.gitignore` entries for runtime state

**Files:**
- Modify: `.gitignore` (create if absent)

- [ ] **Step 1: Check if `.gitignore` exists**

Run: `ls /home/siemprearmando/agentes/losgretis/.gitignore 2>/dev/null || echo "not found"`

- [ ] **Step 2: Add runtime exclusions**

Append to `.gitignore` (create if missing):

```
# Plugin runtime state (regenerated each cycle — do not commit)
claude/runtime/plan.json
claude/runtime/execution-brief.json
claude/runtime/execution-brief.md
claude/runtime/execution-dispatch.json
claude/runtime/result.json
```

Do NOT add `claude/runtime/operator-approval.json` — it stays versioned.

- [ ] **Step 3: Verify operator-approval.json is still tracked**

Run: `git check-ignore -v claude/runtime/operator-approval.json`
Expected: no output (file is NOT ignored)

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore runtime state files, keep operator-approval versioned"
```

---

### Task 2: Fix `pre-commit.py` — paths, orchestrator, conditional runtime checks

**Files:**
- Modify: `claude/hooks/pre-commit.py`

- [ ] **Step 1: Read the file**

Read `claude/hooks/pre-commit.py` fully before editing.

- [ ] **Step 2: Rewrite `REQUIRED_PATHS`**

Replace the entire `REQUIRED_PATHS` list with corrected `claude/` paths (no dot prefix) and without `orchestrator.md`. Runtime files that are gitignored must be checked conditionally (not in this static list):

```python
ROOT = Path(__file__).resolve().parents[2]

# These files must always exist (versioned)
REQUIRED_PATHS = [
    ROOT / "CLAUDE.md",
    ROOT / "claude" / "plugin.json",
    ROOT / "claude" / "agents" / "readers" / "reader.md",
    ROOT / "claude" / "agents" / "readers" / "project-reader.md",
    ROOT / "claude" / "agents" / "readers" / "db-reader.md",
    ROOT / "claude" / "agents" / "readers" / "query-reader.md",
    ROOT / "claude" / "agents" / "readers" / "ui-reader.md",
    ROOT / "claude" / "agents" / "planner.md",
    ROOT / "claude" / "agents" / "writer.md",
    ROOT / "claude" / "agents" / "frontend.md",
    ROOT / "claude" / "agents" / "backend.md",
    ROOT / "claude" / "agents" / "reviewer.md",
    ROOT / "claude" / "maps" / "PROJECT_MAP.md",
    ROOT / "claude" / "maps" / "DB_MAP.md",
    ROOT / "claude" / "maps" / "QUERY_MAP.md",
    ROOT / "claude" / "maps" / "UI_MAP.md",
    ROOT / "claude" / "schemas" / "reader-context.json",
    ROOT / "claude" / "schemas" / "plan.json",
    ROOT / "claude" / "schemas" / "execution-brief.json",
    ROOT / "claude" / "schemas" / "execution-dispatch.json",
    ROOT / "claude" / "schemas" / "operator-approval.json",
    ROOT / "claude" / "schemas" / "result.json",
    ROOT / "claude" / "schemas" / "review.json",
    ROOT / "claude" / "runtime" / "operator-approval.json",
    ROOT / "claude" / "hooks" / "approve-plan.py",
    ROOT / "claude" / "hooks" / "execute-plan.py",
    ROOT / "claude" / "commands" / "implement-feature.md",
    ROOT / "claude" / "commands" / "review-change.md",
]

# Runtime JSON files that exist only after a cycle runs (gitignored — check only if present)
RUNTIME_JSON_FILES = [
    ROOT / "claude" / "runtime" / "execution-brief.json",
    ROOT / "claude" / "runtime" / "plan.json",
    ROOT / "claude" / "runtime" / "execution-dispatch.json",
]
```

- [ ] **Step 3: Rewrite `JSON_FILES`**

Replace `JSON_FILES` with only always-versioned JSON files:

```python
JSON_FILES = [
    ROOT / "claude" / "plugin.json",
    ROOT / "claude" / "schemas" / "reader-context.json",
    ROOT / "claude" / "schemas" / "plan.json",
    ROOT / "claude" / "schemas" / "execution-brief.json",
    ROOT / "claude" / "schemas" / "execution-dispatch.json",
    ROOT / "claude" / "schemas" / "operator-approval.json",
    ROOT / "claude" / "schemas" / "result.json",
    ROOT / "claude" / "schemas" / "review.json",
    ROOT / "claude" / "runtime" / "operator-approval.json",
]
```

- [ ] **Step 4: Update `main()` to validate runtime JSON conditionally**

After the existing `invalid_json` check, add:

```python
# Validate runtime JSON files only if they exist (gitignored, generated at runtime)
runtime_errors = [
    error
    for path in RUNTIME_JSON_FILES
    if path.exists() and (error := validate_json_file(path))
]
if runtime_errors:
    print("Invalid runtime JSON files detected:")
    for error in runtime_errors:
        print(f"- {error}")
    return 1
```

- [ ] **Step 5: Run hook to verify it passes**

Run: `python3 claude/hooks/pre-commit.py`
Expected: `Claude plugin structure ok`

- [ ] **Step 6: Commit**

```bash
git add claude/hooks/pre-commit.py
git commit -m "fix: pre-commit paths claude/ prefix, remove orchestrator, conditional runtime checks"
```

---

### Task 3: Update `claude/schemas/result.json` — per-agent structure

**Files:**
- Modify: `claude/schemas/result.json`

- [ ] **Step 1: Replace with per-agent schema**

Overwrite `claude/schemas/result.json` with:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ClaudeResult",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "frontend": {
      "type": "object",
      "additionalProperties": false,
      "required": ["status", "summary", "artifacts", "next_steps"],
      "properties": {
        "status": { "type": "string", "enum": ["success", "partial", "blocked"] },
        "summary": { "type": "string" },
        "artifacts": { "type": "array", "items": { "type": "string" } },
        "next_steps": { "type": "array", "items": { "type": "string" } }
      }
    },
    "backend": {
      "type": "object",
      "additionalProperties": false,
      "required": ["status", "summary", "artifacts", "next_steps"],
      "properties": {
        "status": { "type": "string", "enum": ["success", "partial", "blocked"] },
        "summary": { "type": "string" },
        "artifacts": { "type": "array", "items": { "type": "string" } },
        "next_steps": { "type": "array", "items": { "type": "string" } }
      }
    }
  }
}
```

No top-level `required`. Both `frontend` and `backend` are optional. If neither key is present, the reviewer handles it (returns `blocked`).

- [ ] **Step 2: Validate JSON is valid**

Run: `python3 -c "import json; json.load(open('claude/schemas/result.json')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add claude/schemas/result.json
git commit -m "feat: result.json schema per-agent structure (frontend/backend keys)"
```

---

### Task 4: Remove `orchestrator` from `plan.json` and `execution-brief.json` schemas

**Files:**
- Modify: `claude/schemas/plan.json` (line 62 — owner enum)
- Modify: `claude/schemas/execution-brief.json` (line 29 — target_agents enum; line 60 — implementation_steps owner enum)

- [ ] **Step 1: Edit `plan.json` — remove orchestrator from owner enum**

In `claude/schemas/plan.json`, find the `owner` enum inside `steps.items.properties`:

```json
"enum": ["orchestrator", "planner", "writer", "frontend", "backend", "reviewer"]
```

Replace with:

```json
"enum": ["planner", "writer", "frontend", "backend", "reviewer"]
```

- [ ] **Step 2: Edit `execution-brief.json` — remove orchestrator from target_agents enum**

In `claude/schemas/execution-brief.json`, find `target_agents.items.enum`:

```json
"enum": ["frontend", "backend", "reviewer", "orchestrator"]
```

Replace with:

```json
"enum": ["frontend", "backend", "reviewer"]
```

- [ ] **Step 3: Edit `execution-brief.json` — remove orchestrator from implementation_steps owner enum**

Find `implementation_steps.items.properties.owner.enum`:

```json
"enum": ["frontend", "backend", "reviewer", "orchestrator"]
```

Replace with:

```json
"enum": ["frontend", "backend", "reviewer"]
```

- [ ] **Step 4: Validate both files**

Run:
```bash
python3 -c "import json; json.load(open('claude/schemas/plan.json')); print('plan ok')"
python3 -c "import json; json.load(open('claude/schemas/execution-brief.json')); print('brief ok')"
```
Expected: `plan ok` then `brief ok`

- [ ] **Step 5: Commit**

```bash
git add claude/schemas/plan.json claude/schemas/execution-brief.json
git commit -m "fix: remove orchestrator from plan and execution-brief schemas"
```

---

### Task 5: Delete `orchestrator.md` and update `plugin.json`

**Files:**
- Delete: `claude/agents/orchestrator.md`
- Modify: `claude/plugin.json`

- [ ] **Step 1: Delete orchestrator agent**

Run: `rm claude/agents/orchestrator.md`

- [ ] **Step 2: Remove orchestrator from plugin.json agents array**

Read `claude/plugin.json`. Find the `agents` array. Remove `"orchestrator"` from it. The array should become:

```json
"agents": ["reader", "project-reader", "db-reader", "query-reader", "ui-reader", "planner", "writer", "frontend", "backend", "reviewer"]
```

- [ ] **Step 3: Validate plugin.json**

Run: `python3 -c "import json; json.load(open('claude/plugin.json')); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add claude/plugin.json
git rm claude/agents/orchestrator.md
git commit -m "feat: remove orchestrator agent from plugin"
```

---

### Task 6: Rewrite `claude/agents/readers/reader.md` — lean routing only

**Files:**
- Modify: `claude/agents/readers/reader.md`

- [ ] **Step 1: Read the current file to understand what to keep**

Read `claude/agents/readers/reader.md`. The routing rules (lines 34-48) and output format are the parts to keep. The preamble about responsibilities can be shortened. Everything referencing `orchestrator` must be removed.

- [ ] **Step 2: Rewrite the file**

Replace the entire content with a lean routing-only agent (~60 lines):

```markdown
# Reader

Eres el agente de entrada del plugin. Tu unico trabajo es clasificar la peticion y decidir que readers activar.

## Entradas

- la peticion del usuario
- `claude/maps/PROJECT_MAP.md` si la peticion es ambigua o transversal

## Trabajo

1. Lee la peticion y detecta el dominio principal.
2. Activa solo los readers necesarios (minimo uno, maximo los que aporten contexto real).
3. Consolida sus respuestas.
4. Devuelve el JSON para el `planner`.

## Reglas de enrutado

- `project-reader` → arquitectura, estructura, modulos, ownership, flujo general
- `db-reader` → tablas, relaciones, modelos, migraciones, persistencia
- `query-reader` → consultas, filtros, joins, rendimiento, acceso a datos
- `ui-reader` → pantallas, componentes, estados visuales, experiencia de usuario
- si la peticion mezcla dominios, elige un `primary_reader` segun donde ocurre el primer cambio real
- no actives readers que no aporten contexto real para esta peticion
- si un reader activo no encuentra contexto util, excluyelo de `selected_readers`

## Reglas de salida

- devuelve solo JSON valido, sin markdown ni texto adicional
- el JSON debe cumplir `claude/schemas/reader-context.json`
- no inventes rutas ni archivos si los readers no los sustentan
- usa `notes` solo si falta informacion en algun mapa o hay riesgo a comunicar al planner

## Salida esperada

```json
{
  "primary_reader": "project-reader",
  "selected_readers": ["project-reader"],
  "maps_used": ["PROJECT_MAP.md"],
  "files_to_open": ["src/app.py"],
  "files_to_review": ["src/models.py"],
  "reason": "La peticion afecta arquitectura general del modulo de autenticacion."
}
```
```

- [ ] **Step 3: Verify line count**

Run: `wc -l claude/agents/readers/reader.md`
Expected: under 70 lines

- [ ] **Step 4: Commit**

```bash
git add claude/agents/readers/reader.md
git commit -m "refactor: slim reader.md to lean routing agent, remove orchestrator ref"
```

---

### Task 7: Fix `writer.md` — remove orchestrator ref and fix `.claude/` paths

**Files:**
- Modify: `claude/agents/writer.md`

- [ ] **Step 1: Read the full file**

Read `claude/agents/writer.md` completely.

- [ ] **Step 2: Fix all `.claude/` path prefixes**

Run: `grep -n "\.claude/" claude/agents/writer.md`

For every occurrence of `.claude/runtime/` or `.claude/schemas/`, replace with `claude/runtime/` or `claude/schemas/`.

- [ ] **Step 3: Edit the orchestrator reference**

Find:
```
- si el plan no tiene pasos ejecutables para `frontend`, `backend`, `reviewer` u `orchestrator`, dejalo indicado en `notes`
```

Replace with:
```
- si el plan no tiene pasos ejecutables para `frontend`, `backend` o `reviewer`, dejalo indicado en `notes`
```

- [ ] **Step 4: Verify no `.claude/` refs remain**

Run: `grep -n "\.claude/" claude/agents/writer.md`
Expected: no output

- [ ] **Step 5: Verify no orchestrator refs remain**

Run: `grep -n "orchestrator" claude/agents/writer.md`
Expected: no output

- [ ] **Step 6: Commit**

```bash
git add claude/agents/writer.md
git commit -m "fix: remove orchestrator ref and fix runtime paths in writer.md"
```

---

### Task 8: Update `frontend.md` — write result under `frontend` key, fix paths

**Files:**
- Modify: `claude/agents/frontend.md`

- [ ] **Step 1: Read the full file**

Read `claude/agents/frontend.md` completely.

- [ ] **Step 2: Fix all `.claude/` path prefixes**

Run: `grep -n "\.claude/" claude/agents/frontend.md`

For every occurrence of `.claude/runtime/` or `.claude/schemas/`, replace with `claude/runtime/` or `claude/schemas/`.

- [ ] **Step 3: Update the result output section**

Find the section describing the output format (the result.json example). Update it so the agent writes under the `frontend` key:

Find the output example block — it will show a flat `{ "status": ..., "summary": ... }`. Replace with:

```json
{
  "frontend": {
    "status": "success",
    "summary": "descripcion de lo implementado",
    "artifacts": ["ruta/al/archivo/modificado.tsx"],
    "next_steps": []
  }
}
```

- [ ] **Step 4: Verify no `.claude/` refs remain**

Run: `grep -n "\.claude/" claude/agents/frontend.md`
Expected: no output

- [ ] **Step 5: Commit**

```bash
git add claude/agents/frontend.md
git commit -m "fix: frontend writes result under frontend key, fix runtime paths"
```

---

### Task 9: Update `backend.md` — write result under `backend` key, fix paths

**Files:**
- Modify: `claude/agents/backend.md`

- [ ] **Step 1: Read the full file**

Read `claude/agents/backend.md` completely.

- [ ] **Step 2: Fix all `.claude/` path prefixes**

Run: `grep -n "\.claude/" claude/agents/backend.md`

Replace every `.claude/runtime/` and `.claude/schemas/` with `claude/runtime/` and `claude/schemas/`.

- [ ] **Step 3: Update the result output section**

Find the output example. Replace flat structure with:

```json
{
  "backend": {
    "status": "success",
    "summary": "descripcion de lo implementado",
    "artifacts": ["ruta/al/archivo/modificado.py"],
    "next_steps": []
  }
}
```

- [ ] **Step 4: Verify no `.claude/` refs remain**

Run: `grep -n "\.claude/" claude/agents/backend.md`
Expected: no output

- [ ] **Step 5: Commit**

```bash
git add claude/agents/backend.md
git commit -m "fix: backend writes result under backend key, fix runtime paths"
```

---

### Task 10: Update `reviewer.md` — read per-agent result, fix paths

**Files:**
- Modify: `claude/agents/reviewer.md`

- [ ] **Step 1: Read the full file**

Read `claude/agents/reviewer.md` completely.

- [ ] **Step 2: Fix all `.claude/` path prefixes**

Run: `grep -n "\.claude/" claude/agents/reviewer.md`

Replace every `.claude/runtime/` and `.claude/schemas/` with `claude/runtime/` and `claude/schemas/`.

- [ ] **Step 3: Update the review inputs section**

Find the "Fuentes de verdad" or inputs section. Add `claude/runtime/result.json` if not present, and note it uses per-agent keys.

- [ ] **Step 4: Add per-agent reading behavior**

Find the "Como revisar" section. Add or update the first step to describe how to read result.json:

```
1. Lee `claude/runtime/result.json`. El archivo tiene claves opcionales `frontend` y `backend`, una por cada agente que ejecutó.
   - Si una clave no está presente, ese agente no ejecutó — no lo marques como error.
   - Si el archivo está vacío (`{}`), devuelve `blocked` con reason: "result.json está vacío — ningún agente produjo salida".
   - Revisa los artefactos de cada agente por separado antes de evaluar el resultado combinado.
```

- [ ] **Step 5: Verify no `.claude/` refs remain**

Run: `grep -n "\.claude/" claude/agents/reviewer.md`
Expected: no output

- [ ] **Step 6: Commit**

```bash
git add claude/agents/reviewer.md
git commit -m "fix: reviewer reads per-agent result.json structure, fix runtime paths"
```

---

### Task 11: Update `CLAUDE.md` — remove orchestrator from docs

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Read CLAUDE.md**

Read `CLAUDE.md` fully.

- [ ] **Step 2: Remove orchestrator from the pipeline diagram**

Find the pipeline diagram line:
```
Usuario → Reader → [readers especializados] → Planner → Writer → [Aprobacion operador] → execute-plan.py → Frontend/Backend → Reviewer
```
This diagram doesn't mention orchestrator directly — verify and leave as-is if correct.

- [ ] **Step 3: Remove orchestrator from the agents table**

Find the agents table with `| Agente | Entrada | Salida |`. Remove the row for `orchestrator` if present.

- [ ] **Step 4: Verify no orchestrator references remain**

Run: `grep -n "orchestrator" CLAUDE.md`
Expected: no output

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: remove orchestrator from CLAUDE.md"
```

---

### Task 12: Final validation

- [ ] **Step 1: Run pre-commit hook**

Run: `python3 claude/hooks/pre-commit.py`
Expected: `Claude plugin structure ok`

- [ ] **Step 2: Verify no orchestrator references anywhere**

Run: `grep -rn "orchestrator" claude/ CLAUDE.md`
Expected: no output

- [ ] **Step 3: Verify result.json schema structure**

Run: `python3 -c "import json; s=json.load(open('claude/schemas/result.json')); assert 'frontend' in s['properties']; assert 'backend' in s['properties']; assert 'required' not in s; print('schema ok')"`
Expected: `schema ok`

- [ ] **Step 4: Verify reader.md line count**

Run: `wc -l claude/agents/readers/reader.md`
Expected: under 100 lines

- [ ] **Step 5: Verify orchestrator.md is gone**

Run: `ls claude/agents/orchestrator.md 2>/dev/null || echo "correctly absent"`
Expected: `correctly absent`

- [ ] **Step 6: Verify no stray `.claude/` paths in any agent file**

Run: `grep -rn "\.claude/" claude/agents/`
Expected: no output

- [ ] **Step 7: Final commit if any loose changes**

```bash
git status
# commit anything uncommitted
```
