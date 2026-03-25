"""Tests para analyzers/core.py — infraestructura compartida."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers.core import (
    FileInfo, FunctionInfo, ModelInfo, ProjectSummary,
    walk_repo, detect_stack, git_hotspots, git_cochange,
    build_query_entry,
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


def test_build_query_entry_returns_required_keys(tmp_path):
    (tmp_path / "manager.py").write_text(
        "from database import db\n"
        "def get_pedido(id):\n"
        "    return db.session.query(Pedido).filter_by(id=id).first()\n"
    )
    files = walk_repo(tmp_path)
    mgr = next(f for f in files if "manager.py" in f.rel_path)
    entry = build_query_entry(mgr, files, {})
    assert "path" in entry
    assert "role" in entry
    assert "functions" in entry
    assert "query_examples" in entry


def _make_fi(rel_path: str) -> "FileInfo":
    from analyzers.core import FileInfo
    return FileInfo(rel_path=rel_path, language="python", role="controller", size=100)

def test_find_test_file_pytest_convention():
    from analyzers.core import find_test_file
    all_files = [
        _make_fi("controllers/auth.py"),
        _make_fi("tests/test_auth.py"),
    ]
    result = find_test_file("controllers/auth.py", all_files)
    assert result == "tests/test_auth.py"

def test_find_test_file_suffix_convention():
    from analyzers.core import find_test_file
    all_files = [
        _make_fi("services/stripe.py"),
        _make_fi("tests/stripe_test.py"),
    ]
    result = find_test_file("services/stripe.py", all_files)
    assert result == "tests/stripe_test.py"

def test_find_test_file_sibling_dir():
    from analyzers.core import find_test_file
    all_files = [
        _make_fi("blueprints/auth.py"),
        _make_fi("blueprints/tests/test_auth.py"),
    ]
    result = find_test_file("blueprints/auth.py", all_files)
    assert result == "blueprints/tests/test_auth.py"

def test_find_test_file_returns_none_when_missing():
    from analyzers.core import find_test_file
    all_files = [_make_fi("controllers/auth.py")]
    result = find_test_file("controllers/auth.py", all_files)
    assert result is None

def test_find_test_file_never_returns_self():
    from analyzers.core import find_test_file
    all_files = [_make_fi("tests/test_auth.py")]
    result = find_test_file("tests/test_auth.py", all_files)
    assert result is None
