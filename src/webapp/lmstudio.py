"""LM Studio Agent API (/api/v1/chat) クライアント。

LM StudioはFASTALERT/payoutの各MCPをintegrationsパラメータで指定すると自動的にツール呼び出しを
編成する。レスポンスは output 配列(reasoning/message/tool_callが混在)で返るため、
type=="message" のうち最後の要素の content を最終回答として採用する
(2026-07-05, qwen/qwen3.6-35b-a3b で実測して確認済みのスキーマ)。
"""

from __future__ import annotations

import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen/qwen3.6-35b-a3b")
LM_STUDIO_API_KEY = os.environ.get("LM_STUDIO_API_KEY", "")

CHAT_TIMEOUT_SECONDS = 240.0

SYSTEM_PREAMBLE = """あなたは地震保険の補償額を案内するアシスタントです。以下のツールが使えます:
- geocode_address: 住所→緯度経度・自治体判定(質問の最初に呼ぶ)
- get_intensity: 震度取得
- compute_features: FASTALERT被害特徴量取得(倒壊・断水・火災など被害タイプ別の構成比)
- calculate_payout: 補償額計算
- explain_payout: 直近の計算の根拠を返す(震度・特徴量・重み・各項の寄与・計算式を含む。引数不要。
  過去の会話ターンでツール呼び出しが見えなくても、裏側の状態ファイルには前回の計算結果が保持されて
  いるので、迷わずこのツールを呼べば必ず答えられる)
- estimate_payout_for_address: geocode/intensity/features/payoutを1回で行う複合ツール

ルール(重要・厳守):
1. 「補償額」を尋ねられたら、余計なことを考えずに estimate_payout_for_address を1回呼ぶ。
2. 「根拠」を尋ねられたら、余計なことを考えずに explain_payout を1回呼ぶ(引数無し)。
   過去のツール呼び出しが会話履歴のテキストに見当たらなくても、それは表示上省略されているだけで
   実際には裏側で計算済みなので、再計算や様子見をせず、まず explain_payout を呼んで結果を見ること。
3. ツールを呼ぶ前に長々と検討しない。ルール1・2に従って即座にツールを呼び出すこと。
4. 補償額の回答は必ず「補償額は○○円です」という形式にする。
5. 根拠を説明するときは explain_payout が返す震度・特徴量(features)・重み(weights)・各項の寄与
   (contributions: w1*S_i, feature_breakdown, feature_total, zなど)・計算式(formula)を具体的な
   数値付きで示すこと。どの特徴量にどの重みがかかり、その結果どういう計算になったのかが分かる
   ように、数式や数値を隠さずに説明する。
6. 数式・変数・計算過程を書くときは、必ずすべて `$...$`(1行の式)または `$$...$$`(独立した式)で
   囲むこと。`w1*S_i` や `z = w0 + w1*S_i + ...` のような式を$で囲まずに地の文へ書かない。
   $で囲まなかった部分の * や _ はMarkdownの強調記号として誤解釈され表示が崩れるため、
   例外なく徹底すること。
"""


def _integrations(use_fastalert: bool) -> list[dict]:
    integrations = [{"type": "plugin", "id": "mcp/payout"}]
    if use_fastalert:
        integrations.append({"type": "plugin", "id": "mcp/fastalert"})
    return integrations


def _build_input(history: list[dict], user_message: str) -> str:
    """直近の会話履歴をテキスト連結してプロンプトを組み立てる。

    /api/v1/chat はセッションを保持しないため、履歴はこちらでテキストとして渡す。
    """
    lines = [SYSTEM_PREAMBLE, ""]
    for turn in history[-6:]:
        role = "ユーザー" if turn["role"] == "user" else "アシスタント"
        lines.append(f"{role}: {turn['content']}")
    lines.append(f"ユーザー: {user_message}")
    return "\n".join(lines)


async def chat(user_message: str, history: list[dict], use_fastalert: bool = False) -> str:
    """LM Studioにプロンプトを送り、最終回答テキストのみを返す。"""
    payload = {
        "model": LM_STUDIO_MODEL,
        "input": _build_input(history, user_message),
        "integrations": _integrations(use_fastalert),
        "context_length": 32768,
    }
    headers = {"Content-Type": "application/json"}
    if LM_STUDIO_API_KEY:
        headers["Authorization"] = f"Bearer {LM_STUDIO_API_KEY}"

    async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{LM_STUDIO_BASE_URL}/api/v1/chat", json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()

    return _extract_final_text(body)


def _extract_final_text(body: dict) -> str:
    """output配列からtype=="message"の最後の要素を最終回答として取り出す。

    未知のレスポンス形状が来た場合はデモを止めないよう、本文をJSON文字列で返す。
    """
    output = body.get("output")
    if isinstance(output, list):
        messages = [item.get("content", "") for item in output if item.get("type") == "message"]
        for message in reversed(messages):
            if message and message.strip():
                return message.strip()
    return json.dumps(body, ensure_ascii=False)
