"""Tests para analyzers/jobs.py — genera JOBS_MAP.json."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers import core
from analyzers.jobs import run


def _make_project_with_celery(tmp_path):
    (tmp_path / "requirements.txt").write_text("celery==5.3.0\nredis==5.2.1\n")
    (tmp_path / "tasks.py").write_text(
        'from celery import Celery\n'
        'app = Celery("tasks")\n\n'
        '@app.task\n'
        'def enviar_notificacion(user_id):\n'
        '    """Envía notificación por email al usuario."""\n'
        '    pass\n\n'
        '@app.task(bind=True)\n'
        'def procesar_pago(self, pedido_id):\n'
        '    pass\n'
    )
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_returns_required_keys(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert "scheduler" in result
    assert "jobs" in result
    assert "queues" in result


def test_detects_celery_scheduler(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert result["scheduler"] == "celery"


def test_detects_celery_tasks(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    job_fns = [j["function"] for j in result["jobs"]]
    assert "enviar_notificacion" in job_fns, f"enviar_notificacion not found in {job_fns}"
    assert "procesar_pago" in job_fns, f"procesar_pago not found in {job_fns}"


def test_empty_project_returns_null_scheduler(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run(tmp_path, files, stack)
    assert result == {"scheduler": None, "jobs": [], "queues": []}


def test_job_has_required_fields(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert len(result["jobs"]) > 0, "Expected at least one job detected"
    for job in result["jobs"]:
        assert "file" in job
        assert "function" in job
        assert "trigger" in job
        assert "schedule" in job
        assert "description" in job
        assert job["trigger"] in ("manual", "cron", "interval", "event", "startup")
