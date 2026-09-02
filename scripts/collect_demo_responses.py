"""発表用デモの固定回答候補をQwenから収集する。

3つのデモ住所について、補償額・平易な根拠・数式説明・被害写真の順に実際の
LM Studio + payout MCP経路を通し、回答原文、計算state、画像をレビュー用に保存する。
``--only-reason`` の場合は保存済みstateを使い、平易な根拠だけを再収集して差し替える。
FASTALERTのliveモードは使用しない。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from payout_mcp import state  # noqa: E402
from payout_mcp.server import run_explain_payout  # noqa: E402
from webapp import lmstudio, quick_replies  # noqa: E402

DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "demo_responses"
MOCK_CONFIG = {"intensity_mode": "mock", "features_mode": "mock"}


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する。

    Returns:
        解析済みの引数。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="回答JSON・レビューMarkdown・画像の保存先",
    )
    parser.add_argument(
        "--only-reason",
        action="store_true",
        help="既存の回答JSONを使い、平易な根拠だけをQwenから再収集する",
    )
    return parser.parse_args()


async def collect_response(prompt: str, history: list[dict]) -> str:
    """Qwenへ1つの質問を送り、会話履歴へ回答を追加する。

    Args:
        prompt: ユーザーとして送る質問。
        history: 当該シナリオ内の会話履歴。

    Returns:
        Qwenの回答原文。
    """
    answer = await lmstudio.chat(prompt, history, use_fastalert=False)
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": answer})
    return answer


async def download_image(image_url: str, destination_stem: Path) -> Path:
    """画像URLをローカルへ保存する。

    Args:
        image_url: ダウンロード対象URL。
        destination_stem: 拡張子を除く保存先パス。

    Returns:
        実際に保存した画像パス。

    Raises:
        RuntimeError: 応答が画像ではない場合。
        httpx.HTTPError: ダウンロードに失敗した場合。
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": "DIG20-demo-response-collector/1.0"},
    ) as client:
        response = await client.get(image_url)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "").split(";", 1)[0]
    suffix_by_type = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    suffix = suffix_by_type.get(content_type)
    if suffix is None:
        raise RuntimeError(f"画像ではない応答です: content-type={content_type}")

    destination = destination_stem.with_suffix(suffix)
    destination.write_bytes(response.content)
    return destination


async def collect_scenario(
    option: quick_replies.DemoAddress,
    output_dir: Path,
) -> dict:
    """1住所分の4回答と画像を収集する。

    Args:
        option: 対象となるデモ住所。
        output_dir: 収集結果の保存先。

    Returns:
        回答原文、state、画像情報を含む辞書。

    Raises:
        RuntimeError: MCPの計算・画像取得・固定数式回答に不整合がある場合。
    """
    state.reset_latest()
    history: list[dict] = []
    prompts = (
        ("payout", "補償額", option.message),
        ("reason", "平易な根拠", quick_replies.REASON_MESSAGE),
        ("math", "数式による根拠", quick_replies.MATH_MESSAGE),
        ("photo", "被害写真", quick_replies.PHOTO_MESSAGE),
    )
    turns = []

    for kind, label, prompt in prompts:
        print(f"[{option.key}] {label}を収集中...", flush=True)
        answer = await collect_response(prompt, history)
        turns.append(
            {
                "kind": kind,
                "label": label,
                "prompt": prompt,
                "answer": answer,
            }
        )

        latest = state.read_latest()
        if kind == "payout" and "payout" not in latest:
            raise RuntimeError(f"{option.key}: 補償額のstateが生成されませんでした")
        if kind == "math":
            expected = run_explain_payout({}).get("calculation_markdown")
            if answer.strip() != expected:
                raise RuntimeError(f"{option.key}: 数式回答が固定Markdownと一致しません")
        if kind == "photo" and "damage_image" not in latest:
            raise RuntimeError(f"{option.key}: 被害画像のstateが生成されませんでした")

    latest = deepcopy(state.read_latest())
    image = latest["damage_image"]
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    local_image_path = await download_image(
        image["image_url"],
        image_dir / option.key,
    )
    image["local_path"] = str(local_image_path.relative_to(output_dir))

    checks = {
        "payout_state_exists": "payout" in latest,
        "reason_mentions_fastalert": "FASTALERT" in turns[1]["answer"],
        "math_matches_fixed_markdown": (
            turns[2]["answer"].strip()
            == run_explain_payout({})["calculation_markdown"]
        ),
        "photo_markdown_in_answer": image["markdown"] in turns[3]["answer"],
        "image_downloaded": local_image_path.exists(),
    }

    return {
        "key": option.key,
        "label": option.label,
        "address": option.address,
        "turns": turns,
        "state": latest,
        "image": image,
        "checks": checks,
    }


async def collect_reason_only(scenario: dict) -> str:
    """保存済みstateを使って1住所分の平易な根拠だけを収集する。

    Args:
        scenario: 既存の回答と計算stateを含むシナリオ。

    Returns:
        Qwenが返した平易な根拠の回答原文。

    Raises:
        RuntimeError: 保存済みstateが不完全、またはQwenが固定回答を変更した場合。
    """
    saved_state = scenario.get("state", {})
    if "payout" not in saved_state:
        raise RuntimeError(f"{scenario.get('key')}: 保存済みの補償額stateがありません")

    state.reset_latest()
    state.merge_latest(deepcopy(saved_state))
    print(f"[{scenario['key']}] 平易な根拠だけを再収集中...", flush=True)
    answer = await lmstudio.chat(
        quick_replies.REASON_MESSAGE,
        history=[],
        use_fastalert=False,
    )
    expected = run_explain_payout({}).get("explanation_ja")
    if answer.strip() != expected:
        raise RuntimeError(f"{scenario['key']}: 理由回答が固定Markdownと一致しません")
    return answer


