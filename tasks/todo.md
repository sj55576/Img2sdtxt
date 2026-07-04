# TODO: GitHub Issues 実装 (2026-07-04)

対象ブランチ: `claude/github-issues-implementation-lxbl6p`（マージ済みPR #88の後、origin/main a2737a4 から再作成）

## 選定issue

- [ ] #61 残タスク: ジョブキュー強化（優先度・推定残り時間 ETA・並べ替え）→ Sonnetサブエージェント A
- [ ] #63 残タスク: XLSX形式の履歴エクスポート → Sonnetサブエージェント C（Aと並行・ファイル非重複）
- [ ] #65 一部: Webhook通知（generic / Discord / Slack）→ Sonnetサブエージェント B（A完了後、job_queueの完了リスナーフックに依存）

見送り: #62 コンポーネント化・#64 認証・#61 ComfyUI対応（規模超過）、#77（UI比重が大きい）

## 手順

- [x] ベースライン確認: pytest 356 passed（環境の cffi 欠落は pip install で解消）
- [ ] Wave 1: A（#61）と C（#63）を並行実行 → メインでレビュー → コミット
- [ ] Wave 2: B（#65 Webhook）を実行 → メインでレビュー → コミット
- [ ] 全体検証: pytest / ruff / mypy
- [ ] push → issueへの進捗報告

## 運用ルール

- サブエージェントはコミットしない（メインがレビュー後にコミット）
- サブエージェント稼働中は stash/checkout/reset 禁止 (lessons.md)
- 並行エージェントは全テストを回さず担当テストのみ実行（DB系テストの衝突回避）、全体は本セッションで実行

## Review

（完了後に記載）
