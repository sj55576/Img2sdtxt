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

### 3. Python 3.8+

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
git clone https://github.com/sj55576/Img2sdtxt.git
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
| `SD_API_URL` | `http://localhost:7860` | AUTOMATIC1111 APIのURL |
| `API_HOST` | `0.0.0.0` | APIサーバーのバインドアドレス |
| `API_PORT` | `8000` | APIサーバーのポート番号 |
| `DEBUG` | `false` | デバッグモード / ホットリロード |
| `CORS_ALLOWED_ORIGINS` | `*` | 許可するブラウザOrigin（カンマ区切り）。本番環境では明示指定を推奨 |
| `CORS_ALLOW_CREDENTIALS` | `false` | 認証情報付きCORSリクエストを許可。Originを制限した場合のみ有効化推奨 |
| `TRUST_PROXY_HEADERS` | `false` | 信頼済みリバースプロキシ配下でのみ `X-Forwarded-For` / `X-Real-IP` を信頼 |
| `HTTPS_ENABLED` | `false` | HTTPSで起動する |
| `SSL_CERTFILE` | *(自動)* | TLS証明書ファイルのパス（PEM形式） |
| `SSL_KEYFILE` | *(自動)* | TLS秘密鍵ファイルのパス（PEM形式） |
| `WEBHOOK_URL` | *(空)* | Webhook送信先URL。空の場合は通知を無効化 |
| `WEBHOOK_EVENTS` | `job_completed,job_failed,batch_completed` | 通知対象イベント（カンマ区切り）（`job_completed`, `job_failed`, `job_cancelled`, `batch_completed`） |
| `WEBHOOK_FORMAT` | `generic` | ペイロード形式：`generic`、`discord`、`slack` のいずれか |
| `WEBHOOK_TIMEOUT` | `5` | Webhookリクエストのタイムアウト秒数 |

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

## プロジェクト構成

```
Img2sdtxt/
├── main.py                  # FastAPIアプリケーション・全APIルート
├── config.py                # アプリ設定・オプションリスト
├── llm_client.py            # LLMサーバーとの通信
├── prompt_generator.py      # プロンプト生成ロジック
├── sd_client.py             # Stable Diffusion APIクライアント
├── history.py               # SQLite履歴管理
├── presets.py               # プリセットテンプレート管理
├── requirements.txt         # Python依存パッケージ
├── .env.example             # 環境変数テンプレート
├── run.bat / run.sh         # ワンクリック起動スクリプト
├── setup.bat / setup.sh     # セットアップのみのスクリプト
├── data/                    # 実行時データ（DB・プリセット・パラメータ）
│   ├── history.db
│   ├── presets.json
│   └── last_params.json
├── outputs/                 # 生成済み画像（自動作成）
│   └── YYYY-MM-DD/
│       ├── *.png
│       ├── *_metadata.json
│       └── thumbs/
└── static/
    ├── index.html           # WebアプリケーションUI
    ├── style.css            # スタイルシート
    └── script.js            # JavaScriptロジック
```

---

## APIエンドポイント

### プロンプト生成

| メソッド | パス | 説明 |
|---------|------|------|
| `POST` | `/api/generate-prompts` | 画像1枚からプロンプト生成 |
| `POST` | `/api/generate-prompts-batch` | 最大10枚の画像を一括処理 |
| `POST` | `/api/generate-prompts-text` | テキスト説明からプロンプト生成 |
| `POST` | `/api/refine-prompt` | 既存プロンプトの改善・強化 |

### 履歴

| メソッド | パス | 説明 |
|---------|------|------|
| `GET` | `/api/history` | 履歴一覧（`limit`・`offset`・`search`・`style`・`quality`・`favorites_only`対応） |
| `GET` | `/api/history/export` | 全履歴をJSON・CSV・XLSXとしてダウンロード（`format`） |
| `PUT` | `/api/history/{id}/favorite` | お気に入りのトグル |
| `DELETE` | `/api/history/{id}` | 特定エントリを削除 |
| `DELETE` | `/api/history` | 全履歴を削除 |

### プリセット

| メソッド | パス | 説明 |
|---------|------|------|
| `GET` | `/api/presets` | 全プリセット一覧 |
| `POST` | `/api/presets` | カスタムプリセット作成 |
| `DELETE` | `/api/presets/{id}` | カスタムプリセット削除 |

### Stable Diffusion

| メソッド | パス | 説明 |
|---------|------|------|
| `GET` | `/api/sd/status` | A1111接続確認 |
| `GET` | `/api/sd/models` | 利用可能なモデル一覧 |
| `GET` | `/api/sd/loras` | 利用可能なLoRA一覧 |
| `GET` | `/api/sd/upscalers` | 利用可能なアップスケーラー一覧 |
| `POST` | `/api/sd/generate` | txt2img（テキストから画像生成） |
| `POST` | `/api/sd/generate-multi-model` | 複数モデルで順序に txt2img 生成 |
| `POST` | `/api/sd/img2img` | img2img（画像から画像生成） |
| `POST` | `/api/sd/inpaint` | インペイント |

**`/api/sd/generate` リクエスト（JSON）:**
```json
{
  "positive": "プロンプト...",
  "negative": "ネガティブプロンプト...",
  "width": 512,
  "height": 512,
  "steps": 20,
  "cfg_scale": 7.0,
  "sampler": "Euler a",
  "seed": -1,
  "batch_size": 1,
  "model": "",
  "loras": "",
  "enable_hr": false,
  "hr_scale": 2.0,
  "hr_upscaler": "R-ESRGAN 4x+",
  "hr_second_pass_steps": 0,
  "hr_denoising_strength": 0.7
}
```

### その他

| メソッド | パス | 説明 |
|---------|------|------|
| `GET` | `/api/config` | アプリ設定情報 |
| `GET` | `/health` | ヘルスチェック |
| `GET` | `/api/outputs` | ギャラリー画像一覧（`date`・`mode`・`limit`・`offset`対応） |
| `GET` | `/api/last-params/{feature}` | 最後のパラメータを取得 |
| `POST` | `/api/last-params/{feature}` | 最後のパラメータを保存 |

`{feature}` に指定できる値: `generate`, `sd`, `img2img`, `inpaint`, `multi_model`

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
