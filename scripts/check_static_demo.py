"""生成済みの静的デモサイトをオフライン要件に沿って検証する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "site"
DATA_PREFIX = "window.DEMO_DATA = "
REQUIRED_FILES = (
    "index.html",
    "app.css",
    "app.js",
    "data/demo-data.js",
    "vendor/leaflet.css",
    "vendor/leaflet.js",
    "vendor/katex/katex.min.css",
    "vendor/katex/katex.min.js",
    "vendor/katex/auto-render.min.js",
)
REQUIRED_TURN_KINDS = {"payout", "reason", "math", "photo"}
FORBIDDEN_RUNTIME_REFERENCES = (
    'fetch("/api/state")',
    'hx-post="/chat"',
    "pbs.twimg.com",
)


def load_demo_data(path: Path) -> dict[str, Any]:
    """生成済みJavaScriptから固定回答データを読み込む。

    Args:
        path: `demo-data.js`のパス。

    Returns:
        JavaScript変数へ代入される固定回答データ。

    Raises:
        ValueError: 想定する代入形式でない場合。
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith(DATA_PREFIX) or not text.rstrip().endswith(";"):
        raise ValueError("demo-data.jsの形式が不正です")
    return json.loads(text[len(DATA_PREFIX) :].rstrip().removesuffix(";"))


def validate_site(site_dir: Path) -> list[str]:
    """静的サイトのファイルと固定回答の整合性を検証する。

    Args:
        site_dir: 静的サイトのルートディレクトリ。

    Returns:
        検証したシナリオキーの一覧。

    Raises:
        AssertionError: 必須ファイルや固定回答に不整合がある場合。
    """
    for relative_path in REQUIRED_FILES:
        path = site_dir / relative_path
        assert path.is_file(), f"必須ファイルがありません: {path}"

    payload = load_demo_data(site_dir / "data" / "demo-data.js")
    scenarios = payload.get("scenarios", [])
    assert scenarios, "公開用シナリオがありません"

    keys: list[str] = []
    for scenario in scenarios:
        key = scenario["key"]
        keys.append(key)
        assert set(scenario["turns"]) == REQUIRED_TURN_KINDS
        assert scenario["query"]["lat"] is not None
        assert scenario["query"]["lon"] is not None
        assert scenario["payout"]["payout_yen"] > 0
        image_path = site_dir / scenario["image"]["local_path"]
        assert image_path.is_file(), f"画像がありません: {image_path}"
        assert "<img" in scenario["turns"]["photo"]["answer_html"]

    searchable_files = (
        site_dir / "index.html",
        site_dir / "app.js",
        site_dir / "data" / "demo-data.js",
    )
    searchable_text = "\n".join(
        path.read_text(encoding="utf-8") for path in searchable_files
    )
    for forbidden in FORBIDDEN_RUNTIME_REFERENCES:
        assert forbidden not in searchable_text, (
            f"外部実行依存が残っています: {forbidden}"
        )
    return keys


def main() -> None:
    """静的デモサイトを検証し、結果を標準出力へ表示する。"""
    keys = validate_site(SITE_DIR)
    print(f"静的デモ検証OK: {len(keys)}シナリオ ({', '.join(keys)})")


if __name__ == "__main__":
    main()
