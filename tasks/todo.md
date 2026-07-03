# TODO: GitHub Issues 実装 (2026-07-03)

対象ブランチ: `claude/github-issues-impl-vj1fvq`

## 選定issue

- [x] #84 履歴の統計・分析ダッシュボード → Sonnetサブエージェント
- [x] #81 CLIP Interrogator / DeepDanbooru 連携 → Sonnetサブエージェント
- [x] #83 LLM応答のストリーミング表示 (SSE) → メインセッション(高難度)

見送り: #61-66(包括的な親issueでクローズ不可)、#85/#82/#77(規模超過)

## 手順

- [x] ベースライン確認: pytest 179 passed / ruff クリーン
- [x] #84 実装(サブエージェントA)→ メインでレビュー → コミット
- [x] #81 実装(サブエージェントB)→ メインでレビュー → コミット(hybridのキャッシュ順序を修正)
- [x] #83 バックエンド実装(メイン、Aと並行・ファイル非重複)
- [x] #83 フロントエンド実装(A/B完了後)
- [x] 全体検証: pytest 229 passed / ruff / mypy / node --check
- [x] push → PR #87 作成 → issue #81 #83 #84 クローズ済み

## 運用ルール

- サブエージェントはコミットしない(メインがレビュー後にコミット)
- サブエージェント稼働中は stash/checkout/reset 禁止 (lessons.md)
- 共有ファイル(index.html / script.js / i18n)の編集は直列化する

## Review

- テスト: 179 → 229 passed(+50: streaming 15 / stats 13 / interrogate 24、一部統合)。ruff / mypy クリーン。
- E2E検証: フェイクOpenAI互換ストリーミングサーバー + 実アプリ + Playwright で
  SSEタイプライター表示・完了時の結果反映・キャンセル(トースト表示/結果なし)を実機確認。
- メインでの監査所見と修正:
  - #81 hybridモードでキャッシュヒット時にも interrogate が走る非効率 → キャッシュミス時のみ実行に修正。
  - キャッシュキーは mode="llm" デフォルトで従来と同一(後方互換)を確認。
  - #84 は履歴スキーマ(is_favorite / tags)・outputsメタデータ構造との整合を実コードで確認。
- ストリーミング設計: 非対応プロバイダーは LLMProvider 基底のフォールバックで一括1チャンク。
  フロントは 404/405・ネットワーク失敗時のみ従来エンドポイントへフォールバック
  (SSE error イベント時は再試行しない=LLM二重課金を防止)。
