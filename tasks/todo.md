# 改良計画: コードレビューに基づく修正と機能追加 (2026-06-11)

調査結果: バックエンド13バグ/12改善点、フロントエンド20バグ/15 UXギャップを検出。
このうち「価値が高く・リスクが低く・一貫性のある」ものを選定して実装する。

## バックエンド (main.py / sd_client.py / history.py / presets.py / config.py)

- [x] BE-1: ブロッキングI/Oのイベントループ解放
- [x] BE-2: 新エンドポイント `GET /api/sd/progress`
- [x] BE-3: 入力バリデーション強化
- [x] BE-4: `/health` を軽量化
- [x] BE-5: refine 結果を履歴に保存
- [x] BE-6: ファイルI/Oの堅牢化
- [x] BE-7: 小修正
- [x] BE-8: テスト整備

## フロントエンド (static/script.js / index.html / style.css)

- [x] FE-1: 二重送信ガード
- [x] FE-2: 150ms setTimeout レース解消
- [x] FE-3: SD生成プログレスバー (ポーリング方式)
- [x] FE-4: エラーハンドリング修正
- [x] FE-5: Ctrl+Enter で生成実行
- [x] FE-6: 履歴カード改善
- [x] FE-7: ギャラリーモーダルにプロンプトコピーボタン
- [x] FE-8: inpaint hires.fix UI — 対応不要確認済み

---

# 第2期改良計画 (2026-06-16)

## 新機能

- [x] NEW-1: **WebSocket SD進捗通知**
  - ポーリング方式(500ms setInterval)をWebSocketに置換
  - サーバー→クライアントへの即時プッシュで効率的な進捗表示
  - 接続管理、自動再接続、フォールバック対応
  - 担当: メインセッション (設計・実装が複雑なため)

- [x] NEW-2: **ギャラリー画像詳細モーダル**
  - サムネイルクリックで全画面モーダルを表示
  - 生成パラメータ(プロンプト、ステップ数、CFG、サンプラー、シード、モデル)を表示
  - プロンプトをワンクリックでコピー / SD生成ページに送る機能
  - 前後の画像へのナビゲーション (← →)
  - 担当: Sonnet サブエージェント

- [x] NEW-3: **プロンプトトークンカウンター**
  - ポジティブ/ネガティブプロンプトの推定トークン数をリアルタイム表示
  - SD1.5は77トークン、SDXLは150トークンが上限目安
  - 上限超過時の警告表示
  - 担当: Sonnet サブエージェント

- [x] NEW-4: **ネガティブプロンプトテンプレート**
  - カテゴリ別のネガティブプロンプト定型文 (人物、風景、アニメなど)
  - ワンクリックで挿入、複数テンプレートの組み合わせ対応
  - 担当: Sonnet サブエージェント

- [x] NEW-5: **APIルート分割 (リファクタリング)**
  - main.py (1,300行) を FastAPI APIRouter に分割
  - routes/prompts.py, routes/history.py, routes/sd.py, routes/presets.py, routes/gallery.py
  - 担当: Sonnet サブエージェント

## 実装順序

1. NEW-5 (APIルート分割) — 他の変更のベースとなるため最初に
2. NEW-2 (ギャラリー詳細モーダル) と NEW-3 (トークンカウンター) — 並行実装可
3. NEW-4 (ネガティブテンプレート)
4. NEW-1 (WebSocket進捗) — 最後にメインセッションで実装

---

# 第3期改良計画 (2026-06-18)

## バックエンド改善

- [x] BE3-1: **Pydanticリクエストモデル導入**
  - routes/sd.py の全エンドポイントで raw dict → Pydantic BaseModel に置換
  - 自動バリデーション、Swagger ドキュメント自動生成の改善
  - レスポンスモデルも定義して API 契約を明確化
  - 担当: Sonnet サブエージェント

- [x] BE3-2: **レートリミットミドルウェア**
  - IP ベースのインメモリレートリミッター
  - 生成系エンドポイント: 10 req/min、その他: 60 req/min
  - 429 Too Many Requests レスポンス
  - 担当: Sonnet サブエージェント

- [x] BE3-3: **ControlNet API 対応**
  - sd_client.py に ControlNet 拡張パラメータ追加
  - GET /api/sd/controlnet/models エンドポイント
  - txt2img / img2img に ControlNet 引数サポート
  - 担当: Sonnet サブエージェント

- [x] BE3-4: **生成キュー (Background Tasks)**
  - 非同期ジョブキュー: 生成リクエストを即時レスポンス+バックグラウンド実行
  - GET /api/jobs/{job_id} でステータス確認
  - WebSocket でジョブ完了通知
  - 担当: メインセッション (アーキテクチャ設計が複雑)

## フロントエンド改善

- [x] FE3-1: **ダークモード**
  - CSS変数ベースのテーマシステム
  - システム設定 (prefers-color-scheme) の自動検出
  - 手動切り替えトグル (サイドバーに配置)
  - localStorage でテーマ永続化
  - 担当: Sonnet サブエージェント

- [x] FE3-2: **プロンプトウェイトエディター**
  - プロンプト内の (tag:1.2) 形式のウェイトをスライダーで視覚的に調整
  - タグ一覧表示 + 個別ウェイト調整 UI
  - ウェイト変更のリアルタイムプレビュー
  - 担当: メインセッション (フロントエンドロジックが複雑)

- [x] FE3-3: **img2img 画像比較スライダー**
  - Before/After の比較表示コンポーネント
  - ドラッグ可能な分割バー
  - 担当: Sonnet サブエージェント

## 実装順序

1. BE3-1 + FE3-1 + BE3-2 — 並行実装 (独立した変更)
2. BE3-3 + FE3-3 — 並行実装
3. FE3-2 — プロンプトウェイトエディター (メインセッション)
4. BE3-4 — 生成キュー (メインセッション)

---

# Issue #80: PNG Info インポート機能 (2026-07-02)

## 計画

- [ ] 1. A1111 パラメータパーサーの堅牢化（メインセッション担当・最難部）
  - `sd_client.py` のパース処理を module-level 関数 `parse_a1111_parameters(raw)` に抽出
  - 引用符付き値（`Lora hashes: "a: b, c: d"` 等、カンマを含む値）に対応
  - 未知キー（Model hash, VAE, Clip skip 等）は `extras` dict に収集
  - 既存の戻り値キーとの後方互換を維持
- [ ] 2. バックエンド `POST /api/png-info`（Sonnet サブエージェント A 担当）
  - `routes/png_info.py` 新規作成、`main.py` に登録
  - 既存バリデーション（type / MAX_IMAGE_SIZE / `_validate_image_bytes`）を踏襲
  - bytes から PIL で `info["parameters"]` を読み `parse_a1111_parameters` でパース
  - レスポンス: `{has_metadata, parameters}` / 無し時 `{has_metadata: false}`
  - `tests/test_png_info.py`（パーサー単体 + エンドポイント）
- [ ] 3. フロントエンド PNG Info タブ（Sonnet サブエージェント B 担当）
  - ドロップゾーン + ファイル選択 → `/api/png-info`
  - 抽出結果表示、txt2img / img2img への転送、コピー、i18n（ja/en）
- [ ] 4. レビュー・テスト実行・検証（メインセッション担当）
- [ ] 5. コミット & プッシュ（branch: claude/github-issues-implementation-ml1yiw）

## レビュー結果

（実装完了後に記入）
