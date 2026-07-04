# TODO: GitHub Issues 実装 (2026-07-04)

対象ブランチ: `claude/github-issues-implementation-lxbl6p`（マージ済みPR #88の後、origin/main a2737a4 から再作成）

## 選定issue

- [x] #61 残タスク: ジョブキュー強化（優先度・推定残り時間 ETA・並べ替え）→ Sonnetサブエージェント A
- [x] #63 残タスク: XLSX形式の履歴エクスポート → Sonnetサブエージェント C（Aと並行・ファイル非重複）
- [x] #65 一部: Webhook通知（generic / Discord / Slack）→ Sonnetサブエージェント B（A完了後、job_queueの完了リスナーフックに依存）

見送り: #62 コンポーネント化・#64 認証・#61 ComfyUI対応（規模超過）、#77（UI比重が大きい）

## 手順

- [x] ベースライン確認: pytest 356 passed（環境の cffi 欠落は pip install で解消）
- [x] Wave 1: A（#61）と C（#63）を並行実行 → メインでレビュー → コミット
- [x] Wave 2: B（#65 Webhook）を実行 → メインでレビュー → コミット
- [x] 全体検証: pytest 385 passed / ruff / ruff format / mypy 全て緑
- [x] push → issueへの進捗報告

## 運用ルール

- サブエージェントはコミットしない（メインがレビュー後にコミット）
- サブエージェント稼働中は stash/checkout/reset 禁止 (lessons.md)
- 並行エージェントは全テストを回さず担当テストのみ実行（DB系テストの衝突回避）、全体は本セッションで実行

## Review

- コミット: 8b0e1a6 (#63 XLSX) / 6660265 (#61 キュー強化) / caa2e84 (#65 Webhook) / 53c7496 (main由来のCI失敗修正)
- #61: asyncio.Queue → 優先度ソート済みpendingリスト + Condition に置換。優先度クランプ(-10..10)、
  `POST /api/jobs/{id}/priority`、ETA（ジョブ種別ごと直近20件の移動平均）、完了リスナーフック追加
- #63: `format=xlsx`（openpyxl遅延import、threadpoolでビルド、リスト/辞書セルの型変換）
- #65: WebhookNotifier（generic/discord/slack）。job_queueリスナー + BatchProcessor.run() 末尾にフック
- メインレビューでの修正2点: submitレスポンスを`job_info()`に統一（queue_position/eta欠落の非一貫性）、
  `job_listener`にWebhook無効時の早期リターン追加（無駄なスレッド起動防止）
- 既存CI問題（mainマージ時のmypyエラー8件・未フォーマット6ファイル）も別コミットで解消
- 最終検証: pytest 385 passed / ruff / ruff format / mypy 全て緑
