import pytest
from fastapi.testclient import TestClient

from firebuddy import app as app_module
from firebuddy import config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "DRY_RUN", True)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "FIREBUDDY_FIXTURES", "")
    with TestClient(app_module.app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_sms_webhook_help_command(client):
    r = client.post("/sms", data={"From": "+15559990000", "Body": "HELP"})
    assert r.status_code == 200
    assert "<Response>" in r.text


def test_sms_webhook_onboarding(client):
    r1 = client.post("/sms", data={"From": "+15559990001", "Body": "hi"})
    assert r1.status_code == 200
