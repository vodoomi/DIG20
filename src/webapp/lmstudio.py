"""LM Studio Agent API (/api/v1/chat) クライアント。

LM StudioはFASTALERT/payoutの各MCPをintegrationsパラメータで指定すると自動的にツール呼び出しを
編成する。レスポンスは output 配列(reasoning/message/tool_callが混在)で返るため、
type=="message" のうち最後の要素の content を最終回答として採用する
(2026-07-05, qwen/qwen3.6-35b-a3b で実測して確認済みのスキーマ)。
"""

from __future__ import annotations

import json
import os
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx
from dotenv import load_dotenv

load_dotenv()

LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen/qwen3.6-35b-a3b")
LM_STUDIO_API_KEY = os.environ.get("LM_STUDIO_API_KEY", "")

CHAT_TIMEOUT_SECONDS = 240.0
_LONG_DECIMAL_PATTERN = re.compile(r"(?<![\w.])(-?\d+\.\d{3,})(?![\w.])")
_DISPLAY_DECIMAL_PLACES = Decimal("0.01")

SYSTEM_PREAMBLE = """あなたは地震保険の補償額を案内するアシスタントです。以下のツールが使えます:
- geocode_address: 住所→緯度経度・自治体判定(質問の最初に呼ぶ)
- get_intensity: 震度取得
- compute_features: FASTALERT被害特徴量取得(倒壊・断水・火災など被害タイプ別の構成比)
- calculate_payout: 補償額計算
- explain_payout: 直近の計算の根拠を返す(震度・特徴量・重み・各項の寄与・計算式を含む。引数不要。
  過去の会話ターンでツール呼び出しが見えなくても、裏側の状態ファイルには前回の計算結果が保持されて
  いるので、迷わずこのツールを呼べば必ず答えられる)
- get_damage_image: 直近の補償額算定で影響が大きかった被害カテゴリの実際の被害画像を1枚返す(引数不要)
- estimate_payout_for_address: geocode/intensity/features/payoutを1回で行う複合ツール

ルール(重要・厳守):
1. 「補償額」を尋ねられたら、余計なことを考えずに estimate_payout_for_address を1回呼ぶ。
2. 「根拠」や「理由」を尋ねられたら、余計なことを考えずに explain_payout を1回呼ぶ(引数無し)。
   過去のツール呼び出しが会話履歴のテキストに見当たらなくても、それは表示上省略されているだけで
   実際には裏側で計算済みなので、再計算や様子見をせず、まず explain_payout を呼んで結果を見ること。
3. 「被害の状況を写真で教えて」「被害の様子を画像で見せて」のように写真・画像を求められたら、
   余計なことを考えずに get_damage_image を1回呼ぶ(引数無し)。回答には、返り値の markdown
   フィールドの文字列を一字も変えずそのまま貼り付ける
   (URLを自分で書き写さない・短縮しない・コードブロックで囲まない)。その後に1〜2文で、これが
   補償額算定で影響が大きかった被害カテゴリの実際の投稿画像であることを添える。
4. ツールを呼ぶ前に長々と検討しない。上記ルールに従って即座にツールを呼び出すこと。
5. 補償額の回答は必ず「補償額は○○円です」という形式にする。金額の部分を太字にすること。
   算定の上限に使う金額は、再調達価額ではなく法人契約の保険金額1,000万円である。
6. 根拠・理由の説明は、ユーザーが「数式を使って」と明示的に頼んだかどうかで出し分けること:
   - 「数式を使って」と明示されていない普通の質問(「根拠を教えてください」「理由を教えて」など)では、
     explain_payout が返す explanation_ja の文字列を一字も変えず、そのまま回答として使うこと。
     見出し・箇条書き・太字・数値を省略、追加、言い換えしない。explanation_ja は、揺れの強さ、
     震度に対するベースの損害率、FASTALERTで確認した被害情報の水準、
     被害情報による損害率の上昇幅、最終的な補償額の順に構造化済みである。
   - 「数式を使って説明して」のように数式が明示的に求められた場合のみ、explain_payout が返す
     calculation_markdownの文字列を一字も変えず、そのまま回答として使うこと。数値を再計算したり、
     別の数式を追加したりしない。calculation_markdownには震度・特徴量・重み・各項の寄与・支払率・
     補償額が表示用に丸めた状態で含まれている。
7. 数式・変数・計算過程を書くときは、必ずすべて `$...$`(1行の式)または `$$...$$`(独立した式)で
   囲むこと。`w1*S_i` や `z = w0 + w1*S_i + ...` のような式を$で囲まずに地の文へ書かない。
   $で囲まなかった部分の * や _ はMarkdownの強調記号として誤解釈され表示が崩れるため、
   例外なく徹底すること。
8. 数式で説明するとき、計算途中の小数は小数第3位を四捨五入し、必ず小数第2位まで表示する。
   末尾の0も省略しない。保険金額・補償額など円単位の整数は、小数にせず3桁区切りで表示する。
   支払率は0〜1の小数ではなく、100倍した百分率を小数第2位まで表示する(例: 0.3091ではなく30.91%)。
   計算自体は丸め前の値で行い、丸めた表示値を式へ代入するときは等号ではなく `\\approx` を使う。
9. ブロック数式は横長にしない。一般式、数値の代入、計算結果を1つの数式へ詰め込まず、短い数式へ
   分割する。1つのブロック数式には原則として等号を1つだけ使い、説明文は数式の外へ書く。
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

    answer = _extract_final_text(body)
    if "数式" in user_message:
        return _round_math_decimals(answer)
    return answer


def _round_math_decimals(text: str) -> str:
    """数式回答に含まれる小数第3位以降を四捨五入する。

    すでに小数第2位までの値、円単位の整数、指数表記、URLは変更しない。
    """

    def _replace(match: re.Match[str]) -> str:
        try:
            value = Decimal(match.group(1)).quantize(
                _DISPLAY_DECIMAL_PLACES,
                rounding=ROUND_HALF_UP,
            )
        except InvalidOperation:
            return match.group(1)
        return f"{value:.2f}"

    return _LONG_DECIMAL_PATTERN.sub(_replace, text)


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
