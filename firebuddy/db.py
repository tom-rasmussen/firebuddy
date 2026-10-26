import json
import sqlite3
from contextlib import contextmanager

from firebuddy import config
from firebuddy.clock import now

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    state TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    label TEXT NOT NULL,
    address TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    radius_mi REAL NOT NULL DEFAULT 15,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS incident_state (
    place_id INTEGER NOT NULL REFERENCES places(id),
    incident_key TEXT NOT NULL,
    last_acres REAL,
    last_contained REAL,
    alerted_thresholds TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (place_id, incident_key)
);

CREATE TABLE IF NOT EXISTS sent_alerts (
    place_id INTEGER NOT NULL REFERENCES places(id),
    key TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    UNIQUE (place_id, key)
);

CREATE TABLE IF NOT EXISTS followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    place_id INTEGER NOT NULL REFERENCES places(id),
    due_at TEXT NOT NULL,
    note TEXT,
    done INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    direction TEXT NOT NULL,
    body TEXT NOT NULL,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    input TEXT NOT NULL,
    tool_calls TEXT NOT NULL DEFAULT '[]',
    final_text TEXT,
    validator_result TEXT,
    retries INTEGER NOT NULL DEFAULT 0,
    latency_ms REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    ts TEXT NOT NULL
);
"""


def connect(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def session(db_path: str | None = None):
    conn = connect(db_path)
    try:
        init_db(conn)
        yield conn
    finally:
        conn.close()


# --- users ---

def get_or_create_user(conn: sqlite3.Connection, phone: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    if row:
        return row
    conn.execute(
        "INSERT INTO users (phone, status, state, created_at) VALUES (?, 'active', NULL, ?)",
        (phone, now().isoformat()),
    )
    conn.commit()
    return conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()


def set_user_status(conn: sqlite3.Connection, user_id: int, status: str) -> None:
    conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
    conn.commit()


def set_user_state(conn: sqlite3.Connection, user_id: int, state: str | None) -> None:
    conn.execute("UPDATE users SET state = ? WHERE id = ?", (state, user_id))
    conn.commit()


# --- places ---

def add_place(
    conn: sqlite3.Connection,
    user_id: int,
    label: str,
    address: str,
    lat: float,
    lon: float,
    radius_mi: float = 15,
) -> sqlite3.Row:
    cur = conn.execute(
        "INSERT INTO places (user_id, label, address, lat, lon, radius_mi, active) "
        "VALUES (?, ?, ?, ?, ?, ?, 1)",
        (user_id, label, address, lat, lon, radius_mi),
    )
    conn.commit()
    return conn.execute("SELECT * FROM places WHERE id = ?", (cur.lastrowid,)).fetchone()


def list_places(conn: sqlite3.Connection, user_id: int, active_only: bool = True) -> list[sqlite3.Row]:
    if active_only:
        return conn.execute(
            "SELECT * FROM places WHERE user_id = ? AND active = 1 ORDER BY id", (user_id,)
        ).fetchall()
    return conn.execute("SELECT * FROM places WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()


def get_place(conn: sqlite3.Connection, place_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()


def remove_place(conn: sqlite3.Connection, place_id: int) -> None:
    conn.execute("UPDATE places SET active = 0 WHERE id = ?", (place_id,))
    conn.commit()


def set_radius(conn: sqlite3.Connection, place_id: int, radius_mi: float) -> None:
    conn.execute("UPDATE places SET radius_mi = ? WHERE id = ?", (radius_mi, place_id))
    conn.commit()


def list_active_places_all_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT places.*, users.phone AS user_phone, users.status AS user_status "
        "FROM places JOIN users ON users.id = places.user_id "
        "WHERE places.active = 1 AND users.status = 'active'"
    ).fetchall()


# --- incident_state (growth/containment tracking) ---

def get_incident_state(conn: sqlite3.Connection, place_id: int, incident_key: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM incident_state WHERE place_id = ? AND incident_key = ?",
        (place_id, incident_key),
    ).fetchone()


def upsert_incident_state(
    conn: sqlite3.Connection,
    place_id: int,
    incident_key: str,
    last_acres: float | None,
    last_contained: float | None,
    alerted_thresholds: list,
) -> None:
    conn.execute(
        "INSERT INTO incident_state (place_id, incident_key, last_acres, last_contained, alerted_thresholds) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(place_id, incident_key) DO UPDATE SET "
        "last_acres = excluded.last_acres, last_contained = excluded.last_contained, "
        "alerted_thresholds = excluded.alerted_thresholds",
        (place_id, incident_key, last_acres, last_contained, json.dumps(alerted_thresholds)),
    )
    conn.commit()


# --- sent_alerts (dedupe) ---

def already_sent(conn: sqlite3.Connection, place_id: int, key: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sent_alerts WHERE place_id = ? AND key = ?", (place_id, key)
    ).fetchone() is not None


def mark_sent(conn: sqlite3.Connection, place_id: int, key: str) -> bool:
    """Record that `key` was sent for `place_id`. Returns False if already sent (race-safe)."""
    try:
        conn.execute(
            "INSERT INTO sent_alerts (place_id, key, sent_at) VALUES (?, ?, ?)",
            (place_id, key, now().isoformat()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        return False


# --- followups ---

def schedule_followup(conn: sqlite3.Connection, user_id: int, place_id: int, due_at: str, note: str) -> sqlite3.Row:
    cur = conn.execute(
        "INSERT INTO followups (user_id, place_id, due_at, note, done) VALUES (?, ?, ?, ?, 0)",
        (user_id, place_id, due_at, note),
    )
    conn.commit()
    return conn.execute("SELECT * FROM followups WHERE id = ?", (cur.lastrowid,)).fetchone()


def due_followups(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT followups.*, users.phone AS user_phone FROM followups "
        "JOIN users ON users.id = followups.user_id "
        "WHERE followups.done = 0 AND followups.due_at <= ?",
        (now().isoformat(),),
    ).fetchall()


def mark_followup_done(conn: sqlite3.Connection, followup_id: int) -> None:
    conn.execute("UPDATE followups SET done = 1 WHERE id = ?", (followup_id,))
    conn.commit()


# --- messages ---

def log_message(conn: sqlite3.Connection, user_id: int, direction: str, body: str) -> None:
    conn.execute(
        "INSERT INTO messages (user_id, direction, body, ts) VALUES (?, ?, ?, ?)",
        (user_id, direction, body, now().isoformat()),
    )
    conn.commit()


def recent_messages(conn: sqlite3.Connection, user_id: int, limit: int = 12) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
    ).fetchall()
    return list(reversed(rows))


# --- agent_traces ---

def log_trace(
    conn: sqlite3.Connection,
    user_id: int,
    input_text: str,
    tool_calls: list,
    final_text: str | None,
    validator_result: str | None,
    retries: int,
    latency_ms: float | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> None:
    conn.execute(
        "INSERT INTO agent_traces "
        "(user_id, input, tool_calls, final_text, validator_result, retries, latency_ms, "
        "input_tokens, output_tokens, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            input_text,
            json.dumps(tool_calls),
            final_text,
            validator_result,
            retries,
            latency_ms,
            input_tokens,
            output_tokens,
            now().isoformat(),
        ),
    )
    conn.commit()


def last_traces(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM agent_traces ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
