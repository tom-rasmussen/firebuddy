import pytest

from firebuddy import config, sms


@pytest.fixture(autouse=True)
def clear_outbox():
    sms.clear_outbox()
    yield
    sms.clear_outbox()


def test_send_defaults_to_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(config, "DRY_RUN", True)
    monkeypatch.setattr(config, "SMS_ALLOWLIST", [])
    sms.send("+15551234567", "hello")
    assert sms.OUTBOX == [("+15551234567", "hello")]
    assert "DRY RUN" in capsys.readouterr().out


def test_send_blocked_when_not_allowlisted_even_if_dry_run_false(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "SMS_ALLOWLIST", [])
    called = []
    monkeypatch.setattr(sms, "_send_real", lambda to, body: called.append((to, body)))
    sms.send("+15551234567", "hello")
    assert called == []
    assert sms.OUTBOX == [("+15551234567", "hello")]  # fell back to dry run


def test_send_real_called_when_allowlisted_and_not_dry_run(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "SMS_ALLOWLIST", ["+15551234567"])
    called = []
    monkeypatch.setattr(sms, "_send_real", lambda to, body: called.append((to, body)))
    sms.send("+15551234567", "hello")
    assert called == [("+15551234567", "hello")]


def test_send_real_failure_does_not_raise(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "SMS_ALLOWLIST", ["+15551234567"])
    monkeypatch.setattr(config, "TWILIO_ACCOUNT_SID", "bad")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "bad")
    monkeypatch.setattr(config, "TWILIO_FROM_NUMBER", "+10000000000")

    class FakeMessages:
        def create(self, **kwargs):
            raise RuntimeError("simulated twilio failure")

    class FakeClient:
        def __init__(self, *a, **kw):
            self.messages = FakeMessages()

    import twilio.rest

    monkeypatch.setattr(twilio.rest, "Client", FakeClient)
    sms.send("+15551234567", "hello")  # must not raise


def test_verify_twilio_signature_delegates_to_twilio_validator(monkeypatch):
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "sekrit")
    calls = []

    class FakeValidator:
        def __init__(self, token):
            calls.append(token)

        def validate(self, url, params, signature):
            calls.append((url, params, signature))
            return True

    import twilio.request_validator

    monkeypatch.setattr(twilio.request_validator, "RequestValidator", FakeValidator)
    ok = sms.verify_twilio_signature("https://example.com/sms", {"Body": "hi"}, "sig123")
    assert ok is True
    assert calls[0] == "sekrit"
    assert calls[1] == ("https://example.com/sms", {"Body": "hi"}, "sig123")
