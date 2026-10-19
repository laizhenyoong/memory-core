import base64
import sqlite3

from memory_agent.errors import BadRequest

DEFAULT_MAX_RESULTS = 20
MAX_RESULTS = 100


def page(
    conn: sqlite3.Connection, sql: str, params: tuple, next_token: str | None, max_results: int
) -> tuple[list[sqlite3.Row], str | None]:
    """Run `sql` (which must have a stable ORDER BY) and return one page plus the next token."""
    offset = _decode(next_token)
    rows = conn.execute(f"{sql} LIMIT ? OFFSET ?", (*params, max_results + 1, offset)).fetchall()
    if len(rows) > max_results:
        return rows[:max_results], _encode(offset + max_results)
    return rows, None


def _encode(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _decode(token: str | None) -> int:
    if not token:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(token.encode()).decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise BadRequest("Invalid nextToken") from exc
    if offset < 0:
        raise BadRequest("Invalid nextToken")
    return offset
