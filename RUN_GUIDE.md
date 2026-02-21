# Img2sdtxt - アプリケーション実行ガイド

このドキュメントは、Windows と Linux/macOS でアプリケーションを実行するための方法を説明しています。

## 必須要件

- **Python 3.8 以上**
- **LLM サーバー** (デフォルト: `http://localhost:1234/v1`)
- **Stable Diffusion API** (デフォルト: `http://localhost:7860`)

## Windows での実行

### 方法 1: 自動セットアップと起動（推奨）

**run.bat** をダブルクリックするか、コマンドプロンプトで実行します：

```cmd
run.bat
```

このスクリプトは以下を自動的に行います：
- Python 仮想環境の作成（存在しない場合）
- 依存パッケージのインストール
- `.env` ファイルのデフォルト設定（存在しない場合）
- アプリケーションの起動

### 方法 2: セットアップのみ実行

```cmd
setup.bat
```

このスクリプトは以下を行います：
- Python 仮想環境の作成
- 依存パッケージのインストール

その後、仮想環境を有効化して手動でアプリを起動できます：

```cmd
venv\Scripts\activate.bat
python main.py
```

### 方法 3: 手動セットアップ

```cmd
# 仮想環境を作成
python -m venv venv

# 仮想環境を有効化
venv\Scripts\activate.bat

# 依存パッケージをインストール
pip install -r requirements.txt

# アプリケーションを起動
python main.py
```

## Linux/macOS での実行

### 方法 1: 自動セットアップと起動（推奨）

```bash
chmod +x run.sh
./run.sh
```

または：

```bash
bash run.sh
```

このスクリプトは以下を自動的に行います：
- Python 仮想環境の作成（存在しない場合）
- 依存パッケージのインストール
- `.env` ファイルのデフォルト設定（存在しない場合）
- アプリケーションの起動

### 方法 2: セットアップのみ実行

```bash
chmod +x setup.sh
./setup.sh
```

または：

```bash
bash setup.sh
```

その後、仮想環境を有効化して手動でアプリを起動できます：

```bash
source venv/bin/activate
python main.py
```

### 方法 3: 手動セットアップ

```bash
# 仮想環境を作成
python3 -m venv venv

# 仮想環境を有効化
source venv/bin/activate

# 依存パッケージをインストール
pip install -r requirements.txt

# アプリケーションを起動
python main.py
```

## 環境設定

### .env ファイルについて

アプリケーションは `.env` ファイルから環境変数を読み込みます。スクリプトを初回実行時にデフォルトの `.env` が自動生成されます。

**デフォルト設定：**

```env
# LLM Server Configuration
LLM_SERVER_URL=http://localhost:1234/v1
LLM_MODEL=gpt-3.5-turbo

# Stable Diffusion API Configuration
SD_API_URL=http://localhost:7860

# API Server Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false
```

### カスタマイズ方法

`.env` ファイルを編集して以下を設定できます：

| 変数 | 説明 | デフォルト |
|------|------|----------|
| `LLM_SERVER_URL` | LLM サーバーの URL | `http://localhost:1234/v1` |
| `LLM_MODEL` | 使用する LLM モデル | `gpt-3.5-turbo` |
| `SD_API_URL` | Stable Diffusion API の URL | `http://localhost:7860` |
| `API_HOST` | API サーバーのバインドアドレス | `0.0.0.0` |
| `API_PORT` | API サーバーのポート番号 | `8000` |
| `DEBUG` | デバッグモード | `false` |

## アプリケーションの使用

起動後、以下の URL でアプリケーションにアクセスできます：

```
http://localhost:8000
```

### API ドキュメント

FastAPI の自動生成ドキュメント：

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## トラブルシューティング

### Python が見つからないエラー

**Windows:**
- Python が PATH に追加されていることを確認してください
- Python を再インストールし、インストール時に「Add Python to PATH」を選択してください

**Linux/macOS:**
```bash
sudo apt-get install python3 python3-venv python3-pip  # Ubuntu/Debian
brew install python3  # macOS
```

### LLM サーバーが接続できないエラー

LLM サーバーが起動していることを確認してください：

```bash
# LLM サーバーの起動例
# ollama serve  # または他の LLM サーバー
curl http://localhost:1234/v1/models
```

### Stable Diffusion API が接続できないエラー

Stable Diffusion API が起動していることを確認してください：

```bash
# Stable Diffusion WebUI が起動していることを確認
curl http://localhost:7860/config
```

### 依存パッケージのインストールエラー

```bash
# Windows
venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt

# Linux/macOS
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 仮想環境の無効化

```cmd
# Windows
deactivate

# Linux/macOS
deactivate
```

## まとめ

| OS | 推奨実行方法 |
|----|----------|
| **Windows** | `run.bat` をダブルクリック |
| **Linux/macOS** | `bash run.sh` または `./run.sh` |

スクリプトが問題を自動的に処理するため、初回使用時は推奨方法を使用することをお勧めします。
