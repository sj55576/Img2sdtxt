# CLAUDE.md

@AGENTS.md

## このファイルの役割

Claude Code が読み込むのは `CLAUDE.md` だけで、`AGENTS.md` は読み込みません。冒頭の import で `AGENTS.md` を取り込むことで、他のコーディングエージェントと同じルールを共有します。

プロジェクト固有の指示は `AGENTS.md` 側に書きます。このテンプレートを使って `CLAUDE.md` を更新する場合は、Claude Code 固有の指示を対象プロジェクト側で手動統合してください。Claude Code 固有の記載が不要な場合は、`CLAUDE.md` を `AGENTS.md` へのシンボリックリンクにしても同じ結果になります（Windows では管理者権限または開発者モードが必要なため、import 方式を推奨します）。

## タスク別コマンド

`.claude/commands/` に必要なコマンドを配置した場合、次のコマンドを使用できます。引数には対象の URL または番号を渡します。

| コマンド | 用途 |
| --- | --- |
| `/implement-issue` | Issue の調査、最小差分の実装、検証、報告 |
| `/fix-ci` | CI 失敗の原因特定、最小修正、再検証 |
| `/review-pr` | 品質・セキュリティ・互換性のレビュー（コードは変更しない） |
| `/investigate-issue` | コードを変更しない原因調査と対応案の比較 |
| `/audit-repository` | リポジトリの課題・改善点を診断し、必要に応じて重複のないGitHub Issueを作成 |
| `/propose-features` | アプリの目的・実装・拡張性を確認し、追加実装候補を必要に応じてGitHub Issueとして作成 |

## 計画レビュー・差分レビューの必須ゲート

`/implement-issue`、`/fix-ci`、および `/quick-request` の `実装` / `CI` は、次の段階分けと2つの必須ゲートをプロンプト本文に含んでいます。

1. 調査（目的・完了条件・変更範囲・実装方針・リスクを整理する）
2. **計画レビュー**（要求との整合性・見落とし・実現性を確認する。Critical/High 相当の懸念があれば着手前に解消する必須ゲート）
3. 実装
4. **差分レビュー**（`review-pr.md` と同じ観点で確認する。Critical/High 相当の指摘があれば完了・PR作成前に解消する必須ゲート）

サブエージェントへの委任（`ai-platform-planner` / `ai-platform-reviewer` / `ai-platform-implementer`）は `.claude/agents/` にそれらを配置した場合のみ有効な、AI Platform Repository のオプション機能です。本リポジトリには現時点で `.claude/agents/` を導入していないため、上記の段階分けは単一の会話内での自己レビューとして機能します。導入する場合は AI Platform Repository の `agents/planner.md` / `agents/implementer.md` / `agents/reviewer.md` を参照してください。

コードを変更しない `/review-pr`、`/investigate-issue`、`/audit-repository`、`/propose-features` にはこの段階分けは不要です（プロンプト本文の指示どおり単独で完結します）。

## 検証コマンドの実行

`AGENTS.md` の「検証コマンド」を実行する前に、依存関係が導入済みかを確認します。クラウドセッションは毎回新しい VM でリポジトリを clone するため、ローカルにだけ導入した依存やツールは存在しません。導入が必要な場合は、未導入であることを報告に含めます。

<!-- 依存導入を自動化する場合は、リポジトリの .claude/settings.json に SessionStart hook を設定します。設定例は AI Platform Repository の README を参照してください。 -->

## 報告とコミット

- 実行していない検証を成功として報告しません。実行できなかった検証は、理由とともに明示します。
- コミットとプッシュは、依頼された場合にのみ行います。クラウドセッションからプッシュできるのは、そのセッションの作業ブランチだけです。
- PR を作成する場合は、`.github/pull_request_template.md` の項目を埋めます。

<!--
このテンプレートを `CLAUDE.md` に適用する場合は、ファイル全体が置き換わります。
プロジェクト固有の指示は AGENTS.md に記載してください。
Claude Code 固有の指示（plan mode を使う範囲、レビューが必須のディレクトリ、
優先して使うサブエージェントなど）は、適用前に対象プロジェクト側で手動統合してください。
-->
