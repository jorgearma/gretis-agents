# Plugin Improvements Design
**Date:** 2026-03-24
**Goal:** Reduce token cost per cycle and increase agent specialization.

---

## Context

The plugin orchestrates a multi-agent pipeline:

```
Reader → Planner → Writer → [Operator Gate] → Frontend/Backend → Reviewer
```

After review, four structural problems were identified that increase token consumption and reduce clarity.

---

## Changes

### 1. Slim down `reader.md`

**Problem:** `reader.md` is 4,105 lines. It contains routing logic AND repeats instructions already present in each specialized reader (`project-reader.md`, `db-reader.md`, `query-reader.md`, `ui-reader.md`). Every session loads all of this into context unnecessarily.

**Solution:** Rewrite `reader.md` as a lean routing agent. Its only job:
- Receive the user request
- Classify the domain (project / db / query / ui)
- Decide which specialized readers to activate
- Delegate and consolidate their outputs into `reader-context.json`

All domain-specific logic (what files to look for, what patterns to detect) stays in the specialized reader files. No duplication.

**Expected outcome:** `reader.md` reduced to ~50-80 lines. Token cost for the reader stage drops significantly.

---

### 2. Eliminate `orchestrator.md`

**Problem:** The orchestrator has no clear entry point in the pipeline. The `reader` already handles routing. The pipeline is sequential with JSON contracts — agents know their inputs and outputs. The orchestrator adds token cost without adding value.

**Solution:**
- Delete `.claude/agents/orchestrator.md`
- Remove `"orchestrator"` from the `agents` array in `plugin.json`
- Remove references to `orchestrator` as a valid `owner` in `plan.json` schema and `execution-brief.json` schema
- The `planner` and `writer` take full ownership of their stages

**Expected outcome:** One fewer agent loaded per session. Cleaner ownership in schemas.

---

### 3. Unified `result.json` with per-agent structure

**Problem:** Both `frontend` and `backend` agents write to the same `result.json`, overwriting each other. The `reviewer` cannot distinguish what each agent did.

**Solution:** Update `result.json` schema to accumulate results by agent:

```json
{
  "frontend": {
    "status": "success | partial | blocked",
    "summary": "string",
    "artifacts": ["list of modified files"],
    "next_steps": ["list of actions"]
  },
  "backend": {
    "status": "success | partial | blocked",
    "summary": "string",
    "artifacts": ["list of modified files"],
    "next_steps": ["list of actions"]
  }
}
```

Each key is optional — if only `backend` ran, only `backend` is present. The `reviewer` reads whichever keys exist.

Update `frontend.md`, `backend.md`, and `reviewer.md` to reference this new structure.

**Expected outcome:** Reviewer has full traceability. No data loss when both agents execute.

---

### 4. Selective `.gitignore` for `runtime/`

**Problem:** Runtime state files are committed to the repo, causing unnecessary git noise and potential merge conflicts in team scenarios.

**Solution:** Add to `.gitignore`:

```
# Plugin runtime state (regenerated each cycle)
.claude/runtime/plan.json
.claude/runtime/execution-brief.json
.claude/runtime/execution-brief.md
.claude/runtime/execution-dispatch.json
```

**Keep versioned:**
- `.claude/runtime/operator-approval.json` — approval history is meaningful to track

**Expected outcome:** Clean git history. No merge conflicts from runtime state.

---

## Files Affected

| File | Change |
|------|--------|
| `.claude/agents/reader.md` | Rewrite — routing only, ~50-80 lines |
| `.claude/agents/orchestrator.md` | Delete |
| `.claude/plugin.json` | Remove `orchestrator` from agents array |
| `.claude/schemas/result.json` | Update to per-agent structure |
| `.claude/schemas/plan.json` | Remove `orchestrator` from owner enum |
| `.claude/schemas/execution-brief.json` | Remove `orchestrator` from target_agents enum |
| `.claude/agents/frontend.md` | Update result output format |
| `.claude/agents/backend.md` | Update result output format |
| `.claude/agents/reviewer.md` | Update to read per-agent result structure |
| `.gitignore` | Add runtime state exclusions |

---

## Success Criteria

- `reader.md` is under 100 lines and contains no domain-specific logic
- `orchestrator.md` does not exist
- `result.json` schema has `frontend` and `backend` as top-level optional keys
- Running `git status` after a pipeline cycle shows no changes to runtime files (except `operator-approval.json`)
- `python3 .claude/hooks/pre-commit.py` passes after all changes
