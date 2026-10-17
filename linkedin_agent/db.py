import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Status: draft -> approved -> published | rejected
SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'draft',
    text TEXT NOT NULL,
    topic TEXT,
    source_url TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT,
    linkedin_id TEXT
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def add_draft(conn, text, topic=None, source_url=None):
    cur = conn.execute(
        "INSERT INTO posts (text, topic, source_url, created_at) VALUES (?, ?, ?, ?)",
        (text, topic, source_url, _now()),
    )
    conn.commit()
    return cur.lastrowid


def list_posts(conn, status=None):
    if status:
        return conn.execute("SELECT * FROM posts WHERE status=? ORDER BY id", (status,)).fetchall()
    return conn.execute("SELECT * FROM posts ORDER BY id").fetchall()


def set_status(conn, post_id, status):
    conn.execute("UPDATE posts SET status=? WHERE id=?", (status, post_id))
    conn.commit()


def update_text(conn, post_id, text):
    conn.execute("UPDATE posts SET text=? WHERE id=?", (text, post_id))
    conn.commit()


def mark_published(conn, post_id, linkedin_id):
    conn.execute(
        "UPDATE posts SET status='published', published_at=?, linkedin_id=? WHERE id=?",
        (_now(), linkedin_id, post_id),
    )
    conn.commit()


def used_urls(conn):
    return {r["source_url"] for r in conn.execute("SELECT source_url FROM posts WHERE source_url IS NOT NULL")}
