"""FastAPI dependencies: one SQLite connection per request and the calling principal."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from memory_agent import auth, db


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


def current_principal(request: Request, conn: Conn) -> auth.Principal:
    scheme, _, key = request.headers.get("authorization", "").partition(" ")
    return auth.principal_for_key(conn, key.strip() if scheme.lower() == "bearer" else None)


CurrentPrincipal = Annotated[auth.Principal, Depends(current_principal)]
