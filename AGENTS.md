# AGENTS.md — Img2sdtxt

> このファイルにはプロジェクト固有の指示だけを記載します。共通の詳細ルールは AI Platform Repository の `prompts/coding-agent-typescript-python.md` を参照してください。参照できない環境では「重要な共通ルールの要約」を適用します。

## プロジェクト概要

- 目的: 画像またはテキスト説明をローカル LLM（LM Studio / Lemonade Server 等）で解析し、Stable Diffusion 用のプロンプトを生成する Web アプリケーション。AUTOMATIC1111 WebUI API と直接連携し、アプリを離れずに画像生成まで行える。
- 所有チーム・連絡先: リポジトリ Issue / PR で連絡
- 対象環境: local（開発）/ Docker（自己ホスト）。本番運用は想定されておらず、README にも "Work in Progress" と明記されている。

## 使用技術

- 言語・バージョン: Python 3.10–3.12（CI は 3.10 / 3.11 / 3.12 でテスト、Docker は 3.12 相当を想定）
- フレームワーク・主要ライブラリ: FastAPI, Uvicorn, Pillow, anthropic / google-generativeai（マルチプロバイダ LLM クライアント）, aiofiles, watchdog
- 実行環境: Node 不要（フロントエンドは `static/` 配下の素の HTML/CSS/JS）。Docker / docker-compose で実行可能。

## パッケージマネージャー

- Python: `pip`、依存定義: `requirements.txt`（実行時）, `requirements-dev.txt`（lint/型チェック/テスト用、`-r requirements.txt` を含む）
- 依存更新のルール: バージョン範囲はピン留め方針（`==` または上限付き `>=,<`）を踏襲する。更新時は `requirements.txt` と `requirements-dev.txt` の両方を確認し、CI（lint / test / typecheck）を通す。

## ディレクトリ構成

| パス | 役割 | 変更時の注意 |
| --- | --- | --- |
| `main.py` | FastAPI アプリのエントリーポイント、ミドルウェア設定、ルーター登録 | ルーター追加時は CORS・レート制限ミドルウェアの適用順を維持する |
| `routes/` | 機能別 API ルーター（sd, llm, history, backup, jobs, gallery, presets, tags, wildcards 等） | 新規エンドポイントは既存ルーターの命名・レスポンス形式に合わせる |
| `providers/` | LLM プロバイダ実装（Anthropic, Gemini 等） | `llm_provider.py` のインターフェースに準拠する |
| `static/` | フロントエンド（素の HTML/CSS/JS、i18n 含む） | ビルドツールなし。直接編集が反映される |
| `tests/` | pytest ベースのユニット・統合テスト | 新機能・修正には対応するテストを追加する |
| `data/` | SQLite DB（`data/history.db`）や wildcards 等の実行時データ | Git に含めない生成物・ユーザーデータを置く場所。誤ってコミットしない |
| `docs/` | 実装メモ・サンプル | 挙動を変えたら関連ドキュメントも更新する |
| `docker-compose.yml`, `Dockerfile` | コンテナ実行環境 | 環境変数・ポート・ボリュームの変更は `.env.example` と同期する |

## アーキテクチャ

- エントリーポイント: `main.py`（FastAPI app 生成、ミドルウェア登録、`routes/*` のルーター include）
- レイヤー・責務: `routes/`（HTTP 層）→ `*_client.py` / `*_provider.py`（外部サービス連携: `llm_client.py`, `sd_client.py`）→ `models.py`（Pydantic モデル）、横断的関心事は `cache.py`, `rate_limit.py`, `retry.py`, `job_queue.py`, `webhook.py` に分離
- 状態管理・非同期処理: FastAPI の async ルート + `job_queue.py` によるバックグラウンドジョブキュー（バッチ処理・非同期生成に使用）
- 重要な設計制約: 設定値は `config.py`（`.env` 由来）に集約する。ルート層で外部入力（アップロード画像、プリセット名、ページネーションパラメータ等）を `validators.py` で検証してから下位層に渡す。

## 検証コマンド