def build_review_markdown(payload: dict) -> str:
    """収集結果から人手確認用Markdownを生成する。

    Args:
        payload: 全シナリオの収集結果。

    Returns:
        レビュー用Markdown文字列。
    """
    lines = [
        "# 発表用デモ 回答候補レビュー",
        "",
        f"- 収集日時: {payload['collected_at']}",
        f"- モデル: `{payload['model']}`",
        "- モード: 震度=`mock`、被害特徴量=`mock`",
        "- 回答原文・計算state: [responses.json](responses.json)",
        "",
        "## 自動確認結果",
        "",
        "| 住所 | 補償額 | 震度 | FASTALERT言及 | 数式固定 | 写真保存 |",
        "|---|---:|---:|:---:|:---:|:---:|",
    ]
    for scenario in payload["scenarios"]:
        checks = scenario["checks"]
        payout_result = scenario["state"]["payout"]
        intensity_result = scenario["state"]["intensity"]
        lines.append(
            f"| {scenario['label']} | {payout_result['payout_yen_formatted']} | "
            f"{intensity_result['shindo_class']} | "
            f"{'✓' if checks['reason_mentions_fastalert'] else '×'} | "
            f"{'✓' if checks['math_matches_fixed_markdown'] else '×'} | "
            f"{'✓' if checks['image_downloaded'] else '×'} |"
        )

    for scenario in payload["scenarios"]:
        lines.extend(
            [
                "",
                f"## {scenario['label']}",
                "",
                f"- 入力住所: `{scenario['address']}`",
                f"- ジオコード結果: `{scenario['state']['query']['matched_address']}`",
                f"- 画像カテゴリ: {scenario['image']['category']}",
                f"- 画像出典: [元投稿]({scenario['image']['source_url']}) / "
                f"[FASTALERT]({scenario['image']['fastalert_url']})",
            ]
        )
        for turn in scenario["turns"]:
            answer = turn["answer"]
            if turn["kind"] == "photo":
                answer = answer.replace(
                    scenario["image"]["image_url"],
                    scenario["image"]["local_path"],
                )
            lines.extend(
                [
                    "",
                    f"### {turn['label']}",
                    "",
                    "入力:",
                    "",
                    f"> {turn['prompt']}",
                    "",
                    "回答:",
                    "",
                    answer,
                ]
            )

    return "\n".join(lines) + "\n"


async def collect_all(output_dir: Path) -> dict:
    """全住所の回答候補を収集し、JSON・Markdownへ保存する。

    Args:
        output_dir: 収集結果の保存先。

    Returns:
        保存した全収集結果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    original_config = state.read_config()
    try:
        state.write_config(MOCK_CONFIG)
        scenarios = []
        for option in quick_replies.DEMO_ADDRESSES:
            scenarios.append(await collect_scenario(option, output_dir))

        payload = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "model": lmstudio.LM_STUDIO_MODEL,
            "mode": MOCK_CONFIG,
            "scenarios": scenarios,
        }
        (output_dir / "responses.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "review.md").write_text(
            build_review_markdown(payload),
            encoding="utf-8",
        )
        return payload
    finally:
        state.reset_latest()
        state.write_config(original_config)


async def recollect_reasons(output_dir: Path) -> dict:
    """既存回答のうち平易な根拠だけをQwenで再収集して保存する。

    Args:
        output_dir: 既存の回答JSONとレビューMarkdownを格納するディレクトリ。

    Returns:
        理由回答を差し替えた全収集結果。

    Raises:
        FileNotFoundError: 既存の回答JSONが存在しない場合。
        RuntimeError: シナリオまたは理由回答が不足している場合。
    """
    responses_path = output_dir / "responses.json"
    if not responses_path.is_file():
        raise FileNotFoundError(f"既存の回答JSONがありません: {responses_path}")

    payload = json.loads(responses_path.read_text(encoding="utf-8"))
    scenarios_by_key = {
        scenario["key"]: scenario
        for scenario in payload.get("scenarios", [])
    }
    original_config = state.read_config()
    try:
        state.write_config(MOCK_CONFIG)
        for option in quick_replies.DEMO_ADDRESSES:
            scenario = scenarios_by_key.get(option.key)
            if scenario is None:
                raise RuntimeError(f"既存の回答JSONに{option.key}がありません")

            answer = await collect_reason_only(scenario)
            reason_turn = next(
                (turn for turn in scenario.get("turns", []) if turn.get("kind") == "reason"),
                None,
            )
            if reason_turn is None:
                raise RuntimeError(f"{option.key}: 既存の理由回答がありません")
            reason_turn["answer"] = answer
            scenario.setdefault("checks", {})["reason_mentions_fastalert"] = (
                "FASTALERT" in answer
            )

        payload["collected_at"] = datetime.now(timezone.utc).isoformat()
        payload["model"] = lmstudio.LM_STUDIO_MODEL
        responses_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "review.md").write_text(
            build_review_markdown(payload),
            encoding="utf-8",
        )
        return payload
    finally:
        state.reset_latest()
        state.write_config(original_config)


def main() -> None:
    """回答収集を実行し、保存先を表示する。"""
    args = parse_args()
    output_dir = args.output_dir.resolve()
    if args.only_reason:
        payload = asyncio.run(recollect_reasons(output_dir))
        target = "理由回答の再収集"
    else:
        payload = asyncio.run(collect_all(output_dir))
        target = "全回答の収集"
    print(
        f"{target}完了: {len(payload['scenarios'])}シナリオ -> "
        f"{output_dir / 'review.md'}",
        flush=True,
    )


if __name__ == "__main__":
    main()
