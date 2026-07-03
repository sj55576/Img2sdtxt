# TODO: GitHub Issues 実装 (2026-07-03)

対象ブランチ: `claude/github-issues-impl-vj1fvq`

## 選定issue

- [ ] #84 履歴の統計・分析ダッシュボード → Sonnetサブエージェント
- [ ] #81 CLIP Interrogator / DeepBooru 連携 → Sonnetサブエージェント
- [ ] #83 LLM応答のストリーミング表示 (SSE) → メインセッション(高難度)

見送り: #61-66(包括的な親issueでクローズ不可)、#85/#82/#77(規模超過)

## 手順

- [x] ベースライン確認: pytest 179 passed / ruff クリーン
- [ ] #84 実装(サブエージェントA)→ メインでレビュー → コミット
- [ ] #81 実装(サブエージェントB)→ メインでレビュー → コミット
- [ ] #83 バックエンド実装(メイン、Aと並行・ファイル非重複)
- [ ] #83 フロントエンド実装(A/B完了後)
- [ ] 全体検証: pytest / ruff / mypy
- [ ] push → PR作成 → issue #81 #83 #84 クローズ

## 運用ルール

- サブエージェントはコミットしない(メインがレビュー後にコミット)
- サブエージェント稼働中は stash/checkout/reset 禁止 (lessons.md)
- 共有ファイル(index.html / script.js / i18n)の編集は直列化する

## Review

(完了時に記入)
