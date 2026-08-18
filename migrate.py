#!/usr/bin/env python3
"""
SQLite -> PostgreSQL migration for the Uploader bot.

Usage:
  Windows:
    set DATABASE_URL=postgresql://...
    set SQLITE_PATH=C:\path\to\uploader.db
    python migrate.py

  Railway:
    Add DATABASE_URL to the service.
    Put uploader.db in the working directory (or set SQLITE_PATH).
    python migrate.py

The migration is intentionally UPSERT-based and preserves the SQLite IDs/tokens.
It does NOT delete the source SQLite database.
"""

import os
import sqlite3
import sys
from pathlib import Path

try:
    import psycopg
    from psycopg import sql
except ImportError:
    print("ERROR: psycopg is not installed.")
    print("Install with: pip install 'psycopg[binary]>=3.2,<4'")
    sys.exit(1)

SQLITE_PATH = Path(os.getenv("SQLITE_PATH", "uploader.db"))
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL is not set.")
    sys.exit(1)

if not SQLITE_PATH.exists():
    print(f"ERROR: SQLite database not found: {SQLITE_PATH.resolve()}")
    sys.exit(1)

TABLES = [
    "users",
    "admins",
    "blocked_users",
    "settings",
    "bot_settings",
    "join_channels",
    "user_settings",
    "files",
    "groups",
    "group_items",
]

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    language TEXT DEFAULT 'fa',
    blocked INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS admins (
    user_id BIGINT PRIMARY KEY,
    added_by BIGINT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blocked_users (
    user_id BIGINT PRIMARY KEY,
    blocked_by BIGINT,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS join_channels (
    channel_id TEXT PRIMARY KEY,
    title TEXT,
    username TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    invite_url TEXT
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id BIGINT PRIMARY KEY,
    language TEXT DEFAULT 'fa',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS files (
    id BIGINT PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,
    owner_id BIGINT NOT NULL,
    file_id TEXT,
    file_name TEXT,
    file_size BIGINT DEFAULT 0,
    file_type TEXT,
    text_content TEXT,
    downloads BIGINT DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS groups (
    id BIGINT PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,
    owner_id BIGINT NOT NULL,
    title TEXT,
    downloads BIGINT DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS group_items (
    id BIGINT PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    file_id TEXT,
    file_name TEXT,
    file_size BIGINT DEFAULT 0,
    file_type TEXT,
    text_content TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_token ON files(token);
CREATE INDEX IF NOT EXISTS idx_files_owner_id ON files(owner_id);
CREATE INDEX IF NOT EXISTS idx_groups_token ON groups(token);
CREATE INDEX IF NOT EXISTS idx_groups_owner_id ON groups(owner_id);
CREATE INDEX IF NOT EXISTS idx_group_items_group_id ON group_items(group_id);
"""

UPSERTS = {
    "users": """
        INSERT INTO users
        (user_id, username, first_name, created_at, language, blocked)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (user_id) DO UPDATE SET
          username=EXCLUDED.username,
          first_name=EXCLUDED.first_name,
          created_at=EXCLUDED.created_at,
          language=EXCLUDED.language,
          blocked=EXCLUDED.blocked
    """,
    "admins": """
        INSERT INTO admins (user_id, added_by, created_at)
        VALUES (%s,%s,%s)
        ON CONFLICT (user_id) DO UPDATE SET
          added_by=EXCLUDED.added_by,
          created_at=EXCLUDED.created_at
    """,
    "blocked_users": """
        INSERT INTO blocked_users (user_id, blocked_by, reason, created_at)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (user_id) DO UPDATE SET
          blocked_by=EXCLUDED.blocked_by,
          reason=EXCLUDED.reason,
          created_at=EXCLUDED.created_at
    """,
    "settings": """
        INSERT INTO settings (key, value)
        VALUES (%s,%s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
    """,
    "bot_settings": """
        INSERT INTO bot_settings (key, value)
        VALUES (%s,%s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
    """,
    "join_channels": """
        INSERT INTO join_channels
        (channel_id, title, username, created_at, invite_url)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (channel_id) DO UPDATE SET
          title=EXCLUDED.title,
          username=EXCLUDED.username,
          created_at=EXCLUDED.created_at,
          invite_url=EXCLUDED.invite_url
    """,
    "user_settings": """
        INSERT INTO user_settings
        (user_id, language, created_at, updated_at)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (user_id) DO UPDATE SET
          language=EXCLUDED.language,
          created_at=EXCLUDED.created_at,
          updated_at=EXCLUDED.updated_at
    """,
    "files": """
        INSERT INTO files
        (id, token, owner_id, file_id, file_name, file_size, file_type,
         text_content, downloads, active, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO UPDATE SET
          token=EXCLUDED.token,
          owner_id=EXCLUDED.owner_id,
          file_id=EXCLUDED.file_id,
          file_name=EXCLUDED.file_name,
          file_size=EXCLUDED.file_size,
          file_type=EXCLUDED.file_type,
          text_content=EXCLUDED.text_content,
          downloads=EXCLUDED.downloads,
          active=EXCLUDED.active,
          created_at=EXCLUDED.created_at
    """,
    "groups": """
        INSERT INTO groups
        (id, token, owner_id, title, downloads, active, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO UPDATE SET
          token=EXCLUDED.token,
          owner_id=EXCLUDED.owner_id,
          title=EXCLUDED.title,
          downloads=EXCLUDED.downloads,
          active=EXCLUDED.active,
          created_at=EXCLUDED.created_at
    """,
    "group_items": """
        INSERT INTO group_items
        (id, group_id, position, file_id, file_name, file_size, file_type, text_content)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO UPDATE SET
          group_id=EXCLUDED.group_id,
          position=EXCLUDED.position,
          file_id=EXCLUDED.file_id,
          file_name=EXCLUDED.file_name,
          file_size=EXCLUDED.file_size,
          file_type=EXCLUDED.file_type,
          text_content=EXCLUDED.text_content
    """,
}

def sqlite_columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]

def sqlite_rows(conn, table):
    cols = sqlite_columns(conn, table)
    rows = conn.execute(
        f'SELECT {",".join(chr(34)+c+chr(34) for c in cols)} FROM "{table}"'
    ).fetchall()
    return cols, rows

def normalize_row(table, cols, row):
    d = dict(zip(cols, row))
    if table == "users":
        return tuple(d.get(k) for k in
            ["user_id","username","first_name","created_at","language","blocked"])
    if table == "admins":
        return tuple(d.get(k) for k in ["user_id","added_by","created_at"])
    if table == "blocked_users":
        return tuple(d.get(k) for k in ["user_id","blocked_by","reason","created_at"])
    if table in ("settings", "bot_settings"):
        return (d.get("key"), d.get("value"))
    if table == "join_channels":
        return tuple(d.get(k) for k in
            ["channel_id","title","username","created_at","invite_url"])
    if table == "user_settings":
        return tuple(d.get(k) for k in
            ["user_id","language","created_at","updated_at"])
    if table == "files":
        return tuple(d.get(k) for k in
            ["id","token","owner_id","file_id","file_name","file_size",
             "file_type","text_content","downloads","active","created_at"])
    if table == "groups":
        return tuple(d.get(k) for k in
            ["id","token","owner_id","title","downloads","active","created_at"])
    if table == "group_items":
        return tuple(d.get(k) for k in
            ["id","group_id","position","file_id","file_name","file_size",
             "file_type","text_content"])
    raise ValueError(table)

def pg_count(cur, table):
    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
    return cur.fetchone()[0]

def set_sequence(cur, table):
    # PostgreSQL identity/serial sequence may not exist because IDs are BIGINT.
    # The tables deliberately use explicit BIGINT PKs, so no sequence is required.
    # Future bot inserts should use an explicit ID generator or be migrated to
    # GENERATED BY DEFAULT AS IDENTITY later.

def main():
    print("=" * 60)
    print("SQLite -> PostgreSQL migration")
    print(f"SQLite: {SQLITE_PATH.resolve()}")
    print("=" * 60)

    src = sqlite3.connect(str(SQLITE_PATH))
    src.row_factory = sqlite3.Row

    with psycopg.connect(DATABASE_URL) as pg:
        with pg.cursor() as cur:
            print("\n[1/4] Creating PostgreSQL schema...")
            cur.execute(CREATE_SQL)

            print("[2/4] Migrating tables...")
            totals = {}
            for table in TABLES:
                cols, rows = sqlite_rows(src, table)
                migrated = 0

                # Parent tables must precede group_items.
                for row in rows:
                    values = normalize_row(table, cols, row)
                    cur.execute(UPSERTS[table], values)
                    migrated += 1

                totals[table] = migrated
                print(f"  {table:16} {migrated:6} rows")

            print("\n[3/4] Verifying counts...")
            failed = False
            for table in TABLES:
                sqlite_count = src.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
                postgres_count = pg_count(cur, table)
                status = "OK" if sqlite_count == postgres_count else "MISMATCH"
                print(
                    f"  {table:16} SQLite={sqlite_count:6} "
                    f"PostgreSQL={postgres_count:6} [{status}]"
                )
                if status != "OK":
                    failed = True

            if failed:
                pg.rollback()
                print("\nERROR: Count verification failed. PostgreSQL transaction rolled back.")
                sys.exit(2)

            print("\n[4/4] Committing migration...")
        pg.commit()

    src.close()
    print("\nSUCCESS: Migration completed.")
    print("The original SQLite database was NOT modified or deleted.")

if __name__ == "__main__":
    main()
