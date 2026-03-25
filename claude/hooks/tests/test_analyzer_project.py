"""Tests para analyzers/project.py — genera PROJECT_MAP.json con routing index."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analyzers import core
from analyzers.project import run, DOMAIN_KEYWORDS


def _make_project(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==3.1.0\nSQLAlchemy==2.0.38\n")
    (tmp_path / "main.py").write_text('"""Entry point."""\ndef create_app(): pass')
    (tmp_path / "blueprints").mkdir()
    (tmp_path / "blueprints" / "pedidos.py").write_text(
        'from flask import Blueprint\nbp = Blueprint("pedidos", __name__)\n'
        '@bp.route("/", methods=["GET"])\ndef listar(): pass'
    )
    (tmp_path / "models.py").write_text(
        'class Pedido(Base):\n    __tablename__ = "pedidos"\n    id = Column(Integer)\n'
    )
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_creates_project_map_json(tmp_path):
    root, maps_dir = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert "domains" in result
    assert "name" in result
    assert "stack" in result
    assert "architecture" in result
    assert "entry_points" in result


def test_domains_section_has_required_keys(tmp_path):
    root, _ = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    for domain_name, domain_data in result["domains"].items():
        assert "map" in domain_data, f"{domain_name} missing 'map'"
        assert "reader" in domain_data, f"{domain_name} missing 'reader'"
        assert "summary" in domain_data, f"{domain_name} missing 'summary'"
        assert "trigger_keywords" in domain_data, f"{domain_name} missing 'trigger_keywords'"
        assert isinstance(domain_data["trigger_keywords"], list)
        assert len(domain_data["trigger_keywords"]) > 0


def test_result_has_no_structure_key(tmp_path):
    root, _ = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert "structure" not in result, "PROJECT_MAP no debe tener 'structure'"


def test_all_6_domains_present(tmp_path):
    root, _ = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    expected = {"db", "query", "ui", "api", "services", "jobs"}
    for domain in expected:
        assert domain in result["domains"], f"Dominio '{domain}' falta en domains"


def test_summary_graceful_when_map_missing(tmp_path):
    """Cuando el MAP de un dominio no existe, summary debe explicar que falta."""
    root, _ = _make_project(tmp_path)
    # No pre-existing domain MAPs — they are not created in _make_project
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    for domain_name, domain_data in result["domains"].items():
        summary = domain_data["summary"]
        assert isinstance(summary, str), f"{domain_name}: summary debe ser string"
        assert len(summary) > 0, f"{domain_name}: summary no debe ser vacío"
        # When MAP is missing, summary should mention it
        assert "MAP" in summary or "map" in summary or "analyze" in summary, (
            f"{domain_name}: summary debería mencionar que el MAP no fue generado, got: {summary!r}"
        )


def test_project_map_has_modules_and_problems(tmp_path):
    """PROJECT_MAP debe tener modules (dict por rol) y problems (lista)."""
    from analyzers.core import walk_repo, detect_stack
    from analyzers.project import run

    # Crear estructura mínima
    (tmp_path / "app.py").write_text('"""Entry point."""\nfrom flask import Flask\napp = Flask(__name__)\n')
    (tmp_path / "controllers").mkdir()
    (tmp_path / "controllers" / "auth.py").write_text('"""Auth controller."""\ndef login():\n    pass\n')
    (tmp_path / ".git").mkdir()  # simular repo

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    assert "modules" in result, "PROJECT_MAP debe tener campo modules"
    assert isinstance(result["modules"], dict), "modules debe ser un dict"
    assert "problems" in result, "PROJECT_MAP debe tener campo problems"
    assert isinstance(result["problems"], list), "problems debe ser una lista"

def test_project_map_modules_have_required_fields(tmp_path):
    """Cada módulo en modules debe tener path, purpose, search_keywords, symbols, test_file, related_to."""
    from analyzers.core import walk_repo, detect_stack
    from analyzers.project import run

    (tmp_path / "controllers").mkdir()
    (tmp_path / "controllers" / "auth.py").write_text('"""Auth handler."""\ndef login(): pass\n')
    (tmp_path / ".git").mkdir()

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    for role, entries in result["modules"].items():
        for entry in entries:
            for field in ("path", "purpose", "search_keywords", "symbols", "test_file", "related_to"):
                assert field in entry, f"modules[{role}][].{field} ausente"
