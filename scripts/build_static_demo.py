"""固定回答から発表用の静的デモサイト資産を生成する。

LM Studio、MCP、FASTALERT、FastAPIへ接続せずにブラウザだけで動作するよう、
レビュー済み回答を表示用HTMLへ変換し、必要な画像とvendor資産を公開ディレクトリへコピーする。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

import markdown

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESPONSES_PATH = REPO_ROOT / "data" / "demo_responses" / "responses.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "site"
WEBAPP_STATIC_DIR = REPO_ROOT / "src" / "webapp" / "static"
REQUIRED_TURN_KINDS = {"payout", "reason", "math", "photo"}
MATH_PLACEHOLDER = "\x00MATH{}\x00"


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する。

    Returns:
        解析済みのコマンドライン引数。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--responses",
        type=Path,
        default=DEFAULT_RESPONSES_PATH,
        help="固定回答JSONのパス",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="静的サイトの出力先",
    )
    return parser.parse_args()


def render_markdown_with_math(text: str) -> str:
    """LaTeX区間を保護しながらMarkdownをHTMLへ変換する。

    Args:
        text: MarkdownとLaTeXを含む固定回答。

    Returns:
        クライアント側KaTeXで処理できるHTML文字列。
    """
    placeholders: list[str] = []

    def stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return MATH_PLACEHOLDER.format(len(placeholders) - 1)

    protected = re.sub(r"\$\$.+?\$\$", stash, text, flags=re.DOTALL)
    protected = re.sub(r"\$[^$\n]+?\$", stash, protected)
    html = markdown.markdown(protected)

    for index, original in enumerate(placeholders):
        html = html.replace(MATH_PLACEHOLDER.format(index), original)
    return html


def load_responses(path: Path) -> dict[str, Any]:
    """固定回答JSONを読み込む。

    Args:
        path: 固定回答JSONのパス。

    Returns:
        固定回答を格納した辞書。

    Raises:
        FileNotFoundError: 固定回答JSONが存在しない場合。
        ValueError: シナリオが存在しない場合。
    """
    if not path.is_file():
        raise FileNotFoundError(f"固定回答JSONが見つかりません: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("scenarios"):
        raise ValueError("固定回答JSONにシナリオがありません")
    return payload


def build_public_payload(source: dict[str, Any], responses_dir: Path) -> dict[str, Any]:
    """ブラウザ表示に必要な項目だけを抽出する。

    Args:
        source: 固定回答の全データ。
        responses_dir: 固定回答JSONを格納するディレクトリ。

    Returns:
        静的デモ用に最小化した公開データ。

    Raises:
        ValueError: 回答種別、画像パス、画像メタデータに不整合がある場合。
    """
    scenarios = [
        _build_public_scenario(scenario, responses_dir)
        for scenario in source["scenarios"]
    ]
    return {
        "collected_at": source.get("collected_at"),
        "progress_delay_ms": 600,
        "unsupported_message": (
            "このサイトは発表用デモのため、回答できる住所と質問を限定しています。"
            "画面に表示された選択肢から選んでください。"
        ),
        "scenarios": scenarios,
    }


def _build_public_scenario(
    scenario: dict[str, Any],
    responses_dir: Path,
) -> dict[str, Any]:
    turns = {turn["kind"]: turn for turn in scenario["turns"]}
    missing_kinds = REQUIRED_TURN_KINDS - turns.keys()
    if missing_kinds:
        raise ValueError(
            f"{scenario['key']}: 回答種別が不足しています: {sorted(missing_kinds)}"
        )

    image = scenario["image"]
    local_image = responses_dir / image["local_path"]
    if not local_image.is_file():
        raise ValueError(f"{scenario['key']}: 保存画像がありません: {local_image}")

    photo_answer = turns["photo"]["answer"]
    if image["local_path"] not in photo_answer or "pbs.twimg.com" in photo_answer:
        raise ValueError(f"{scenario['key']}: 写真回答がローカル画像を参照していません")

    state_image = scenario["state"].get("damage_image", {})
    if state_image.get("topic_id") != image.get("topic_id"):
        raise ValueError(f"{scenario['key']}: 被害画像のtopic IDが一致しません")
    if state_image.get("category") != image.get("category"):
        raise ValueError(f"{scenario['key']}: 被害画像のカテゴリが一致しません")

    public_turns = {
        kind: {
            "label": turns[kind]["label"],
            "prompt": turns[kind]["prompt"],
            "answer_html": render_markdown_with_math(turns[kind]["answer"]),
        }
        for kind in ("payout", "reason", "math", "photo")
    }
    state = scenario["state"]
    return {
        "key": scenario["key"],
        "label": scenario["label"],
        "address": scenario["address"],
        "turns": public_turns,
        "query": {
            key: state["query"].get(key)
            for key in (
                "address",
                "lat",
                "lon",
                "matched_address",
                "muni_name",
            )
        },
        "intensity": {
            "shindo_class": state["intensity"]["shindo_class"],
            "s_i": state["intensity"]["s_i"],
        },
        "payout": {
            key: state["payout"][key]
            for key in (
                "payout_ratio",
                "payout_yen",
                "payout_yen_formatted",
            )
        },
        "damage_summary": _damage_summary(state["features"]),
        "image": {
            "category": image["category"],
            "damage_type": image["damage_type"],
            "local_path": image["local_path"],
            "source_url": image["source_url"],
        },
    }


def _damage_summary(features: dict[str, Any]) -> str:
    ranked = sorted(
        (
            (key.removeprefix("nsi_").removeprefix("ratio_"), float(value))
            for key, value in features.items()
            if key.startswith(("nsi_", "ratio_"))
            and isinstance(value, (int, float))
            and value > 0
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    return "、".join(name for name, _ in ranked[:3]) or "該当情報なし"


def write_demo_data(payload: dict[str, Any], output_dir: Path) -> Path:
    """公開用データをJavaScriptファイルとして保存する。

    Args:
        payload: 公開用の固定回答データ。
        output_dir: 静的サイトの出力先。

    Returns:
        作成したJavaScriptファイルのパス。
    """
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    serialized = serialized.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    destination = data_dir / "demo-data.js"
    destination.write_text(
        f"window.DEMO_DATA = {serialized};\n",
        encoding="utf-8",
    )
    return destination


def copy_static_assets(
    source: dict[str, Any],
    responses_dir: Path,
    output_dir: Path,
) -> None:
    """画像、Leaflet、KaTeXのローカル資産を公開先へコピーする。

    Args:
        source: 固定回答の全データ。
        responses_dir: 固定回答JSONを格納するディレクトリ。
        output_dir: 静的サイトの出力先。
    """
    for scenario in source["scenarios"]:
        relative_path = Path(scenario["image"]["local_path"])
        source_image = responses_dir / relative_path
        destination_image = output_dir / relative_path
        destination_image.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_image, destination_image)

    vendor_dir = output_dir / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("leaflet.css", "leaflet.js"):
        shutil.copy2(WEBAPP_STATIC_DIR / "vendor" / filename, vendor_dir / filename)
    shutil.copytree(
        WEBAPP_STATIC_DIR / "vendor" / "images",
        vendor_dir / "images",
        dirs_exist_ok=True,
    )
    shutil.copytree(
        WEBAPP_STATIC_DIR / "vendor" / "katex",
        vendor_dir / "katex",
        dirs_exist_ok=True,
    )


def main() -> None:
    """静的デモ用データと依存資産を生成する。"""
    args = parse_args()
    responses_path = args.responses.resolve()
    output_dir = args.output_dir.resolve()
    source = load_responses(responses_path)
    public_payload = build_public_payload(source, responses_path.parent)
    data_path = write_demo_data(public_payload, output_dir)
    copy_static_assets(source, responses_path.parent, output_dir)
    print(
        f"静的デモ資産を生成しました: {len(public_payload['scenarios'])}シナリオ -> "
        f"{data_path}"
    )


if __name__ == "__main__":
    main()
