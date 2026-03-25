"""Tests para analyzers/core.py — infraestructura compartida."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers.core import (
    FileInfo, FunctionInfo, ModelInfo, ProjectSummary,
    walk_repo, detect_stack, git_hotspots, git_cochange,
    IGNORE_DIRS, SOURCE_EXTS, ROLE_PATTERNS,
)


def test_fileinfo_defaults():
    fi = FileInfo(rel_path="main.py", language="python", role="entry_point", size=100)
    assert fi.classes == []
    assert fi.functions == []
    assert fi.has_db_access == False
    assert fi.function_infos == []


def test_walk_repo_returns_fileinfos(tmp_path):
    (tmp_path / "app.py").write_text("def hello(): pass")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "foo.js").write_text("// ignored")
    files = walk_repo(tmp_path)
    paths = [f.rel_path for f in files]
    assert any("app.py" in p for p in paths)
    assert not any("node_modules" in p for p in paths)


def test_walk_repo_parses_python_functions(tmp_path):
    (tmp_path / "service.py").write_text(
        "def create_order(): pass\ndef cancel_order(): pass\n"
    )
    files = walk_repo(tmp_path)
    svc = next(f for f in files if "service.py" in f.rel_path)
    assert "create_order" in svc.functions
    assert "cancel_order" in svc.functions


def test_detect_stack_from_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==3.1.0\nSQLAlchemy==2.0.38\n")
    stack = detect_stack(tmp_path)
    assert "Flask" in stack
    assert "SQLAlchemy" in stack


def test_git_hotspots_returns_empty_without_git(tmp_path):
    result = git_hotspots(tmp_path)
    assert result == []


def test_git_cochange_returns_empty_without_git(tmp_path):
    result = git_cochange(tmp_path)
    assert result == {}
