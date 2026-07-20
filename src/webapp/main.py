"""地震保険 即時補償額デモ Webアプリ(FastAPI + htmx)。

チャット経路(LM Studio + payout MCP)と地図経路(このFastAPIアプリ)は
data/app_state/{config,latest}.json を介して連携する(payout_mcp.state参照)。
"""

from __future__ import annotations

import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import markdown  # noqa: E402
from fastapi import FastAPI, Form, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from payout_mcp import state  # noqa: E402
from payout_mcp.server import (  # noqa: E402
    run_estimate_payout_for_address,
    run_explain_payout,
    run_get_damage_image,
)
from webapp import lmstudio  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 前回セッションの残骸(建物マーカー等)を初期表示に出さないよう、起動時に一度だけクリアする。
    state.reset_latest()
    # モード切替UIは撤去済みのため、起動時は常にCSVモックへ戻す
    # (POST /api/mode は残っているので、必要ならcurl等でliveへ切替可能)。
    state.write_config(dict(state.DEFAULT_CONFIG))
    yield


WEBAPP_DIR = Path(__file__).resolve().parent
app = FastAPI(title="地震保険 即時補償額デモ", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEBAPP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEBAPP_DIR / "templates")

# 単一セッション前提の簡易な会話履歴(デモ用途、プロセス内メモリのみで永続化しない)
_chat_history: list[dict] = []


def _use_fastalert(config: dict) -> bool:
    return config.get("intensity_mode") == "live" or config.get("features_mode") == "live"


_MATH_PLACEHOLDER = "\x00MATH{}\x00"


def _render_markdown_with_math(text: str) -> str:
    """LaTeX区間($$...$$、$...$)をmarkdown変換から保護しつつHTML化する。

    python-markdownはLaTeXを解釈しないため、数式中の*や_をmarkdown記法として誤変換してしまう
    (例: w1*S_i が w1<em>S_i</em> のように壊れる)。数式区間を退避してからmarkdown変換し、
    変換後に元のLaTeX文字列へ復元することで、クライアント側のKaTeXがそのまま解釈できるようにする。
    """
    placeholders: list[str] = []

    def _stash(match: re.Match) -> str:
        placeholders.append(match.group(0))
        return _MATH_PLACEHOLDER.format(len(placeholders) - 1)

    # $$...$$(複数行可)を先に退避してから、残りの$...$(単一行)を退避する
    protected = re.sub(r"\$\$.+?\$\$", _stash, text, flags=re.DOTALL)
    protected = re.sub(r"\$[^$\n]+?\$", _stash, protected)

    html = markdown.markdown(protected)

    for i, original in enumerate(placeholders):
        html = html.replace(_MATH_PLACEHOLDER.format(i), original)

    return html


def _chat_turn_response(request: Request, message: str, answer: str):
    _chat_history.append({"role": "user", "content": message})
    _chat_history.append({"role": "assistant", "content": answer})
    # 例文ボタンは「補償額→根拠(平易な説明)→数式での説明」の順に誘導する:
    # 補償額の回答後は根拠ボタン、根拠・理由を尋ねた後は数式ボタンを出す。
    has_payout = "payout" in state.read_latest()
    asked_reason = ("根拠" in message) or ("理由" in message)
    return templates.TemplateResponse(
        request,
        "partials/chat_turn.html",
        {
            "user_message": message,
            "assistant_message_html": _render_markdown_with_math(answer),
            "show_explain_button": has_payout and not asked_reason,
            "show_math_button": has_payout and asked_reason,
        },
    )


@app.get("/")
async def index(request: Request):
    config = state.read_config()
    return templates.TemplateResponse(request, "index.html", {"config": config})


@app.post("/api/mode")
async def update_mode(intensity_mode: str = Form(...), features_mode: str = Form(...)):
    config = state.write_config({"intensity_mode": intensity_mode, "features_mode": features_mode})
    return f"適用済み(震度={config['intensity_mode']}, 特徴量={config['features_mode']})"


@app.get("/api/state")
async def get_state():
    return JSONResponse(state.read_latest())


@app.post("/chat")
async def chat(request: Request, message: str = Form(...)):
    config = state.read_config()
    answer = await lmstudio.chat(message, _chat_history, use_fastalert=_use_fastalert(config))
    return _chat_turn_response(request, message, answer)


@app.post("/chat_direct")
async def chat_direct(request: Request, message: str = Form(...)):
    """LLMを経由しない直接計算フォールバック(デモが不安定な場合の保険)。"""
    answer = await _direct_answer(message)
    return _chat_turn_response(request, message, answer)


async def _direct_answer(message: str) -> str:
    if "画像" in message:
        result = run_get_damage_image({})
        if "error" in result:
            return result["error"]
        return (
            f"{result['markdown']}\n\n"
            f"補償額の算定で影響が大きかった被害タイプ「{result['damage_type']}」に対応する、"
            f"{result['muni_name']}で実際に投稿された被害画像です。"
        )

    if "根拠" in message or "理由" in message:
        result = run_explain_payout({})
        if "error" in result:
            return result["error"]
        if "数式" not in message:
            # 数式が明示されない限りは、数式・重みを出さない平易な説明のみ返す
            return result["explanation_ja"]
        c = result["contributions"]
        w = result["weights"]
        breakdown = "、".join(
            f"{key.split('_', 1)[-1]}: {value:.2f}"
            for key, value in c["feature_breakdown"].items()
        )
        return (
            f"{result['explanation_ja']}\n\n"
            "**計算の内訳**\n"
            f"- 計算式: {result['formula']}\n"
            f"- 震度スコア S_i = {result['s_i']}, 切片 w0 = {w['w0']}, 震度の重み w1 = {w['w1']}\n"
            f"- w1×S_i = {c['w1*S_i']:.3f}\n"
            f"- 特徴量ごとの寄与(重み×特徴量値。0は算定に未反映): {breakdown or 'なし'}\n"
            f"- 特徴量の合計寄与 feature_total = {c['feature_total']:.3f}\n"
            f"- z = w0 + w1×S_i + feature_total = {c['z']:.3f}\n"
            f"- 支払率 = 1/(1+exp(-z)) = {result['payout_ratio']:.3f}\n"
            f"- 補償額 = 支払率 × 再調達価額(2,000万円) = {result['payout_yen_formatted']}"
        )

    result = await run_estimate_payout_for_address({"address": message})
    if "error" in result:
        return result["error"]
    return f"補償額は{result['payout']['payout_yen_formatted']}です。"
