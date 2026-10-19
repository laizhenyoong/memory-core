"""Control-plane logic for memories and their strategies. Strategies are stored, not run, yet."""

import sqlite3

from memory_agent import db, pagination
from memory_agent.errors import BadRequest, Conflict, NotFound
from memory_agent.models import (
    CreateMemoryInput,
    CustomConfiguration,
    ModifyStrategyInput,
    StrategyInput,
    UpdateMemoryInput,
)

STRATEGY_TYPES = {
    "semantic_memory_strategy": "SEMANTIC",
    "user_preference_memory_strategy": "USER_PREFERENCE",
    "summary_memory_strategy": "SUMMARY",
    "episodic_memory_strategy": "EPISODIC",
    "custom_memory_strategy": "CUSTOM",
}
OVERRIDE_BASES = {
    "semanticOverride": "SEMANTIC",
    "userPreferenceOverride": "USER_PREFERENCE",
    "summaryOverride": "SUMMARY",
    "episodicOverride": "EPISODIC",
}
ACTOR_NAMESPACE = "/strategy/{memoryStrategyId}/actors/{actorId}/"
DEFAULT_NAMESPACES = {
    "SEMANTIC": [ACTOR_NAMESPACE],
    "USER_PREFERENCE": [ACTOR_NAMESPACE],
    "SUMMARY": ["/strategy/{memoryStrategyId}/actors/{actorId}/sessions/{sessionId}/"],
    "EPISODIC": ["/strategy/{memoryStrategyId}/actor/{actorId}/"],
    None: [ACTOR_NAMESPACE],  # self-managed
}
DEFAULT_REFLECTION_NAMESPACES = ["/strategy/{memoryStrategyId}/"]


def create_memory(conn: sqlite3.Connection, data: CreateMemoryInput) -> dict:
    memory_id, ts = db.new_id("mem"), db.now()
    try:
        with conn:
            conn.execute(
                "INSERT INTO memories (id, name, description, event_expiry_days, status,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)",
                (memory_id, data.name, data.description, data.event_expiry_duration, ts, ts),
            )
            for item in data.memory_strategies:
                _insert_strategy(conn, memory_id, item, ts)
    except sqlite3.IntegrityError as exc:
        raise Conflict(f"A memory named {data.name} or a duplicate strategy name exists") from exc
    return get_memory(conn, memory_id)


