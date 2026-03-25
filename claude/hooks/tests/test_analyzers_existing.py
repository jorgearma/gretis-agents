"""Tests para db.py, query.py, ui.py — lógica migrada de analyze-repo.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from analyzers import core
from analyzers.db import run as run_db
from analyzers.query import run as run_query
from analyzers.ui import run as run_ui


@pytest.fixture(autouse=True)
def reset_model_cache():
    """Reset the walk_repo models cache before each test to prevent cross-test contamination."""
    from analyzers import core as _core
    _core._walk_repo_models_cache.clear()
    yield
    _core._walk_repo_models_cache.clear()


def _make_flask_project(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\nSQLAlchemy==2.0.38\n"
    )
    (tmp_path / "models.py").write_text(
        'from sqlalchemy import Column, Integer, String\n'
        'from database import Base\n'
        'class Pedido(Base):\n'
        '    __tablename__ = "pedidos"\n'
        '    id = Column(Integer)\n'
        '    estado = Column(String)\n'
    )
    (tmp_path / "database.py").write_text("from sqlalchemy import create_engine")
    (tmp_path / "managers").mkdir()
    (tmp_path / "managers" / "pedido_manager.py").write_text(
        "from database import db\n"
        "def get_pedido(id):\n"
        "    return db.session.query(Pedido).filter_by(id=id).first()\n"
    )
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "pedidos.html").write_text("<html></html>")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_db_run_returns_required_keys(tmp_path):
    root, _ = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run_db(root, files, stack)
    assert "orm" in result
    assert "models" in result
    assert "connection_files" in result
    assert "migrations" in result


def test_db_run_detects_sqlalchemy_model(tmp_path):
    root, _ = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run_db(root, files, stack)
    model_names = [m["name"] for m in result["models"]]
    assert "Pedido" in model_names


def test_db_run_writes_file(tmp_path):
    root, maps_dir = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    run_db(root, files, stack)
    assert (maps_dir / "DB_MAP.json").exists()


def test_query_run_returns_required_keys(tmp_path):
    root, _ = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run_query(root, files, stack)
    assert "pattern" in result
    assert "files" in result
    assert "cochange_with_models" in result


def test_ui_run_returns_required_keys(tmp_path):
    root, _ = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run_ui(root, files, stack)
    assert "framework" in result
    assert "views" in result
    assert "routers" in result


def test_db_empty_project_writes_file(tmp_path):
    """Si no hay modelos, DB_MAP.json debe escribirse con arrays vacíos."""
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    # Proyecto sin modelos ni DB
    (tmp_path / "main.py").write_text("print('hello')")
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run_db(tmp_path, files, stack)
    assert (maps_dir / "DB_MAP.json").exists()
    assert isinstance(result["models"], list)
    assert isinstance(result["migrations"], list)
    assert isinstance(result["connection_files"], list)


def test_query_empty_project_writes_file(tmp_path):
    """Si no hay archivos con acceso a DB, QUERY_MAP.json debe escribirse."""
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    (tmp_path / "main.py").write_text("print('hello')")
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run_query(tmp_path, files, stack)
    assert (maps_dir / "QUERY_MAP.json").exists()
    assert isinstance(result["files"], list)
    assert isinstance(result["cochange_with_models"], list)


def test_ui_empty_project_writes_file(tmp_path):
    """Si no hay templates/componentes, UI_MAP.json debe escribirse."""
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    (tmp_path / "main.py").write_text("print('hello')")
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run_ui(tmp_path, files, stack)
    assert (maps_dir / "UI_MAP.json").exists()
    assert isinstance(result["views"], dict)
    assert isinstance(result["routers"], list)


def test_db_model_entry_has_required_subkeys(tmp_path):
    """Cada entrada en models debe tener name, table, file, fields, relationships."""
    root, _ = _make_flask_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run_db(root, files, stack)
    assert len(result["models"]) > 0, "Debe haber al menos un modelo detectado"
    for model_entry in result["models"]:
        for key in ("name", "table", "file", "fields", "relationships"):
            assert key in model_entry, f"model entry missing '{key}': {model_entry}"


def test_db_map_models_have_test_file(tmp_path):
    from analyzers.core import walk_repo, detect_stack
    from analyzers.db import run
    from analyzers import core as _core
    _core._walk_repo_models_cache.clear()

    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "user.py").write_text(
        "from sqlalchemy import Column, Integer, String\n"
        "from sqlalchemy.ext.declarative import declarative_base\n"
        "Base = declarative_base()\n"
        "class User(Base):\n    __tablename__ = 'users'\n    id = Column(Integer, primary_key=True)\n    email = Column(String)\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_user.py").write_text("def test_user_model(): pass\n")
    (tmp_path / ".git").mkdir()

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    assert result["models"], "debe detectar al menos un modelo"
    for model in result["models"]:
        assert "test_file" in model, f"modelo {model['name']} no tiene test_file"
