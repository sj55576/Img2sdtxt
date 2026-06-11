# 改良計画: コードレビューに基づく修正と機能追加 (2026-06-11)

調査結果: バックエンド13バグ/12改善点、フロントエンド20バグ/15 UXギャップを検出。
このうち「価値が高く・リスクが低く・一貫性のある」ものを選定して実装する。

## バックエンド (main.py / sd_client.py / history.py / presets.py / config.py)

- [x] BE-1: ブロッキングI/Oのイベントループ解放
  - JSONボディ/引数のみのハンドラは `async def` → `def`(FastAPIがスレッドプール実行)
  - UploadFile を使うハンドラは `await file.read()` 後、ブロッキング処理を
    `fastapi.concurrency.run_in_threadpool` でオフロード
  - 共有状態 (`_gallery_cache`, last_params, presets ファイル) に `threading.Lock`
- [x] BE-2: 新エンドポイント `GET /api/sd/progress`
  - SD WebUI `/sdapi/v1/progress?skip_current_image=true` のプロキシ
  - 返却: `{available, progress, eta_relative, state}`
- [x] BE-3: 入力バリデーション強化
  - int/float キャストの 422 化 (sd/generate, generate-multi-model)
  - `/api/outputs` の `date` を `YYYY-MM-DD` 正規表現で検証
  - アップロード画像を Pillow で実体検証 (MIME偽装対策)、`image/bmp` を許可リストに追加
  - text 生成の `description` に最大長ガード
- [x] BE-4: `/health` を軽量化 (LLMにチャット補完を投げない)
- [x] BE-5: refine 結果を履歴に保存 (MI-2)
- [x] BE-6: ファイルI/Oの堅牢化
  - last_params.json / presets.json をアトミック書き込み (tmp + os.replace) + ロック
  - `sd_client.save_images()` の PIL ハンドルリーク修正 (with 文)
  - サムネイルを `.jpg` 拡張子で保存、ギャラリースキャンは旧 `.png` サムネも許容
- [x] BE-7: 小修正
  - `SDClient.get_models()` / `get_model_list()` の重複解消
  - 履歴エクスポートの 10000 件上限撤廃
  - 履歴検索の LIKE ワイルドカード (`%`, `_`) エスケープ
- [x] BE-8: テスト整備
  - `requirements-dev.txt` (pytest, httpx)
  - prompt_generator の JSON パース、history CRUD、presets CRUD のユニットテスト

## フロントエンド (static/script.js / index.html / style.css)

- [x] FE-1: 二重送信ガード (SD生成/img2img/inpaint/マルチモデルのボタン disable + finally 再有効化)
- [x] FE-2: 150ms setTimeout レース解消 (checkSDStatus 系を Promise 化して await)
- [x] FE-3: SD生成プログレスバー (新 `/api/sd/progress` を1秒ポーリング、%表示)
- [x] FE-4: エラーハンドリング修正
  - clipboard.writeText の .catch、履歴削除系の response チェック
  - loadHistory のスピナーを finally で隠す、checkImg2ImgStatus の checking クラス解除
  - loadPresetsIntoSelects の .catch
- [x] FE-5: Ctrl+Enter で生成実行 (generate / refine ページ)
- [x] FE-6: 履歴カード改善 — プロンプトのコピーボタン、「SDへ送る」ボタン、
  DOM スクレイピング (B-10) を構造化データ参照に置換
- [x] FE-7: ギャラリーモーダルにプロンプトコピーボタン
- [x] FE-8: 機能していない inpaint hires.fix UI → 再調査の結果、該当 ID は index.html に存在せず (調査時の誤検出)。対応不要を確認

## 検証

- [x] pytest 全テスト通過 (既存12 + 新規)
- [x] `node --check static/script.js` / `python -m py_compile` 通過
- [x] メインセッション (Fable 5) で全差分をレビュー
- [x] コミット & `claude/repo-review-features-qn7pso` へプッシュ

## 見送り (理由)

- バッチ生成の並列化: ローカルLLMは並列実行で速くならないため、イベントループ解放のみで十分
- 未使用エンドポイント削除 (`/api/config` 等): API互換性維持を優先、影響最小の原則
- ダークモード切替・inpaint undo: 規模が大きく今回のスコープ外

## レビュー結果

メインセッションによる監査 (2026-06-11):

- pytest: **60 passed** (既存12 + 新規48)、`node --check` / `py_compile` 通過
- 二重適用チェック: フロントエンドの新規要素 (プログレスバー×4、ヒント×2、コピーボタン×1、
  `startSDProgress`×1、keydown×1) に重複なし
- `_sdStatusPromise` キャッシュは `finally` で自己クリアする実装で、SD未接続状態を
  永続キャッシュしない (in-flight の重複排除のみ) ことを確認
- 全 SD 生成系関数で `finally { stopProgress(); loading隠し; btn再有効化 }` を確認
- `/health` のレスポンス形式は従来と互換 (degraded 時も 200 を返す挙動は元から同じ)
- ギャラリーのレガシー `.png` サムネイルへのフォールバックを確認
- requirements-dev.txt の httpx は starlette 0.27 互換のため `<0.28` に固定 (妥当)

特記: 当初のフロントエンド実装エージェントが作業を再委任したまま終了したため、
継続エージェントを起動して完遂。最終状態は上記監査で検証済み。