def get_memory(conn: sqlite3.Connection, memory_id: str) -> dict:
    row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    if row is None:
        raise NotFound(f"Memory {memory_id} not found")
    strategies = conn.execute(
        "SELECT * FROM strategies WHERE memory_id = ? ORDER BY created_at, id", (memory_id,)
    ).fetchall()
    return {
        "id": row["id"],
        "name": row["name"],
        **({"description": row["description"]} if row["description"] is not None else {}),
        "eventExpiryDuration": row["event_expiry_days"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "strategies": [_strategy_view(s) for s in strategies],
    }


def list_memories(
    conn: sqlite3.Connection, next_token: str | None, max_results: int
) -> tuple[list[dict], str | None]:
    rows, token = pagination.page(
        conn,
        "SELECT id, name, status, created_at, updated_at FROM memories ORDER BY created_at, id",
        (),
        next_token,
        max_results,
    )
    summaries = [
        {
            "id": r["id"],
            "name": r["name"],
            "status": r["status"],
            "createdAt": r["created_at"],
            "updatedAt": r["updated_at"],
        }
        for r in rows
    ]
    return summaries, token


def update_memory(conn: sqlite3.Connection, memory_id: str, data: UpdateMemoryInput) -> dict:
    get_memory(conn, memory_id)
    ts = db.now()
    changes = data.memory_strategies
    try:
        with conn:
            if data.description is not None:
                conn.execute(
                    "UPDATE memories SET description = ? WHERE id = ?",
                    (data.description, memory_id),
                )
            if data.event_expiry_duration is not None:
                conn.execute(
                    "UPDATE memories SET event_expiry_days = ? WHERE id = ?",
                    (data.event_expiry_duration, memory_id),
                )
            if changes:
                for item in changes.delete_memory_strategies:
                    _strategy_row(conn, memory_id, item.memory_strategy_id)
                    conn.execute("DELETE FROM strategies WHERE id = ?", (item.memory_strategy_id,))
                for item in changes.modify_memory_strategies:
                    _modify_strategy(conn, memory_id, item, ts)
                for item in changes.add_memory_strategies:
                    _insert_strategy(conn, memory_id, item, ts)
            conn.execute("UPDATE memories SET updated_at = ? WHERE id = ?", (ts, memory_id))
    except sqlite3.IntegrityError as exc:
        raise Conflict("A strategy with that name already exists on this memory") from exc
    return get_memory(conn, memory_id)


def delete_memory(conn: sqlite3.Connection, memory_id: str) -> dict:
    get_memory(conn, memory_id)
    # Events, records, strategies and jobs go with it via ON DELETE CASCADE.
    with conn:
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    return {"memoryId": memory_id, "status": "DELETING"}


# --- strategies -------------------------------------------------------------


def _insert_strategy(
    conn: sqlite3.Connection, memory_id: str, item: StrategyInput, ts: str
) -> None:
    key, spec = item.unwrap()
    strategy_type = STRATEGY_TYPES[key]
    config: dict = {}
    base = strategy_type
    if strategy_type == "CUSTOM":
        config = _dump_configuration(spec.configuration)
        base = _custom_base(config)
    reflection = None
    if base == "EPISODIC":
        reflection_config = getattr(spec, "reflection_configuration", None)
        reflection = (
            reflection_config.namespaces if reflection_config else DEFAULT_REFLECTION_NAMESPACES
        )
    conn.execute(
        "INSERT INTO strategies (id, memory_id, name, description, type, namespaces,"
        " reflection_namespaces, config, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            db.new_id(spec.name),
            memory_id,
            spec.name,
            spec.description,
            strategy_type,
            db.dumps(spec.namespaces or DEFAULT_NAMESPACES[base]),
            db.dumps(reflection) if reflection else None,
            db.dumps(config),
            ts,
            ts,
        ),
    )


def _modify_strategy(
    conn: sqlite3.Connection, memory_id: str, item: ModifyStrategyInput, ts: str
) -> None:
    row = _strategy_row(conn, memory_id, item.memory_strategy_id)
    if item.description is not None:
        conn.execute(
            "UPDATE strategies SET description = ? WHERE id = ?", (item.description, row["id"])
        )
    if item.namespaces is not None:
        conn.execute(
            "UPDATE strategies SET namespaces = ? WHERE id = ?",
            (db.dumps(item.namespaces), row["id"]),
        )
    if item.configuration is not None:
        if row["type"] != "CUSTOM":
            raise BadRequest("configuration can only be modified on custom strategies")
        config = _dump_configuration(item.configuration)
        if set(config) != set(db.loads(row["config"])):
            raise BadRequest("a custom strategy cannot change its override or self-managed type")
        conn.execute("UPDATE strategies SET config = ? WHERE id = ?", (db.dumps(config), row["id"]))
    conn.execute("UPDATE strategies SET updated_at = ? WHERE id = ?", (ts, row["id"]))


def _strategy_row(conn: sqlite3.Connection, memory_id: str, strategy_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM strategies WHERE id = ? AND memory_id = ?", (strategy_id, memory_id)
    ).fetchone()
    if row is None:
        raise NotFound(f"Strategy {strategy_id} not found on memory {memory_id}")
    return row


def _dump_configuration(configuration: CustomConfiguration) -> dict:
    return configuration.model_dump(by_alias=True, exclude_none=True)


def _custom_base(config: dict) -> str | None:
    """Built-in type a custom strategy overrides; None means self-managed."""
    return next((OVERRIDE_BASES[k] for k in config if k in OVERRIDE_BASES), None)


def _strategy_view(row: sqlite3.Row) -> dict:
    view = {
        "strategyId": row["id"],
        "name": row["name"],
        "type": row["type"],
        "namespaces": db.loads(row["namespaces"]),
        "status": "ACTIVE",
    }
    if row["description"] is not None:
        view["description"] = row["description"]
    if row["reflection_namespaces"]:
        view["reflectionConfiguration"] = {"namespaces": db.loads(row["reflection_namespaces"])}
    if config := db.loads(row["config"]):
        view["configuration"] = config
    return view
