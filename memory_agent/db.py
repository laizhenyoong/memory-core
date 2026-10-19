import json
import secrets
import sqlite3
import string
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any

ID_ALPHABET = string.digits + string.ascii_lowercase


def new_id(prefix: str) -> str:
    return f"{prefix}-{''.join(secrets.choice(ID_ALPHABET) for _ in range(10))}"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def loads(value: str | None) -> Any:
    return None if value is None else json.loads(value)


def connect(path: str) -> sqlite3.Connection:
    # One connection per request; FastAPI may run setup and handler on different threads.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(path: str) -> None:
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(files("memory_agent").joinpath("schema.sql").read_text())
    finally:
        conn.close()
