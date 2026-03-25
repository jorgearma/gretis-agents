"""Tests para db.py, query.py, ui.py — lógica migrada de analyze-repo.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers import core
from analyzers.db import run as run_db
from analyzers.query import run as run_query
from analyzers.ui import run as run_ui


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
