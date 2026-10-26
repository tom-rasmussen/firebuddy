import json
import time
from pathlib import Path

import httpx

from firebuddy import config


class TTLCache:
    def __init__(self, ttl_sec: float = config.CACHE_TTL_SEC):
        self.ttl_sec = ttl_sec
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, key: str):
        hit = self._store.get(key)
        if hit is None:
            return None
        expires_at, value = hit
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: object) -> None:
        self._store[key] = (time.monotonic() + self.ttl_sec, value)


def http_client(timeout: float = 15.0) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": config.NWS_USER_AGENT}, timeout=timeout)


def load_fixture(name: str) -> dict:
    fixtures_dir = Path(config.FIREBUDDY_FIXTURES)
    path = fixtures_dir / name
    with open(path) as f:
        return json.load(f)