| 目的 | コマンド | 実行条件・補足 |
| --- | --- | --- |
| lint | `python -m ruff check .` | `requirements-dev.txt` の依存が必要 |
| フォーマットチェック | `python -m ruff format --check .` | CI と同じチェック。差分がある場合は `python -m ruff format .` で修正 |
| 型チェック | `python -m mypy . --config-file pyproject.toml` | `tests/` は mypy 対象外 |
| unit / integration test | `python -m pytest tests/ -v --tb=short` | Python 3.10 / 3.11 / 3.12 で CI 実行。`pytest-asyncio` 使用（`asyncio_mode = auto`） |
| build | なし（コンパイル不要）。Docker イメージ検証は `docker build .` | 変更が Dockerfile/依存に関わる場合のみ実施 |

## 変更禁止領域

- `data/`: 実行時に生成される SQLite DB（`history.db`）やユーザーの wildcards データ。テスト以外でコミットしない。
- `.env`: 実際の環境変数ファイルはコミットしない。変更が必要な場合は `.env.example` を更新する。
- CI ワークフロー（`.github/workflows/ci.yml`）: lint / test / typecheck のマトリクスを縮小する変更は理由を明示してから行う。

## DB・API 固有ルール

- DB: `history.py` が SQLite（`data/history.db`）のスキーマ初期化・マイグレーションを担当。スキーマ変更時は既存データとの後方互換性（`ALTER TABLE` 失敗時のフォールバック等、既存の `sqlite3.OperationalError` ハンドリングパターン）を踏襲する。
- API: `routes/` 配下は FastAPI ルーター単位で機能分割。入力検証は `validators.py` / Pydantic モデル（`models.py`）で行い、ユーザー入力を信頼しない。認証機構は現状最小限（レート制限ミドルウェアのみ）なので、認証・認可を追加する変更は根拠を明確にする。
- 外部サービス: LLM（LM Studio / Lemonade Server / Anthropic / Gemini）、Stable Diffusion WebUI（A1111 API）への呼び出しは `llm_client.py` / `sd_client.py` 経由に統一し、`retry.py` / `fallback.py` の既存パターンを再利用する。

## デプロイ上の注意

- 環境変数はすべて `.env.example` に値なしのキーとして列挙されている。新しい設定を追加した場合は `.env.example` と `config.py` の両方を更新する。
- Docker / docker-compose での実行を想定（`Dockerfile`, `docker-compose.yml`, `setup.sh` / `setup.bat`, `run.sh` / `run.bat`）。ポートや永続化ボリュームの変更は両方の起動手段（スクリプトと Docker）で整合させる。
- 本リポジトリは README に "Work in Progress" と明記されており、機能の動作は完全には保証されていない。破壊的変更（DB スキーマ、API レスポンス形式）は影響範囲をコミットメッセージ・PR に明記する。

## プロジェクト固有の完了条件

- 変更内容に対応する `tests/` のテストが追加・更新されている。
- `ruff check` / `ruff format --check` / `mypy` / `pytest` がすべて成功している（未実行の場合はその旨を報告する）。
- API のリクエスト/レスポンス形式や DB スキーマを変更した場合、`docs/implementation.md` や README（英語版・日本語版）との整合を確認する。

## 重要な共通ルールの要約

<!-- AI-PLATFORM:START -->
## AI Platform 共通ルール（同期管理）

- 変更前に関連実装・設定・テストを確認し、既存の設計と命名を尊重する。
- 必要最小限の差分を選び、外部入力を検証する。TypeScript は型安全性、Python は型ヒントと明確な例外処理を優先する。
- 不具合修正には回帰テストを追加し、lint・型チェック・テスト・ビルドを実行する。テスト削除やチェック無効化で問題を回避しない。
- Secret・個人情報を出力しない。認証、認可、DB、公開 API は根拠なく変更しない。
- 実行していない検証を成功と報告せず、PR には変更内容、テスト結果、リスク・未検証事項を記載する。

詳細: `sj55576/ai-platform` の `prompts/coding-agent-typescript-python.md`
<!-- AI-PLATFORM:END -->
