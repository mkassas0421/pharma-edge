"""Health endpoint: DB probe + scheduler job introspection."""

from app.tasks.scheduler import scheduler


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert "timestamp" in body


def test_health_reports_scheduler_jobs(client):
    """The scheduler_jobs key must exist (empty when not started in tests)."""
    r = client.get("/health")
    assert r.status_code == 200
    assert "scheduler_jobs" in r.json()
    assert isinstance(r.json()["scheduler_jobs"], dict)


def test_scheduler_introspection_without_start():
    """get_jobs() must not raise on a never-started scheduler."""
    assert isinstance(scheduler.get_jobs(), list)
