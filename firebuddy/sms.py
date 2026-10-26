from firebuddy import config

OUTBOX: list[tuple[str, str]] = []


def clear_outbox() -> None:
    OUTBOX.clear()


def _send_dry_run(to_phone: str, body: str) -> None:
    print(f"[DRY RUN] -> {to_phone}: {body}")
    OUTBOX.append((to_phone, body))


def _send_real(to_phone: str, body: str) -> None:
    import twilio.rest

    try:
        client = twilio.rest.Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        client.messages.create(to=to_phone, from_=config.TWILIO_FROM_NUMBER, body=body)
        OUTBOX.append((to_phone, body))
    except Exception as exc:  # never let one failed send kill the monitor loop
        print(f"[SMS SEND FAILED] -> {to_phone}: {exc}")


def send(to_phone: str, body: str) -> None:
    """Real sends require DRY_RUN=false AND the recipient to be in SMS_ALLOWLIST."""
    if not config.DRY_RUN and to_phone in config.SMS_ALLOWLIST:
        _send_real(to_phone, body)
    else:
        _send_dry_run(to_phone, body)


def verify_twilio_signature(url: str, params: dict, signature: str) -> bool:
    import twilio.request_validator

    validator = twilio.request_validator.RequestValidator(config.TWILIO_AUTH_TOKEN)
    return validator.validate(url, params, signature)
