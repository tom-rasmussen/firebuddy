import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")

NWS_USER_AGENT = os.getenv("NWS_USER_AGENT", "FireBuddy/0.1 (tom.j.rasmussen@gmail.com)")

MONITOR_INTERVAL_SEC = int(os.getenv("MONITOR_INTERVAL_SEC", "300"))
DB_PATH = os.getenv("DB_PATH", "firebuddy.db")

FIREBUDDY_FIXTURES = os.getenv("FIREBUDDY_FIXTURES", "").strip()

DRY_RUN = _bool("DRY_RUN", "true")
SMS_ALLOWLIST = _list("SMS_ALLOWLIST")

EVAL_MAX_TURNS = int(os.getenv("EVAL_MAX_TURNS", "60"))

CACHE_TTL_SEC = 240
NOMINATIM_MIN_INTERVAL_SEC = 1.0


def fixtures_enabled() -> bool:
    return bool(FIREBUDDY_FIXTURES)
