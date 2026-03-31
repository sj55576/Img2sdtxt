import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

_batch_log_lock = threading.Lock()
BATCH_LOG_PATH = Path(__file__).parent / "data" / "batch_log.jsonl"

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
                created_at TEXT NOT NULL,
                is_favorite INTEGER NOT NULL DEFAULT 0
            )
        """)
        # 既存DBへの is_favorite カラム追加（マイグレーション）
        try:
            conn.execute("ALTER TABLE prompt_history ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # カラムが既に存在する場合はスキップ
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


def get_history(
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    style: str = "",
    quality: str = "",
    favorites_only: bool = False
) -> List[Dict]:
    init_db()
    conditions = []
    params: List = []

    if search:
        conditions.append("(positive LIKE ? OR negative LIKE ? OR image_name LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])
    if style:
        conditions.append("style = ?")
        params.append(style)
    if quality:
        conditions.append("quality = ?")
        params.append(quality)
    if favorites_only:
        conditions.append("is_favorite = 1")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.extend([limit, offset])

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM prompt_history {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params
        ).fetchall()
        return [dict(r) for r in rows]


def get_history_count(
    search: str = "",
    style: str = "",
    quality: str = "",
    favorites_only: bool = False
) -> int:
    init_db()
    conditions = []
    params: List = []

    if search:
        conditions.append("(positive LIKE ? OR negative LIKE ? OR image_name LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])
    if style:
        conditions.append("style = ?")
        params.append(style)
    if quality:
        conditions.append("quality = ?")
        params.append(quality)
    if favorites_only:
        conditions.append("is_favorite = 1")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM prompt_history {where}", params
        ).fetchone()[0]


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


def toggle_favorite(item_id: int) -> Optional[Dict]:
    """お気に入り状態をトグルし、更新後のアイテムを返す"""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, is_favorite FROM prompt_history WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return None
        new_state = 0 if row["is_favorite"] else 1
        conn.execute(
            "UPDATE prompt_history SET is_favorite = ? WHERE id = ?", (new_state, item_id)
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM prompt_history WHERE id = ?", (item_id,)
        ).fetchone()
        return dict(updated) if updated else None


def save_batch_log(record: Dict) -> None:
    """バッチ処理の実行結果（成功・失敗）をJSONL形式でログに追記する。

    record には以下のキーを含めることを想定:
        image_filename, status, prompt_text, model_used, timestamp,
        processing_time_ms, error (失敗時のみ), metadata
    """
    BATCH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"logged_at": datetime.now().isoformat(), **record}
    with _batch_log_lock:
        with open(BATCH_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
