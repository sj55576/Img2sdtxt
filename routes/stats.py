"""履歴と生成画像メタデータを集計する統計ダッシュボードエンドポイント。"""

import json
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

import history as hist

logger = logging.getLogger("img2sdtxt.stats")

router = APIRouter(prefix="/api", tags=["stats"])

_OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"

_DAILY_ACTIVITY_DAYS = 30

# ------------------------------------------------------------------ #
# タグ抽出
# ------------------------------------------------------------------ #


def _normalize_tag(raw: str) -> str:
    """1個のタグ片から SD の重み付け構文を取り除き、正規化する。

    ``(tag:1.2)`` -> ``tag``、``((tag))`` -> ``tag``、``[tag]`` -> ``tag`` のように、
    囲みカッコと ``:数値`` の重みサフィックスを取り除いてから小文字化する。
    """
    tag = raw.strip()
    if not tag:
        return ""
    # 外側のカッコ ( ) / [ ] を繰り返し剥がす
    while len(tag) >= 2 and tag[0] in "([" and tag[-1] in ")]":
        tag = tag[1:-1].strip()
    # 末尾の重みサフィックス ":1.2" を除去
    tag = re.sub(r":\s*-?[\d.]+\s*$", "", tag).strip()
    # 重み除去でさらにカッコが露出するケースに対応
    while len(tag) >= 2 and tag[0] in "([" and tag[-1] in ")]":
        tag = tag[1:-1].strip()
    return tag.lower()


def _extract_tags(prompt_text: str) -> List[str]:
    """カンマ区切りのプロンプト文字列から正規化済みタグのリストを取り出す。"""
    if not prompt_text:
        return []
    tags = []
    for chunk in prompt_text.split(","):
        tag = _normalize_tag(chunk)
        if tag:
            tags.append(tag)
    return tags


def _top_n_counter(counter: Counter, top_n: int) -> List[Dict]:
    return [{"tag": tag, "count": count} for tag, count in counter.most_common(top_n)]


# ------------------------------------------------------------------ #
# スタイル / トーン / 品質の利用割合
# ------------------------------------------------------------------ #


def _usage_breakdown(counter: Counter) -> Dict:
    total = sum(counter.values())
    counts = []
    for value, count in counter.most_common():
        percent = round((count / total) * 100, 1) if total else 0.0
        counts.append({"value": value, "count": count, "percent": percent})
    return {"total": total, "counts": counts}


# ------------------------------------------------------------------ #
# outputs メタデータの走査
# ------------------------------------------------------------------ #


def _scan_outputs_metadata(outputs_dir: Path) -> List[Dict]:
    """outputs/<date>/*_metadata.json を読み込み、日付タグ付きで返す。"""
    records: List[Dict] = []
    if not outputs_dir.exists():
        return records

    for date_dir in sorted(outputs_dir.iterdir()):
        if not date_dir.is_dir() or date_dir.name == "thumbs":
            continue
        for meta_file in date_dir.glob("*_metadata.json"):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("Failed to parse metadata file %s", meta_file, exc_info=True)
                continue
            meta["_date"] = date_dir.name
            records.append(meta)
    return records


def _generation_stats(records: List[Dict]) -> Dict:
    model_counter: Counter = Counter()
    sampler_counter: Counter = Counter()
    daily_counter: Counter = Counter()
    total_generated_images = 0

    for rec in records:
        params = rec.get("parameters") or {}
        image_count = rec.get("image_count")
        if not isinstance(image_count, int) or image_count <= 0:
            image_count = len(rec.get("files") or [])
        total_generated_images += image_count

        model = (params.get("model") or "").strip()
        if model:
            model_counter[model] += image_count

        sampler = (params.get("sampler") or "").strip()
        if sampler:
            sampler_counter[sampler] += image_count

        date_str = rec.get("_date") or ""
        if date_str:
            daily_counter[date_str] += image_count

    return {
        "total_generated_images": total_generated_images,
        "models": [{"value": v, "count": c} for v, c in model_counter.most_common()],
        "samplers": [{"value": v, "count": c} for v, c in sampler_counter.most_common()],
        "daily_counter": daily_counter,
    }


