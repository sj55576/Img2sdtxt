import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

DB_PATH = Path(__file__).parent / "data" / "history.db"


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_name TEXT,
                positive TEXT NOT NULL,
                negative TEXT NOT NULL,
                style TEXT,
                tone TEXT,
                quality TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


def save_history(
    positive: str,
    negative: str,
    image_name: str = "",
    style: str = "",
    tone: str = "",
    quality: str = ""
) -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """INSERT INTO prompt_history
               (image_name, positive, negative, style, tone, quality, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (image_name, positive, negative, style, tone, quality,
             datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid


def get_history(limit: int = 50, offset: int = 0) -> List[Dict]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM prompt_history
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]


def get_history_item(item_id: int) -> Optional[Dict]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM prompt_history WHERE id = ?", (item_id,)
        ).fetchone()
        return dict(row) if row else None


def delete_history_item(item_id: int) -> bool:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute(
            "DELETE FROM prompt_history WHERE id = ?", (item_id,)
        )
        conn.commit()
        return result.rowcount > 0


def clear_all_history() -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("DELETE FROM prompt_history")
        conn.commit()
        return result.rowcount


def get_history_count() -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT COUNT(*) FROM prompt_history").fetchone()[0]
