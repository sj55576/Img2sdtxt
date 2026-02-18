# 🎨 Image to Stable Diffusion Prompt Generator

画像をアップロードしてStable Diffusion用のポジティブ・ネガティブプロンプトを自動生成するWebアプリです。ローカル実行のLLM（LM StudioまたはLemonade Server）を使用しています。

## 機能

- 📤 **画像アップロード**: JPG, PNG, WebP, GIF形式に対応（最大10MB）
- 🤖 **AI分析**: ローカルLLMで画像の特徴を分析
- ✍️ **プロンプト生成**:
  - ✅ ポジティブプロンプト（被写体、スタイル、品質など）
  - ❌ ネガティブプロンプト（避けたい要素）
- 📋 **テキスト説明モード**: 画像がない場合はテキスト説明からプロンプト生成
- 📋 **コピー機能**: 生成されたプロンプトをワンクリックでコピー

## 必要な環境

### 1. LLMサーバー（どちらか一つ）

#### LM Studio
- ダウンロード: https://lmstudio.ai
- インストール後、任意のモデルをダウンロード（例：neural-chat, llama 2など）
- 「Server」タブを開いてローカルサーバーを起動
- デフォルトポート: `http://localhost:1234`

#### Lemonade Server
- インストール: `pip install lemonade-server`
- 起動: `lemonade-server --port 8000`
- 設定: `.env`ファイルで`LLM_SERVER_URL`を変更

### 2. Python 3.8+

```bash
python --version
```

## インストール

### 1. 依存関係をインストール

```bash
pip install -r requirements.txt
```

### 2. 環境設定

`.env.example`をコピーして`.env`を作成：

```bash
cp .env.example .env
```

`.env`ファイルを編集して、LLMサーバーの設定を調整：

```
LLM_SERVER_URL=http://localhost:1234/v1
LLM_MODEL=gpt-3.5-turbo
API_PORT=8000
DEBUG=false
```

## 使用方法

### 1. LLMサーバーの起動

**LM Studioの場合:**
- LM Studioアプリを起動
- 「Server」タブを開く
- モデルが読み込まれていることを確認
- サーバーが起動していることを確認

**Lemonade Serverの場合:**
```bash
lemonade-server --port 8000
```

### 2. アプリケーションの起動

```bash
python main.py
```

ターミナルに以下のように表示されます：
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### 3. ブラウザでアクセス

http://localhost:8000 を開きます

## 使い方

### 画像からプロンプト生成

1. 「📤 Image Upload」タブを開く
2. 画像をドラッグ&ドロップ（または クリックして選択）
3. 「Generate Prompts」ボタンをクリック
4. ポジティブ・ネガティブプロンプトが生成されます
5. 「Copy」ボタンでプロンプトをコピー

### テキスト説明からプロンプト生成

1. 「✍️ Text Description」タブを開く
2. 画像の説明を入力
3. 「Generate from Text」ボタンをクリック
4. プロンプトが生成されます

## プロジェクト構成

```
Img2sdtxt/
├── main.py                 # FastAPI メインアプリケーション
├── config.py              # 設定ファイル
├── llm_client.py          # LLMサーバーとの通信
├── prompt_generator.py    # プロンプト生成ロジック
├── requirements.txt       # Python依存関係
├── .env.example          # 環境設定のテンプレート
├── .env                  # 環境設定（.env.exampleをコピー）
├── static/
│   ├── index.html        # Webアプリケーション UI
│   ├── style.css         # スタイル
│   └── script.js         # JavaScript ロジック
└── README-ja.md          # このファイル
```

## API エンドポイント

### POST /api/generate-prompts
画像ファイルからプロンプトを生成

**リクエスト:**
```
Content-Type: multipart/form-data
file: <image file>
```

**レスポンス:**
```json
{
  "success": true,
  "data": {
    "positive": "ポジティブプロンプト...",
    "negative": "ネガティブプロンプト..."
  }
}
```

### POST /api/generate-prompts-text
テキスト説明からプロンプトを生成

**リクエスト:**
```json
{
  "description": "画像の説明..."
}
```

**レスポンス:**
```json
{
  "success": true,
  "data": {
    "positive": "ポジティブプロンプト...",
    "negative": "ネガティブプロンプト..."
  }
}
```

### GET /api/config
設定情報を取得

**レスポンス:**
```json
{
  "llm_server": "http://localhost:1234/v1",
  "model": "gpt-3.5-turbo"
}
```

### GET /health
ヘルスチェック

**レスポンス:**
```json
{
  "status": "healthy",
  "llm_server": "connected",
  "message": "Service is running properly"
}
```

## トラブルシューティング

### 「LLM server is not available」エラーが出る
1. LM Studioが起動しているか確認
2. ポート番号が正しいか確認（デフォルト: 1234）
3. 環境変数`LLM_SERVER_URL`が正しいか確認

```bash
# LM Studioへの接続テスト
curl http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "any",
    "messages": [{"role": "user", "content": "test"}],
    "max_tokens": 10
  }'
```

### プロンプトが生成されない
1. LLMサーバーのモデルが読み込まれているか確認
2. ネットワーク接続を確認
3. ブラウザの開発者コンソール（F12）でエラーメッセージを確認

### 画像がアップロードできない
- ファイルサイズが10MBを超えていないか確認
- サポートされている形式（JPG, PNG, WebP, GIF）か確認

## 環境変数

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `LLM_SERVER_URL` | `http://localhost:1234/v1` | LLMサーバーのURL |
| `LLM_MODEL` | `gpt-3.5-turbo` | 使用するモデル名 |
| `API_HOST` | `0.0.0.0` | APIサーバーのホスト |
| `API_PORT` | `8000` | APIサーバーのポート |
| `DEBUG` | `false` | デバッグモード |

## 開発

### 依存関係の更新

```bash
pip freeze > requirements.txt
```

### フォーマット・Linting

```bash
# formatと一緒
pip install black flake8

# コード整形
black *.py

# Lint確認
flake8 *.py
```

## ライセンス

このプロジェクトはLICENSEファイルに従います。

## サポート

問題が発生した場合は、GitHubのIssueセクションで報告してください。

---

**楽しいプロンプト生成を！🚀**
