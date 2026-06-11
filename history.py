import sqlite3
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
    limit: Optional[int] = 50,
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
        query = f"SELECT * FROM prompt_history {where} ORDER BY created_at DESC LIMIT -1 OFFSET ?"
    else:
        params.extend([limit, offset])
        query = f"SELECT * FROM prompt_history {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
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
