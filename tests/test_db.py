from memory_agent import db

TABLES = {
    "memories",
    "strategies",
    "events",
    "memory_records",
    "principals",
    "jobs",
    "cursors",
    "episode_turns",
}


def test_init_db_creates_all_tables_and_is_idempotent(tmp_path):
    path = str(tmp_path / "memory.db")
    db.init_db(path)
    db.init_db(path)

    conn = db.connect(path)
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert TABLES <= names


def test_new_id_has_prefix_and_ten_base36_chars():
    value = db.new_id("mem")
    prefix, suffix = value.split("-")
    assert prefix == "mem"
    assert len(suffix) == 10 and all(c in db.ID_ALPHABET for c in suffix)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
