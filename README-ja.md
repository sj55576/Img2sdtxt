# 🎨 Img2sdtxt — Image to Stable Diffusion Prompt Generator

画像（またはテキスト説明）をローカルLLMで解析し、Stable Diffusion用のプロンプトを自動生成するWebアプリです。  
**AUTOMATIC1111 Stable Diffusion WebUI API** との直接連携により、アプリ内で画像生成も行えます。

> ⚠️ **検証中**: 本リポジトリは現在検証中であり、動作を確実に確認したものではありません。利用は自己責任でお願いします。

> 📖 **English documentation**: [README.md](README.md)

---

## 機能一覧

| 機能 | 説明 |
|------|------|
| 📸 **画像 → プロンプト** | 画像1枚をアップロードしてポジティブ・ネガティブプロンプトを生成 |
| 🗂️ **バッチ処理** | 最大10枚の画像を一括処理 |
| ✍️ **テキスト → プロンプト** | テキスト説明からSDプロンプトを生成 |
| ✨ **プロンプト改善** | 既存のプロンプトをLLMで改善・強化（任意の改善指示も指定可） |
| ⚙️ **スタイル / トーン / クオリティ** | 8スタイル・8トーン・3クオリティレベルでカスタマイズ |
| 🧩 **参照画像の合成** | 役割を指定した2〜3枚の参照画像から1つのプロンプトを生成 |
| 🎨 **プリセット** | 12種類の組み込みスタイルプリセット＋カスタムプリセット |
| 🖼️ **SD txt2img** | A1111 APIで直接テキストから画像生成 |
| 🔄 **SD img2img** | 既存画像をもとに新しい画像を生成 |
| 🖌️ **SD インペイント** | 画像の特定領域をインペイント |
| 🌟 **マルチモデル生成** | 複数のモデルで順序に画像生成（1つのプロンプトから複数モデルで生成） |
| 📋 **履歴** | 全文検索・スタイル/クオリティフィルタ・お気に入り対応のSQLite履歴 |
| ⭐ **お気に入り** | 履歴エントリをお気に入りにマークしてすばやくアクセス |
| 📤 **履歴エクスポート** | プロンプト履歴全件をJSONファイルとしてダウンロード |
| 🗃️ **ギャラリー** | 生成済み画像のブラウズ・フィルタ・ページネーション |
| 💾 **パラメータ保持** | 最後に使用したパラメータを自動復元 |
| 📁 **フォルダランダム読み込み** | ローカルフォルダからランダムに画像を選択 |
| 🧩 **ダイナミックプロンプト** | `{a|b}` 構文と `__wildcard__` ファイルによる展開（SD生成ごとの展開にも対応） |
| 🎛️ **ControlNet** | モデル・プリプロセッサ・参照画像をUIから設定 |
| 🧪 **A/B比較・XY Plot** | プロンプトやStable Diffusionパラメータを比較 |
| ⏳ **ジョブキュー** | 優先度・ETA・キャンセル・WebSocket通知に対応 |
| 🔌 **LLMフォールバック** | 実際に応答したprovider/modelを記録し自動切替 |
| 📊 **稼働状況の可視化** | Request ID、JSONログ、`/metrics`、キャッシュ・キュー統計 |
| 🌐 **多言語UI** | 日本語・英語の翻訳とキーボードショートカット |

---

## 必要な環境

### 1. LLMサーバー（どちらか一つ）

#### LM Studio（推奨）
- ダウンロード: <https://lmstudio.ai>
- ビジョン対応モデルをロード（例：LLaVA、BakLLaVAなど）
- 「Server」タブを開いてローカルサーバーを起動
- デフォルトURL: `http://localhost:1234/v1`

#### Lemonade Server
```bash
pip install lemonade-server
lemonade-server --port 8000
```
`.env` に `LLM_SERVER_URL=http://localhost:8000/api/v1` を設定してください。

### 2. Stable Diffusion WebUI（画像生成を使う場合）
- [AUTOMATIC1111 WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui) をインストール
- `--api` フラグ付きで起動:
  ```bash
  python launch.py --api
  ```
- デフォルトURL: `http://localhost:7860`

### 3. Python 3.10+

---

## クイックスタート

