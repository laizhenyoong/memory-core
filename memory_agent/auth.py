"""API-key principals and authorization. No FastAPI imports here."""

import hashlib
import logging
import secrets
import sqlite3
import string
from dataclasses import dataclass, field

from memory_agent import db, policy
from memory_agent.errors import AccessDenied, Unauthorized

log = logging.getLogger(__name__)

KEY_PREFIX = "mak_"
KEY_ALPHABET = string.ascii_letters + string.digits
ADMIN_POLICY = {
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}],
}


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    policies: list[dict] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def variables(self) -> dict[str, str]:
        return {"principal.id": self.id} | {f"principal.tag/{k}": v for k, v in self.tags.items()}


def new_key() -> str:
    return KEY_PREFIX + "".join(secrets.choice(KEY_ALPHABET) for _ in range(32))


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def principal_for_key(conn: sqlite3.Connection, key: str | None) -> Principal:
    if not key:
        raise Unauthorized("Missing API key")
    row = conn.execute(
        "SELECT id, name, policies, tags FROM principals WHERE key_hash = ? AND disabled = 0",
        (hash_key(key),),
    ).fetchone()
    if row is None:
        raise Unauthorized("The API key is invalid or disabled")
    return Principal(row["id"], row["name"], db.loads(row["policies"]), db.loads(row["tags"]))


def authorize(
    principal: Principal, action: str, resource: str, context: dict[str, str] | None = None
) -> None:
    if policy.is_allowed(principal.policies, action, resource, context, principal.variables):
        return
    log.warning(
        "access denied principal=%s action=%s resource=%s context=%s",
        principal.id,
        action,
        resource,
        context or {},
    )
    raise AccessDenied(f"{principal.id} is not authorized to perform {action} on {resource}")


def bootstrap_admin(conn: sqlite3.Connection, admin_key: str | None) -> str | None:
    """Create the admin principal when none exist. Returns the key only if it was generated."""
    with conn:
        if conn.execute("SELECT 1 FROM principals LIMIT 1").fetchone():
            return None
        key = admin_key or new_key()
        ts = db.now()
        conn.execute(
            "INSERT INTO principals (id, name, key_hash, policies, tags, created_at, updated_at)"
            " VALUES (?, 'admin', ?, ?, '{}', ?, ?)",
            (db.new_id("prn"), hash_key(key), db.dumps([ADMIN_POLICY]), ts, ts),
        )
    log.info("admin principal created")
    return None if admin_key else key
