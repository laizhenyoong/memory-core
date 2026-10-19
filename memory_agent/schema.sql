CREATE TABLE IF NOT EXISTS memories (
  id                TEXT PRIMARY KEY,
  name              TEXT NOT NULL UNIQUE,
  description       TEXT,
  event_expiry_days INTEGER NOT NULL,
  status            TEXT NOT NULL,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategies (
  id                    TEXT PRIMARY KEY,
  memory_id             TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  name                  TEXT NOT NULL,
  description           TEXT,
  type                  TEXT NOT NULL,
  namespaces            TEXT NOT NULL,
  reflection_namespaces TEXT,
  config                TEXT NOT NULL DEFAULT '{}',
  created_at            TEXT NOT NULL,
  updated_at            TEXT NOT NULL,
  UNIQUE (memory_id, name)
);

CREATE TABLE IF NOT EXISTS events (
  id            TEXT PRIMARY KEY,
  memory_id     TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  actor_id      TEXT NOT NULL,
  session_id    TEXT NOT NULL,
  branch_name   TEXT NOT NULL DEFAULT 'main',
  root_event_id TEXT,
  event_ts      TEXT NOT NULL,
  payload       TEXT NOT NULL,
  metadata      TEXT NOT NULL DEFAULT '{}',
  expires_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_scope
  ON events (memory_id, actor_id, session_id, branch_name, event_ts);
CREATE INDEX IF NOT EXISTS events_expiry ON events (expires_at);

CREATE TABLE IF NOT EXISTS memory_records (
  id          TEXT PRIMARY KEY,
  memory_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  strategy_id TEXT,
  namespace   TEXT NOT NULL,
  content     TEXT NOT NULL,
  metadata    TEXT NOT NULL DEFAULT '{}',
  embedding   BLOB,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memory_records_namespace ON memory_records (memory_id, namespace);

CREATE TABLE IF NOT EXISTS principals (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  key_hash   TEXT NOT NULL UNIQUE,
  policies   TEXT NOT NULL DEFAULT '[]',
  tags       TEXT NOT NULL DEFAULT '{}',
  disabled   INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id          TEXT PRIMARY KEY,
  memory_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
  actor_id    TEXT NOT NULL,
  session_id  TEXT NOT NULL,
  kind        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',
  attempts    INTEGER NOT NULL DEFAULT 0,
  error       TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs (status, created_at);

CREATE TABLE IF NOT EXISTS cursors (
  strategy_id   TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
  actor_id      TEXT NOT NULL,
  session_id    TEXT NOT NULL,
  last_event_ts TEXT,
  pending_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (strategy_id, actor_id, session_id)
);

CREATE TABLE IF NOT EXISTS episode_turns (
  strategy_id  TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
  actor_id     TEXT NOT NULL,
  session_id   TEXT NOT NULL,
  turn_id      TEXT NOT NULL,
  summary_turn TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  PRIMARY KEY (strategy_id, actor_id, session_id, turn_id)
);
