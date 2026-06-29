import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("img2sdtxt.history")

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                history_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                FOREIGN KEY (history_id) REFERENCES prompt_history(id) ON DELETE CASCADE,
                UNIQUE(history_id, tag)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_tag ON prompt_tags(tag)")
        conn.commit()


def save_history(
    positive: str,
    negative: str,
    image_name: str = "",
    style: str = "",
    tone: str = "",
    quality: str = ""
) -> int:
    logger.debug("save_history image_name=%s style=%s", image_name, style)
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
        return cursor.lastrowid or 0


def get_history(
    limit: Optional[int] = 50,
    offset: int = 0,
    search: str = "",
    style: str = "",
    quality: str = "",
    favorites_only: bool = False,
    tag: str = ""
) -> List[Dict]:
    logger.debug("get_history limit=%s offset=%d search=%s", limit, offset, search)
    init_db()
    conditions = []
    params: List = []
    join_clause = ""

    if tag:
        join_clause = "JOIN prompt_tags pt ON pt.history_id = prompt_history.id AND pt.tag = ?"
        params.append(tag.strip().lower())

    if search:
        # LIKE 特殊文字をエスケープしてリテラルマッチにする
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(
            "(positive LIKE ? ESCAPE '\\' OR negative LIKE ? ESCAPE '\\' OR image_name LIKE ? ESCAPE '\\')"
        )
        term = f"%{escaped}%"
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

    if limit is None:
        # LIMIT なし — 全件取得
        params.append(offset)
        query = f"SELECT prompt_history.* FROM prompt_history {join_clause} {where} ORDER BY created_at DESC LIMIT -1 OFFSET ?"
    else:
        params.extend([limit, offset])
        query = f"SELECT prompt_history.* FROM prompt_history {join_clause} {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        items = [dict(r) for r in rows]
        # Attach tags to each item
        for item in items:
            tag_rows = conn.execute(
                "SELECT tag FROM prompt_tags WHERE history_id = ? ORDER BY tag",
                (item["id"],)
            ).fetchall()
            item["tags"] = [r[0] for r in tag_rows]
        return items


def get_history_count(
    search: str = "",
    style: str = "",
    quality: str = "",
    favorites_only: bool = False,
    tag: str = ""
) -> int:
    init_db()
    conditions = []
    params: List = []
    join_clause = ""

    if tag:
        join_clause = "JOIN prompt_tags pt ON pt.history_id = prompt_history.id AND pt.tag = ?"
        params.append(tag.strip().lower())

    if search:
        # LIKE 特殊文字をエスケープしてリテラルマッチにする
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(
            "(positive LIKE ? ESCAPE '\\' OR negative LIKE ? ESCAPE '\\' OR image_name LIKE ? ESCAPE '\\')"
        )
        term = f"%{escaped}%"
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
        conn.execute("PRAGMA foreign_keys = ON")
        return conn.execute(
            f"SELECT COUNT(*) FROM prompt_history {join_clause} {where}", params
        ).fetchone()[0]


def add_tags(history_id: int, tags: List[str]) -> List[str]:
    """Add tags to a history item. Returns the full list of tags after adding."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for tag in tags:
            tag = tag.strip().lower()
            if tag:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO prompt_tags (history_id, tag) VALUES (?, ?)",
                        (history_id, tag)
                    )
                except sqlite3.IntegrityError:
                    pass
        conn.commit()
    return get_tags(history_id)


def remove_tag(history_id: int, tag: str) -> List[str]:
    """Remove a tag from a history item. Returns remaining tags."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "DELETE FROM prompt_tags WHERE history_id = ? AND tag = ?",
            (history_id, tag.strip().lower())
        )
        conn.commit()
    return get_tags(history_id)


def get_tags(history_id: int) -> List[str]:
    """Get all tags for a history item."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT tag FROM prompt_tags WHERE history_id = ? ORDER BY tag",
            (history_id,)
        ).fetchall()
        return [r[0] for r in rows]


def get_all_tags() -> List[Dict]:
    """Get all unique tags with their usage count."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT tag, COUNT(*) as count FROM prompt_tags GROUP BY tag ORDER BY count DESC"
        ).fetchall()
        return [{"tag": r[0], "count": r[1]} for r in rows]


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
        conn.execute("PRAGMA foreign_keys = ON")
        result = conn.execute(
            "DELETE FROM prompt_history WHERE id = ?", (item_id,)
        )
        conn.commit()
        return result.rowcount > 0


def clear_all_history() -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        result = conn.execute("DELETE FROM prompt_history")
        conn.commit()
        return result.rowcount


def save_batch_result(
    image_filename: str,
    status: str,
    positive: str = "",
    negative: str = "",
    error: str = "",
) -> None:
    """バッチ処理の結果（成功 / 失敗）を履歴DBに記録する。

    Args:
        image_filename: 処理対象の画像ファイル名。
        status: ``"success"`` または ``"error"``。
        positive: 生成されたポジティブプロンプト（成功時）。
        negative: 生成されたネガティブプロンプト（成功時）。
        error: エラーメッセージ（失敗時）。
    """
    init_db()
    note = error if status == "error" else ""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT INTO prompt_history
               (image_name, positive, negative, style, tone, quality, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                image_filename,
                positive if status == "success" else f"[batch:{status}]",
                negative if status == "success" else note,
                "batch",
                "",
                "",
                datetime.now().isoformat(),
            ),
        )
        conn.commit()


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
