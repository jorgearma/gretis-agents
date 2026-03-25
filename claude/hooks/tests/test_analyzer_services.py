"""Tests para analyzers/services.py — genera SERVICES_MAP.json."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers import core
from analyzers.services import run


def _make_project_with_services(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\ntwilio==9.4.6\nredis==5.2.1\nsentry-sdk==2.54.0\n"
    )
    svc_dir = tmp_path / "services"
    svc_dir.mkdir()
    (svc_dir / "twilio_service.py").write_text(
        'import twilio\nTWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]\n'
        'def enviar_mensaje(to, body): pass\n'
        'def procesar_respuesta(data): pass\n'
    )
    (svc_dir / "cache_service.py").write_text(
        'import redis\nREDIS_URL = os.environ.get("REDIS_URL")\n'
        'def get_cache(key): pass\n'
        'def set_cache(key, value): pass\n'
    )
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_returns_required_keys(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert "integrations" in result


def test_detects_twilio(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    names = [i["name"] for i in result["integrations"]]
    assert "Twilio" in names


def test_integration_has_type(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    for integration in result["integrations"]:
        assert "type" in integration
        assert integration["type"] in (
            "sms", "email", "payments", "storage", "cache", "queue", "monitoring", "other"
        )


def test_integration_has_required_fields(tmp_path):
    """Each integration entry must have name, type, files, functions, env_vars."""
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    for integration in result["integrations"]:
        for key in ("name", "type", "files", "functions", "env_vars"):
            assert key in integration, f"integration missing '{key}': {integration}"


def test_integration_has_env_vars(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    twilio = next((i for i in result["integrations"] if i["name"] == "Twilio"), None)
    assert twilio is not None, "Twilio integration not found"
    assert "TWILIO_ACCOUNT_SID" in twilio.get("env_vars", [])


def test_empty_project_returns_empty_integrations(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run(tmp_path, files, stack)
    assert result == {"integrations": []}
