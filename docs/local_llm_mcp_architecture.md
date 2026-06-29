現在、以下の「ヘッドレスGPUサーバーにおけるローカルLLMとリモートMCPの統合システム」が正常に稼働しています。現在のシステム設計と動作フローは以下の通りです。

---

### 1. システム構成・アーキテクチャ
このシステムは、「ブラウザがないヘッドレス環境（GPUサーバー）で、Web認証が必要なリモートMCP（FASTALERT）を使用する」という課題を解決するため、以下のハイブリッド構成を採用しています。

```text
[ ローカルPC (Windows/GUI) ]
  ├── 1. ブラウザで認証を実行 ──> [~/.mcp-auth] を生成
  └── 2. LM Studio GUIで認証/MCP許可を設定 ──> [.internal/ 設定ファイル群] を生成
            │
            │ (SCPでファイルをセキュア転送)
            ▼
[ GPUサーバー (Linux/ヘッドレス環境) ]
  ├── LM Studio (lms daemon & server) 
  │     ├── 設定適用: permissions-store.json & http-server-config.json
  │     └── モデル: Qwen 3.5 (9B) ※コンテキスト長は 32,768 (32k) でロード
  │
  └── mcp.json (mcp-remote 経由で FASTALERT MCP に接続)
        └── 認証情報の参照: ~/.mcp-auth (転送されたセッション情報を利用)
```

---

### 2. 主要な設計のポイント

#### ① ヘッドレス環境での認証回避（SCP同期戦略）
FASTALERTなどのリモートMCPサービス（SSE接続）はブラウザを介したOAuth認証が必要ですが、GPUサーバー（Linux CLI）単体ではブラウザを起動できません。
これを解決するため、**「ローカルPC（Windows）側で一度認証を完了させ、生成されたセッション情報（`~/.mcp-auth`）をGPUサーバーのホームディレクトリにSCPで直接転送する」**という設計にしています。

#### ② セキュリティとAPI連携（認証ファイルの同期）
API経由でMCP（プラグイン）を実行するためには、LM Studioのセキュリティ制限（認証の必須化、およびMCPの外部許可）をクリアする必要があります。
これも同様に、ローカルPCのGUI側で「Require Authentication」と「Allow calling servers from mcp.json」をONにして生成した以下のファイル群を、GPUサーバーの `~/.lmstudio/.internal/` にSCPで転送して同期させています。
- `http-server-config.json`（サーバー設定）
- `permissions-store.json`（`mcp` 実行権限付きAPIトークン）

これにより、GPUサーバー上のAPIサーバーに対して安全なBearerトークン認証（`Authorization: Bearer lm-sk-...`）を行いながらMCPを呼び出せるようにしています。

#### ③ コンテキスト長の最適化（10kのシステムプロンプト対策）
MCPサーバーを有効化すると、提供されるツールの仕様（スキーマ定義）がシステムプロンプトとして自動挿入されます。今回のFASTALERT MCPの場合、これだけで約10,000トークンを消費します。
標準のコンテキスト長（8,192など）では最初のメッセージ送信時にトークンオーバーフロー（`n_keep` エラー）を起こすため、**モデルのロード時にコンテキスト長（`n_ctx`）を `32,768` (32k) まで引き上げる**設計としています。

---

### 3. API経由での実行フロー
外部のクライアントから、GPUサーバーのAPI（`/api/v1/chat`）に対して以下の形式でリクエストを投げることで、LLM（Qwen 3.5）が必要に応じて自動的にFASTALERTのツール群を呼び出し、リアルタイム情報を踏まえた推論を行います。

- **Endpoint**: `POST http://<GPUサーバーのIP>:1234/api/v1/chat`
- **Headers**:
  - `Authorization: Bearer <ローカルから転送したトークン>`
  - `Content-Type: application/json`
- **Body例**:
  ```json
  {
    "model": "<Qwenのモデル識別子>",
    "input": "FASTALERT MCPを使って、最新の気象警報情報を教えてください。",
    "integrations": [
      {
        "type": "plugin",
        "id": "mcp/fastalert"
      }
    ],
    "context_length": 32768
  }
  ```
