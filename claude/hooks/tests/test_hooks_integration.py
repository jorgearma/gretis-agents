# claude/hooks/tests/test_hooks_integration.py
"""Verifica que los hooks modificados usan validate_artifact."""
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]


def _src(name: str) -> str:
    return (HOOKS_DIR / name).read_text(encoding="utf-8")


def test_execute_plan_no_required_fields_dict():
    source = _src("execute-plan.py")
    assert "_REQUIRED_FIELDS" not in source, "_REQUIRED_FIELDS debe haber sido eliminado"
    assert "validate_fields" not in source, "validate_fields debe haber sido eliminado"


def test_execute_plan_uses_validate_artifact():
    assert "validate_artifact" in _src("execute-plan.py")


def test_approve_plan_uses_validate_artifact():
    assert "validate_artifact" in _src("approve-plan.py")


def test_quick_execute_uses_validate_artifact():
    assert "validate_artifact" in _src("quick-execute.py")


def test_dispatch_reviewer_uses_validate_artifact():
    assert "validate_artifact" in _src("dispatch-reviewer.py")


def test_recover_cycle_uses_validate_artifact():
    assert "validate_artifact" in _src("recover-cycle.py")


def test_pre_commit_uses_validate_artifact():
    assert "validate_artifact" in _src("pre-commit.py")
