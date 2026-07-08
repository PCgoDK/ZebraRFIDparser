CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id TEXT,
    reader_id TEXT,
    antenna TEXT,
    event_type TEXT,
    event_time TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_event_time ON events(event_time);
CREATE INDEX IF NOT EXISTS idx_events_tag_id ON events(tag_id);
