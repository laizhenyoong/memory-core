"""Principal CRUD. The raw API key is returned once, on creation; only its hash is stored."""

import sqlite3

from memory_agent import auth, db, pagination
from memory_agent.errors import NotFound
from memory_agent.models import CreatePrincipalInput, UpdatePrincipalInput


def create_principal(conn: sqlite3.Connection, data: CreatePrincipalInput) -> tuple[dict, str]:
    principal_id, key, ts = db.new_id("prn"), auth.new_key(), db.now()
    with conn:
        conn.execute(
            "INSERT INTO principals (id, name, key_hash, policies, tags, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                principal_id,
                data.name,
                auth.hash_key(key),
                db.dumps(data.policies),
                db.dumps(data.tags),
                ts,
                ts,
            ),
        )
    return get_principal(conn, principal_id), key


def get_principal(conn: sqlite3.Connection, principal_id: str) -> dict:
    row = conn.execute("SELECT * FROM principals WHERE id = ?", (principal_id,)).fetchone()
    if row is None:
        raise NotFound(f"Principal {principal_id} not found")
    return _view(row)


def list_principals(
    conn: sqlite3.Connection, next_token: str | None, max_results: int
) -> tuple[list[dict], str | None]:
    rows, token = pagination.page(
        conn, "SELECT * FROM principals ORDER BY created_at, id", (), next_token, max_results
    )
    return [_view(r) for r in rows], token


def update_principal(
    conn: sqlite3.Connection, principal_id: str, data: UpdatePrincipalInput
) -> dict:
    get_principal(conn, principal_id)
    columns = {
        "name": data.name,
        "policies": None if data.policies is None else db.dumps(data.policies),
        "tags": None if data.tags is None else db.dumps(data.tags),
        "disabled": None if data.disabled is None else int(data.disabled),
    }
    columns = {k: v for k, v in columns.items() if v is not None} | {"updated_at": db.now()}
    assignments = ", ".join(f"{column} = ?" for column in columns)
    with conn:
        conn.execute(
            f"UPDATE principals SET {assignments} WHERE id = ?", (*columns.values(), principal_id)
        )
    return get_principal(conn, principal_id)


def delete_principal(conn: sqlite3.Connection, principal_id: str) -> None:
    get_principal(conn, principal_id)
    with conn:
        conn.execute("DELETE FROM principals WHERE id = ?", (principal_id,))


def _view(row: sqlite3.Row) -> dict:
    return {
        "principalId": row["id"],
        "name": row["name"],
        "policies": db.loads(row["policies"]),
        "tags": db.loads(row["tags"]),
        "disabled": bool(row["disabled"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
