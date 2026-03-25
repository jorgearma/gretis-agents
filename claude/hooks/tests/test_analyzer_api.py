"""Tests para analyzers/api.py — genera API_MAP.json."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers import core
from analyzers.api import run


def _make_flask_api(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==3.1.0\n")
    bp_dir = tmp_path / "blueprints"
    bp_dir.mkdir()
    (bp_dir / "pedidos.py").write_text(
        'from flask import Blueprint\n'
        'from utils.auth import login_required\n'
        'bp = Blueprint("pedidos", __name__, url_prefix="/api/pedidos")\n\n'
        '@bp.route("/", methods=["GET"])\n'
        '@login_required\n'
        'def listar_pedidos():\n'
        '    pass\n\n'
        '@bp.route("/<int:pid>", methods=["PUT"])\n'
        'def actualizar_pedido(pid):\n'
        '    pass\n\n'
        '@bp.route("/webhook", methods=["POST"])\n'
        'def twilio_webhook():\n'
        '    pass\n'
    )
    (tmp_path / "utils").mkdir()
    (tmp_path / "utils" / "auth.py").write_text("def login_required(f): return f")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_returns_required_keys(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert "framework" in result
    assert "blueprints" in result
    assert "webhooks" in result
    assert "middleware_files" in result


def test_detects_flask_framework(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert result["framework"] == "Flask"


def test_detects_blueprint_with_endpoints(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert len(result["blueprints"]) >= 1
    bp = result["blueprints"][0]
    assert "name" in bp
    assert "file" in bp
    assert "prefix" in bp
    assert "endpoints" in bp
    assert len(bp["endpoints"]) >= 1


def test_webhook_classified_separately(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    # twilio_webhook must be in webhooks, not in normal endpoints
    all_endpoint_fns = [
        ep["function"]
        for bp in result["blueprints"]
        for ep in bp["endpoints"]
    ]
    webhook_fns = [w["function"] for w in result["webhooks"]]
    assert "twilio_webhook" in webhook_fns
    assert "twilio_webhook" not in all_endpoint_fns


def test_auth_required_detected(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    # listar_pedidos has @login_required
    for bp in result["blueprints"]:
        for ep in bp["endpoints"]:
            if ep["function"] == "listar_pedidos":
                assert ep["auth_required"] == True


def test_empty_project_returns_empty_structure(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run(tmp_path, files, stack)
    assert result["framework"] is None
    assert result["blueprints"] == []
    assert result["webhooks"] == []