### Windows
```cmd
run.bat
```

### Linux / macOS
```bash
bash run.sh
```

どちらのスクリプトも、仮想環境の作成・依存パッケージのインストール・`.env` の生成・サーバーの起動を自動で行います。

---

## 手動インストール

```bash
# 1. リポジトリをクローン
git clone https://github.com/kumakumapon/Img2sdtxt.git
cd Img2sdtxt

# 2. 依存パッケージをインストール
pip install -r requirements.txt

# 3. .env を作成
cp .env.example .env
# .env を編集して設定を調整

# 4. アプリケーションを起動
python main.py
```

ブラウザで <http://localhost:8000> を開きます。

---

## Docker

### クイックスタート

```bash
cp .env.example .env
# 必要に応じて .env を編集（詳細は下記）
docker compose up -d
```

ブラウザで <http://localhost:8000> を開きます。ログ確認: `docker compose logs -f img2sdtxt`。

このイメージは同梱の `Dockerfile`（Python 3.12-slim、非rootユーザー、`/health` への
`HEALTHCHECK`）からビルドされ、`docker-compose.yml` は `./data`・`./outputs`・`./ssl`
をボリュームとしてマウントするため、履歴・生成画像・TLS証明書はコンテナの
再起動/再ビルドをまたいで保持されます。

### LLMサーバーへの接続

#### オプションA — コンテナ内でOllamaを実行

`ollama` プロファイルを使ってアプリと一緒にOllamaを起動します:

```bash
docker compose --profile ollama up -d
```

`.env` では、コンテナ名でOllamaサービスを指定します（両サービスは
`img2sdtxt-net` Dockerネットワークを共有しています）:

```env
LLM_SERVER_URL=http://ollama:11434/v1
LLM_PROVIDER=openai_compatible
```

その後、起動中のコンテナにビジョン対応モデルをpullします:

```bash
docker compose exec ollama ollama pull llava
```

#### オプションB — ホスト上で動作するLM Studio / A1111 / Ollama

LLMサーバー（またはA1111）がコンテナではなくホストマシン上で直接動作している
場合は、`host.docker.internal` を使ってアクセスします:

```env
LLM_SERVER_URL=http://host.docker.internal:1234/v1
SD_API_URL=http://host.docker.internal:7860
```

- **Docker Desktop（Mac/Windows）**: `host.docker.internal` は自動的に解決される
  ため追加設定は不要です。
- **Linux**: `host.docker.internal` はデフォルトでは解決されないため、
  `docker-compose.yml` の `img2sdtxt` サービスには以下を同梱済みです:
  ```yaml
      extra_hosts:
        - "host.docker.internal:host-gateway"
  ```
  Compose を使わず `docker run` で起動する場合は
  `--add-host=host.docker.internal:host-gateway` を付けるか、
  ホストのLAN/DockerブリッジIP（例: `http://172.17.0.1:1234/v1`）を
  直接指定してください。

### Stable Diffusion WebUI（A1111）

ほとんどのユーザーはGPUへの直接アクセスと更新の容易さのためA1111をホスト上で
実行し、上記のように `SD_API_URL` をそこに向けます（`--api` フラグが必要）。
自分でコンテナ化したい場合のために、コメントアウトされた最小限の `sd-webui`
サービス定義を `docker-compose.yml`（`sd-webui` プロファイル配下）に用意しています。

### GPU利用