def _daily_activity(daily_counter: Counter, days: int = _DAILY_ACTIVITY_DAYS) -> List[Dict]:
    """直近 N 日分の日別アクティビティを、データが無い日も 0 件で埋めて返す（昇順）。"""
    today = date.today()
    daily = []
    for offset in range(days - 1, -1, -1):
        d = today - timedelta(days=offset)
        d_str = d.isoformat()
        daily.append({"date": d_str, "count": daily_counter.get(d_str, 0)})
    return daily


def _weekly_activity(daily: List[Dict]) -> List[Dict]:
    """日別アクティビティ（昇順リスト）を ISO 週単位に集計する。"""
    weekly_counter: "Counter[str]" = Counter()
    week_start: Dict[str, str] = {}
    week_order: List[str] = []
    for entry in daily:
        d = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        iso_year, iso_week, _ = d.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        if week_key not in weekly_counter:
            week_order.append(week_key)
            week_start[week_key] = date.fromisocalendar(iso_year, iso_week, 1).isoformat()
        weekly_counter[week_key] += entry["count"]
    return [
        {"week": week_key, "week_start": week_start[week_key], "count": weekly_counter[week_key]}
        for week_key in week_order
    ]


# ------------------------------------------------------------------ #
# 集計本体
# ------------------------------------------------------------------ #


def compute_stats(top_n: int = 20) -> Dict:
    items = hist.get_history(limit=None, offset=0)

    positive_tag_counter: Counter = Counter()
    negative_tag_counter: Counter = Counter()
    style_counter: Counter = Counter()
    tone_counter: Counter = Counter()
    quality_counter: Counter = Counter()
    favorite_count = 0
    total_prompt_chars = 0
    total_tag_count = 0

    for item in items:
        positive_tag_counter.update(_extract_tags(item.get("positive", "")))
        negative_tag_counter.update(_extract_tags(item.get("negative", "")))

        style = (item.get("style") or "").strip()
        if style:
            style_counter[style] += 1
        tone = (item.get("tone") or "").strip()
        if tone:
            tone_counter[tone] += 1
        quality = (item.get("quality") or "").strip()
        if quality:
            quality_counter[quality] += 1

        if item.get("is_favorite"):
            favorite_count += 1

        total_prompt_chars += len(item.get("positive") or "") + len(item.get("negative") or "")
        total_tag_count += len(item.get("tags") or [])

    total_history = len(items)
    generation = _generation_stats(_scan_outputs_metadata(_OUTPUTS_DIR))
    daily = _daily_activity(generation["daily_counter"])
    weekly = _weekly_activity(daily)

    return {
        "total_history": total_history,
        "total_generated_images": generation["total_generated_images"],
        "favorite_rate": round((favorite_count / total_history) * 100, 1) if total_history else 0.0,
        "favorite_count": favorite_count,
        "avg_prompt_length": round(total_prompt_chars / total_history, 1) if total_history else 0.0,
        "avg_tag_count": round(total_tag_count / total_history, 2) if total_history else 0.0,
        "top_tags": {
            "positive": _top_n_counter(positive_tag_counter, top_n),
            "negative": _top_n_counter(negative_tag_counter, top_n),
        },
        "styles": _usage_breakdown(style_counter),
        "tones": _usage_breakdown(tone_counter),
        "quality_levels": _usage_breakdown(quality_counter),
        "models": generation["models"],
        "samplers": generation["samplers"],
        "activity": {
            "daily": daily,
            "weekly": weekly,
        },
    }


# ------------------------------------------------------------------ #
# エンドポイント
# ------------------------------------------------------------------ #


@router.get("/stats")
async def get_stats(top_n: int = 20):
    """履歴 DB と outputs メタデータを集計したダッシュボード統計を返す。"""
    if top_n <= 0:
        raise HTTPException(status_code=400, detail="top_n must be a positive integer.")
    data = await run_in_threadpool(compute_stats, top_n)
    return {"success": True, **data}
