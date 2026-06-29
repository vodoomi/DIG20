# DIG20 FASTALERT MCP APP

## Setup

環境構築の手順は以下の通りです。ssh接続したRTX 5090での動作を前提としています。

### 1. LM Studioのインストール

```bash
# インストール
curl -fsSL https://lmstudio.ai/install.sh | bash
# パスを通す
echo 'export PATH="/home/abemi/.lmstudio/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 2. LLMのダウンロード

```bash
lms get -y qwen/qwen3.6-35b-a3b # qwen3.6-27b@q8_0
```

### 3. LM Studioの設定

```bash
cp config/http-server-config.json ~/.lmstudio/.internal/http-server-config.json
cp config/mcp.json ~/.lmstudio/mcp.json
```

### 4. LM Studio APIキーの取得

こちらはローカルPCでの操作になります。

1. ローカルPCにGUIで操作できるLM Studioをインストールして起動します。
2. ローカルPCのLM Studioで、左メニューの 「Developer」をクリックします。
3. 画面中央上部の「Server Settings」にある 「Require Authentication」を ON に切り替えます。
4. 同様に 「Allow calling servers from mcp.json」も ON に切り替えます。
5. 「Manage Tokens」 をクリックし、「Create new token」 から適当なトークンを1つ作成し保存します。（これが`LM_STUDIO_API_KEY`）
6. この操作を行った瞬間に、LM Studioがバックグラウンドで permissions-store.json をフォルダ内に自動生成します。
7. scpで転送する
    ```bash
    scp ~/.lmstudio/.internal/permissions-store.json <ユーザー名>@<IPアドレス>:~/.lmstudio/.internal/
    ```

### 5. FASTALERT MCPの認証

こちらもローカルPCでの操作になります。以下のコマンド実行後に表示されるブラウザのポップアップでログインして認証してください。

```bash
# FASTALERT MCPの認証
npx mcp-remote https://app.fastalert.jp/mcp/sse
# 認証情報の転送
scp -r ~/.mcp-auth/ <ユーザー名>@<IPアドレス>:~/.mcp-auth/
```


## Inference

ssh接続したRTX 5090上で、実行してください。

### 1. LM Studio APIサーバーの起動

```bash
lms load qwen3.6-35b-a3b --gpu max -c 32768
lms server start
```

### 2. APIリクエストの送信

```bash
curl http://localhost:1234/api/v1/chat \
  -H "Authorization: Bearer ${LM_STUDIO_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.6-35b-a3b",
    "input": "FASTALERT MCPを使って、国内の避難所の状況を教えてください。具体的にはfeastalert_topicsを使って、2024/01/01から2024/01/10の期間に限定し、categoryを気象・災害、locationsを石川県、limitを100として、取得後「避難 不足」に関連するトピックを決めて、それぞれのIDからdetailを取得してください。",
    "integrations": [
      {
        "type": "plugin",
        "id": "mcp/fastalert"
      }
    ],
    "context_length": 32768
  }'
```

### 3. モデルの停止

```bash
lms unload qwen3.6-35b-a3b
lms server stop
lms daemon down
```