コンテナ化された `ollama`（または `sd-webui`）サービスにNVIDIA GPUへのアクセスを
与えるには、ホストに [NVIDIA Container
Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
をインストールし、`docker-compose.yml` の該当サービス内の
`deploy.resources.reservations.devices` ブロックのコメントを解除します:

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### ボリューム / 永続化

| ホスト側パス | コンテナ側パス | 内容 |
|-------------|----------------|------|
| `./data` | `/app/data` | SQLite履歴DB、プリセット、最後に使用したパラメータ |
| `./outputs` | `/app/outputs` | 生成された画像とメタデータ |
| `./ssl` | `/app/ssl` | 自動生成または指定したTLS証明書・秘密鍵 |
| `ollama-data`（名前付きボリューム） | `/root/.ollama` | ダウンロード済みOllamaモデル（`ollama` プロファイル使用時のみ） |

### リバースプロキシ

コンテナの前段でTLSを終端するNginxの設定例:

```nginx
server {
    listen 443 ssl;
    server_name example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

同等のCaddyfile:

```
example.com {
    reverse_proxy 127.0.0.1:8000
}
```

リバースプロキシ配下で運用する場合は、レート制限が実際のクライアントIPを
認識できるよう `.env` で `TRUST_PROXY_HEADERS=true` を設定し、コンテナ自体では
`HTTPS_ENABLED=false` のままにしてください（TLS終端はプロキシ側が担当します）。

---

## 環境変数

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `LLM_SERVER_URL` | `http://localhost:1234/v1` | LLMサーバーのURL |
| `LLM_MODEL` | `gpt-3.5-turbo` | 使用するモデル名 |
| `LLM_PROVIDER` | `openai_compatible` | 使用するprovider（`openai_compatible` / `anthropic` / `gemini`） |
| `LLM_CACHE_ENABLED` | `true` | LLM応答キャッシュを有効化 |
| `LLM_CACHE_TTL` | `3600` | キャッシュ保持秒数 |
| `LLM_FALLBACK_CHAIN` | *(空)* | 障害時に試すprovider IDの順序（カンマ区切り） |
| `LLM_HEALTH_CHECK_INTERVAL` | `60` | providerヘルスチェック間隔（秒） |
| `ANTHROPIC_API_KEY` | *(空)* | Anthropic APIキー |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Anthropicモデル名 |
| `GEMINI_API_KEY` | *(空)* | Google Gemini APIキー |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Geminiモデル名 |
| `SD_API_URL` | `http://localhost:7860` | AUTOMATIC1111 APIのURL |
| `API_HOST` | `127.0.0.1` | APIサーバーのバインドアドレス。ネットワーク公開を意図する場合のみ `0.0.0.0` を指定 |
| `API_PORT` | `8000` | APIサーバーのポート番号 |
| `DEBUG` | `false` | デバッグモード / ホットリロード |
| `LOG_LEVEL` | `INFO` | Pythonログレベル |
| `LOG_FORMAT` | `text` | `text` または `json`。JSONではRequest ID等を出力 |
| `CORS_ALLOWED_ORIGINS` | *(空)* | 許可するブラウザOrigin（カンマ区切り）。空は同一オリジンのみ。影響を理解しない限り `*` は使わない |
| `CORS_ALLOW_CREDENTIALS` | `false` | 認証情報付きCORSリクエストを許可。Originを制限した場合のみ有効化推奨 |
| `API_TOKEN` | *(空)* | バックアップ、履歴エクスポート/削除、実行中のプロバイダー変更、キャッシュ/ワイルドカード削除に適用する任意の Bearer トークン。localhost 外へ公開する場合は設定必須 |
| `TRUST_PROXY_HEADERS` | `false` | 信頼済みリバースプロキシ配下でのみ `X-Forwarded-For` / `X-Real-IP` を信頼 |
| `HTTPS_ENABLED` | `false` | HTTPSで起動する |
| `SSL_CERTFILE` | *(自動)* | TLS証明書ファイルのパス（PEM形式） |
| `SSL_KEYFILE` | *(自動)* | TLS秘密鍵ファイルのパス（PEM形式） |
| `RATE_LIMIT_ENABLED` | `true` | IPベースのレート制限を有効化 |
| `RATE_LIMIT_GENERATION` | `10` | 生成系APIの1分あたりリクエスト数 |
| `RATE_LIMIT_API` | `60` | その他APIの1分あたりリクエスト数 |
| `JOB_QUEUE_MAX_SIZE` | `20` | 保留できるジョブの最大数 |
| `XY_PLOT_MAX_CELLS` | `36` | XY Plotと安全なバリエーション数の上限 |
| `WILDCARD_BATCH_MAX_COMBINATIONS` | `36` | ワイルドカードの「全組み合わせ」バッチジョブで生成できる画像数の上限 |
| `WEBHOOK_URL` | *(空)* | Webhook送信先URL。空の場合は通知を無効化 |
| `WEBHOOK_EVENTS` | `job_completed,job_failed,batch_completed` | 通知対象イベント（カンマ区切り）（`job_completed`, `job_failed`, `job_cancelled`, `batch_completed`） |
| `WEBHOOK_FORMAT` | `generic` | ペイロード形式：`generic`、`discord`、`slack` のいずれか |
| `WEBHOOK_TIMEOUT` | `5` | Webhookリクエストのタイムアウト秒数 |
| `BACKUP_DIR` | `data/backups` | バックアップ保存先 |
| `AUTO_BACKUP_ENABLED` | `false` | 自動バックアップを有効化 |
| `AUTO_BACKUP_RETENTION` | `7` | 保持する自動バックアップ世代数 |
| `AUTO_BACKUP_INTERVAL_HOURS` | `24` | 自動バックアップ間隔 |
| `MAX_BACKUP_UPLOAD_SIZE` | `2147483648` | 復元ZIPの最大サイズ（バイト） |

---

## 稼働状況の可視化

すべてのレスポンスに `X-Request-ID` ヘッダーが付きます。既存のIDを送ると
ログとリクエストを関連付けられ、未指定の場合はサーバーがUUIDを発行します。
`.env` で `LOG_FORMAT=json` を指定すると、`ts`、`level`、`logger`、`msg`、
`request_id`、処理時間を含むJSON Lines形式でログを出力します。

Prometheus用の `GET /metrics` を提供しています（`API_TOKEN` を設定している
場合は `Authorization: Bearer <API_TOKEN>` が必要です）。

```yaml
scrape_configs:
  - job_name: img2sdtxt
    static_configs:
      - targets: ["localhost:8000"]
```

HTTP、LLM provider／フォールバック、Stable Diffusion、キャッシュ、レート制限、
ジョブキューのカウンター・ヒストグラム・ゲージを取得できます。

これらのメトリクスをすぐに可視化できる Grafana ダッシュボードを
[`docs/grafana/img2sdtxt-dashboard.json`](docs/grafana/img2sdtxt-dashboard.json)
に同梱しています（Grafana の Dashboards → New → Import からインポートし、
Prometheus データソースを指定してください）。

### 分散トレーシング（OpenTelemetry）

トレーシングはデフォルトで無効です。`OTEL_EXPORTER_OTLP_ENDPOINT` に
OTLP/HTTP コレクターのエンドポイント（例: `http://localhost:4318/v1/traces`）
を設定すると有効になります。

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
OTEL_SERVICE_NAME=img2sdtxt
```

`OTEL_SERVICE_NAME`（デフォルト `img2sdtxt`）でトレースに記録するサービス名を設定できます。

有効化すると、FastAPI のリクエストと外部への `requests` 呼び出し
（Stable Diffusion、OpenAI互換LLMプロバイダー）が自動計装され、各 LLM 呼び出しは
`llm.generate` スパンとして `llm.provider` / `llm.model` / `llm.mode` /
`llm.status` / `llm.duration_seconds` 属性つきで記録されます。
`opentelemetry-*` パッケージが未インストールの場合は、アプリを落とさず警告を
出してトレーシングをスキップします。

---

## HTTPS対応

`.env` に `HTTPS_ENABLED=true` を設定するとHTTPSが有効になります。

### オプション1 — 自己署名証明書の自動生成（開発用）

`HTTPS_ENABLED=true` を設定するだけです。証明書ファイルが存在しない場合、
アプリが `ssl/cert.pem` と `ssl/key.pem` を自動生成します（`openssl` のインストールが必要）。

```env
HTTPS_ENABLED=true
```

ブラウザで <https://localhost:8000> を開きます。  
自己署名証明書のためブラウザにセキュリティ警告が表示されます。**詳細設定 → 続行**
をクリックしてください。

### オプション2 — 独自証明書を使用（本番環境）

CA署名済みまたはLet's Encrypt証明書を指定します。

```env
HTTPS_ENABLED=true
SSL_CERTFILE=/etc/letsencrypt/live/example.com/fullchain.pem
SSL_KEYFILE=/etc/letsencrypt/live/example.com/privkey.pem
```

### 自己署名証明書を手動で生成する場合

```bash
mkdir -p ssl
openssl req -x509 -newkey rsa:4096 \
  -keyout ssl/key.pem -out ssl/cert.pem \
  -days 365 -nodes -subj "/CN=localhost"
```

---

## カスタマイズオプション

### スタイル
`photorealistic`（写実的）、`anime`（アニメ）、`painting`（絵画）、`watercolor`（水彩）、`concept_art`（コンセプトアート）、`sketch`（スケッチ）、`pixel_art`（ピクセルアート）、`3d_render`（3Dレンダリング）

### トーン
`natural`（自然）、`vibrant`（鮮やか）、`warm`（暖色）、`cool`（寒色）、`dark`（暗い）、`soft`（柔らかい）、`dramatic`（ドラマティック）、`cinematic`（映画的）

### クオリティレベル
| レベル | 追加キーワード |
|--------|----------------|
| `standard` | `best quality` |
| `high` | `best quality, masterpiece, highly detailed` |
| `ultra` | `best quality, masterpiece, highly detailed, 8k uhd, sharp focus, professional` |

---

## ダイナミックプロンプト / ワイルドカード

プロンプト（Generate、SD Generate、Img2Img、Inpaint、XY Plot）では、
`dynamic_prompts.py` が処理する sd-dynamic-prompts 互換の構文を使用できます。

| 構文 | 意味 |
|--------|---------|
| `{a\|b\|c}` | いずれか1つをランダムに選択（`{a\|{b\|c}}` のようなネストも可） |
| `__filename__` | `data/wildcards/filename.txt` から1行をランダムに選択 |
| `\{` `\}` `\|` | エスケープされたリテラル文字としてそのまま出力 |

ワイルドカードファイルは **Wildcards** ページ（`GET/POST /api/wildcards/`、
`GET/PUT/DELETE /api/wildcards/{name}`）から管理でき、展開プレビューと
組み合わせ総数のカウント（`POST /api/wildcards/expand`）もこのページから行えます。

テンプレートから画像を生成する方法は3通りあります。

- **生成ごとに1回展開** — SD Generate / Img2Img / Inpaint ページの「生成ごとに
  ワイルドカードを展開」チェックボックス（`SDGenerateRequest` /
  `SDMultiModelRequest` の `expand_wildcards`）を有効にするか、Positive Prompt
  欄の 🃏 **Expand** ボタンで生成前にその場で1回展開します。バッチ内の各画像は
  それぞれ個別に展開され、履歴には展開結果と元のテンプレートの両方が保存されます。
- **全組み合わせをテキストのみ確認** — Wildcards ページの「Preview」「Count
  combinations」ボタンは `POST /api/wildcards/expand` を呼び出し、画像を生成せずに
  テンプレートが生成しうる内容を確認できます。
- **全組み合わせを画像として生成** — Wildcards ページの「🎲 Generate all
  combinations」ボタンは `wildcard_batch` ジョブ（`POST /api/jobs/submit`）を投入し、
  組み合わせごとに1枚ずつ画像を生成します。ジョブ投入前に組み合わせ数が
  `WILDCARD_BATCH_MAX_COMBINATIONS` を超えていないか検証され、XY Plot の
  グリッドが大きすぎる場合に開始前に拒否されるのと同様の仕組みです。

---

## 組み込みプリセット

| プリセット名 | 説明 |
|-------------|------|
| Anime Style | アニメ・マンガスタイル |
| Photorealistic | 8K写実的スタイル |
| Oil Painting | 古典的な油絵スタイル |
| Watercolor | 柔らかい水彩画スタイル |
| Fantasy Art | 壮大なファンタジーコンセプトアート |
| Portrait Photo | ボケ背景のポートレート写真 |
| Realistic Portrait | 超写実的な人物描写 |
| Fashion Photo | 編集/ヴォーグスタイルの写真 |
| Cinematic Portrait | 映画的なシネマティック照明 |
| Street Snap | 自然な街撮りスナップ写真 |
| Studio Portrait | プロのスタジオポートレート |
| Natural Light Portrait | 黄金時間の屋外自然光ポートレート |

**プリセット**ページから独自のカスタムプリセットを作成・保存することもできます。

---

## バックアップ / リストア

`data/` 配下（プロンプト履歴・LLMキャッシュ・レートリミット状態・プリセット・
ワイルドカード）を、タイムスタンプ付きの単一ZIPにまとめて保存できます。

**UIから:** **💾 Backup** ページでバックアップの作成、ダウンロード、削除、
および保存済みバックアップ／アップロードしたZIPからの復元が行えます。

**CLIから:**

```bash
python main.py --backup ./backups/            # data/ のみをバックアップ
python main.py --backup ./backups/ --include-outputs   # outputs/ も含める
python main.py --restore ./backups/img2sdtxt-backup-20260724-120000.zip
```

**自動バックアップ** — `.env` で設定します:

```env
AUTO_BACKUP_ENABLED=true
AUTO_BACKUP_INTERVAL_HOURS=24
AUTO_BACKUP_RETENTION=7      # これを超えた古い世代は自動削除
#BACKUP_DIR=/path/to/backups # 既定値: data/backups
```

補足:

- SQLite データベースはオンラインバックアップAPIでスナップショットするため、
  アプリ稼働中に取得しても内容が壊れません。
- 復元時は（明示的に無効化しない限り）現在のデータを安全バックアップとして
  先に退避します。アーカイブに含まれないファイルが削除されることはありません。
- **復元後はサーバーを再起動してください。** 各モジュールは独自のSQLite接続を
  保持しており、再起動するまで復元前のデータを参照し続けます。
- `API_TOKEN` を設定すると、バックアップ用エンドポイントは
  `Authorization: Bearer <API_TOKEN>` を必須にします。アーカイブには全履歴が含まれるため、
  信頼できないネットワークに公開する場合は必ず設定し、リバースプロキシ側でもアクセスを制限してください。

---

## プロジェクト構成

```
Img2sdtxt/
├── main.py                  # FastAPI、ミドルウェア、ヘルス、メトリクス
├── config.py                # 環境変数設定とオプション一覧
├── routes/                  # プロンプト、SD、ジョブ、履歴、バックアップ等のAPI
├── providers/               # Anthropic / Geminiアダプター
├── llm_client.py            # OpenAI互換LLM通信
├── fallback.py              # providerフォールバックチェーン
├── prompt_generator.py      # プロンプト生成と応答正規化
├── sd_client.py             # Stable Diffusion通信と出力メタデータ
├── history.py               # SQLite履歴・タグ・バージョン・A/B記録
├── job_queue.py             # 非同期生成キューとWebSocket購読
├── dynamic_prompts.py       # ワイルドカード / `{a|b}` 展開エンジン
├── metrics.py               # Prometheus計測
├── logging_utils.py         # Request IDとJSONログ
├── tests/                   # ユニット・API回帰テスト
├── scripts/                 # CI用のドキュメント整合性チェック
├── requirements.txt         # 実行時依存パッケージ
├── .env.example             # 環境変数テンプレート
├── run.bat / run.sh         # ワンクリック起動スクリプト
├── setup.bat / setup.sh     # セットアップのみのスクリプト
├── data/                    # 実行時データ（DB・プリセット等）
├── outputs/                 # 生成画像とメタデータ（自動作成）
└── static/                  # UI、CSS、JavaScript、翻訳ファイル
```

---

## APIエンドポイント

サーバー起動中は `/docs` と `/openapi.json` でインタラクティブな完全スキーマを
確認できます。主な公開ルートは次のとおりです。

### プロンプト生成・比較

| メソッド | パス | 説明 |
|---------|------|------|
| `POST` | `/api/generate-prompts` | 画像1枚からプロンプト生成 |
| `POST` | `/api/generate-prompts-batch` | 最大10枚を独立処理 |
| `POST` | `/api/generate-prompts-blend` | 役割指定の2〜3枚から単一プロンプトを生成 |
| `POST` | `/api/generate-prompts-stream` | SSEストリーミング生成 |
| `POST` | `/api/generate-prompts-text` | テキストからプロンプト生成 |
| `POST` | `/api/generate-prompts-compare` | プロンプト候補を比較 |
| `POST` | `/api/refine-prompt` | プロンプトの改善・強化 |
| `POST` | `/api/compare/ab-generate` | 共通seedでA/B画像を生成 |
| `GET` | `/api/compare/ab-history` | A/B比較履歴を取得 |
| `POST` | `/api/compare/ab/{id}/vote` | A/Bの勝者を記録 |

### 履歴・タグ・バージョン

| メソッド | パス | 説明 |
|---------|------|------|
| `GET` | `/api/history` | 履歴一覧（`limit`・`offset`・`search`・`style`・`quality`・`favorites_only`・`tag`） |
| `GET` | `/api/history/export` | JSON・CSV・XLSXでエクスポート（`format`） |
| `GET` | `/api/history/diff` | 2つのプロンプトを比較 |
| `GET` | `/api/history/{id}/versions` | バージョンツリーを取得 |
| `POST` | `/api/history/{id}/rollback` | ロールバック版を作成 |
| `PUT` | `/api/history/{id}/favorite` | お気に入りを切替 |
| `DELETE` | `/api/history/{id}` | 履歴を1件削除 |
| `DELETE` | `/api/history` | 全履歴を削除 |
| `GET` | `/api/tags` | タグと使用回数を取得 |
| `GET` | `/api/tags/suggest` | タグ候補を取得 |
| `GET` | `/api/tags/categories` | タグカテゴリを取得 |
| `POST` | `/api/history/{id}/tags` | 履歴にタグを追加 |
| `DELETE` | `/api/history/{id}/tags/{tag}` | タグを削除 |

### Stable Diffusion

| メソッド | パス | 説明 |
|---------|------|------|
| `GET` | `/api/sd/status` | A1111とControlNetの状態を確認 |
| `GET` | `/api/sd/models` | モデル一覧 |
| `GET` | `/api/sd/loras` | LoRA一覧 |
| `GET` | `/api/sd/upscalers` | アップスケーラー一覧 |
| `GET` | `/api/sd/progress` | 生成進捗 |
| `WS` | `/api/sd/progress/ws` | 生成進捗をストリーム配信 |
| `GET` | `/api/sd/controlnet/models` | ControlNetモデル一覧（未導入時は空） |
| `GET` | `/api/sd/controlnet/modules` | ControlNetプリプロセッサ一覧 |
| `POST` | `/api/sd/generate` | txt2img生成 |
| `POST` | `/api/sd/generate-multi-model` | 複数モデルで順次生成 |
| `POST` | `/api/sd/img2img` | img2img生成 |
| `POST` | `/api/sd/inpaint` | ControlNet対応インペイント |
| `POST` | `/api/interrogate` | CLIP Interrogator / DeepDanbooru |
| `POST` | `/api/png-info` | A1111 PNGメタデータ読み取り |

### ジョブキュー・ダイナミックプロンプト

| メソッド | パス | 説明 |
|---------|------|------|
| `POST` | `/api/jobs/submit` | `txt2img`・`multi_model`・`xy_plot`・`wildcard_batch`を投入 |
| `GET` | `/api/jobs` | ジョブ一覧 |
| `GET` | `/api/jobs/{id}` | 状態・キュー位置・ETAを取得 |
| `POST` | `/api/jobs/{id}/cancel` | ジョブをキャンセル |
| `POST` | `/api/jobs/{id}/priority` | 優先度を変更 |
| `GET` | `/api/jobs/queue/stats` | 状態別のキュー統計 |
| `WS` | `/api/jobs/{id}/ws` | ジョブ進捗をストリーム配信 |
| `GET` | `/api/wildcards/` | ワイルドカード一覧 |
| `POST` | `/api/wildcards/` | ワイルドカード作成 |
| `GET` | `/api/wildcards/{name}` | ワイルドカード取得 |
| `PUT` | `/api/wildcards/{name}` | ワイルドカード更新 |
| `DELETE` | `/api/wildcards/{name}` | ワイルドカード削除 |
| `POST` | `/api/wildcards/expand` | 展開プレビュー／全組み合わせ生成 |

### ギャラリー・キャッシュ・バックアップ・LLM

| メソッド | パス | 説明 |
|---------|------|------|
| `GET` | `/api/outputs` | 生成画像一覧（各種フィルタ対応） |
| `GET` | `/api/outputs/filters` | モデル・サンプラーのフィルタ候補 |
| `POST` | `/api/outputs/download-zip` | 選択画像をZIPで取得 |
| `GET` | `/api/cache/stats` | LLMキャッシュ統計 |
| `DELETE` | `/api/cache` | LLMキャッシュを削除 |
| `POST` | `/api/backup/create` | バックアップ作成 |
| `GET` | `/api/backup/list` | バックアップ一覧 |
| `GET` | `/api/backup/download/{id}` | バックアップをダウンロード |
| `POST` | `/api/backup/restore` | バックアップをアップロードして復元 |
| `POST` | `/api/backup/restore/{id}` | 一覧からバックアップを復元 |
| `DELETE` | `/api/backup/{id}` | バックアップを削除 |
| `GET` | `/api/llm/providers` | provider設定・フォールバック状態 |
| `GET` | `/api/llm/health` | providerのヘルス・応答時間 |
| `POST` | `/api/llm/provider` | 使用providerを切替 |

### 設定・可視化

| メソッド | パス | 説明 |
|---------|------|------|
| `GET` | `/api/config` | アプリ設定とprovider一覧 |
| `GET` | `/api/stats` | 履歴・ギャラリー・タグ・活動統計 |
| `GET` | `/metrics` | Prometheusメトリクス |
| `GET` | `/health` | LLM/SDの状態と稼働時間 |
| `GET` | `/api/last-params/{feature}` | 最後のパラメータを取得 |
| `POST` | `/api/last-params/{feature}` | 最後のパラメータを保存 |

`{feature}` に指定できる値: `generate`, `sd`, `img2img`, `inpaint`, `multi_model`, `xyplot`

---

## 使い方

### 画像からプロンプト生成

1. サイドバーの「📤 Generate」をクリック
2. 「📸 Image」タブを選択し、画像をドラッグ&ドロップ（またはクリックして選択）
3. スタイル・トーン・クオリティ・プリセットをカスタマイズ（任意）
4. 「Generate Prompts」ボタンをクリック
5. 生成されたプロンプトを「Copy」ボタンでコピー

### テキストからプロンプト生成

1. サイドバーの「📤 Generate」をクリック
2. 「✍️ Text」タブを選択し、画像の説明を入力
3. 「Generate from Text」ボタンをクリック

### バッチ処理

1. サイドバーの「🗂️ Batch」をクリック
2. 最大10枚の画像をまとめてアップロード
3. スタイル・プリセットを設定して「Generate All」をクリック

### SD画像生成（txt2img）

1. サイドバーの「🖼️ SD Generate」をクリック
2. プロンプトや各種パラメータを設定
3. 「Generate」ボタンをクリック
4. 生成された画像は `outputs/YYYY-MM-DD/` に自動保存

### img2img

1. サイドバーの「🔄 Img2Img」をクリック
2. 元画像をアップロードし、プロンプトとデノイジング強度を設定
3. 「Generate」ボタンをクリック

### インペイント

1. サイドバーの「🖌️ Inpaint」をクリック
2. 画像をアップロードし、塗り替えたい領域をマスク
3. プロンプトを設定して「Generate」をクリック

### プロンプト改善（Refine）

1. サイドバーの「✨ Refine」をクリック
2. 改善したいポジティブ・ネガティブプロンプトを入力
3. 任意で改善指示（例：「もっとリアルに」）を入力
4. 「Refine Prompt」ボタンをクリック
5. 改善されたプロンプトと変更内容の説明を確認

---

## トラブルシューティング

### 「LLM server is not available」エラー
1. LLMサーバーが起動しているか確認
2. `.env` の `LLM_SERVER_URL` が正しいか確認
3. 接続テスト:
   ```bash
   curl http://localhost:1234/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"any","messages":[{"role":"user","content":"test"}],"max_tokens":10}'
   ```

### 「Stable Diffusion API is not available」エラー
1. A1111 WebUIを `--api` フラグ付きで起動しているか確認
2. `.env` の `SD_API_URL` が正しいか確認
3. 接続テスト: `curl http://localhost:7860/config`

### 画像がアップロードできない
- ファイルサイズが **10MB** 以下か確認
- 対応形式: **JPG・PNG・WebP・GIF**

### APIドキュメント（インタラクティブ）
- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

---

## ライセンス

[LICENSE](LICENSE) ファイルを参照してください。

---

**楽しいプロンプト生成・画像生成を！🚀**
