"""FASTALERT MCPを実際に呼び出して3自治体分の特徴量CSVを生成するCLI。

配布CSV(data/dig20csv)は使わず、fastalert_topics の実呼び出し結果を直接集計する。
ここで使う集計ロジック(payout_mcp.features.extract_features_from_topics)は、
payout_mcp.server の compute_features ツールがライブモードで使うものと完全に同一。
つまり本スクリプトは「一度だけ実行してcachedモード用のスナップショットを作る」役割であり、
liveモードは実行時に同じ関数を呼ぶだけ、という関係になっている。

再実行時は data/features/raw_topics_<key>.json が存在すればMCP呼び出しをスキップする
(--refresh で強制再取得。共有クォータ保護のため通常は再取得しない)。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from payout_mcp import fastalert_client, features  # noqa: E402

CONFIG_DIR = REPO_ROOT / "config"
FEATURES_DIR = REPO_ROOT / "data" / "features"

FEATURE_COLUMNS = [
    "muni_code",
    "muni_name",
    *[f"ratio_{t}" for t in features.DAMAGE_TYPES],
    "n_signal",
    "n_types",
    "t_first_h",
    "src_sns_ratio",
    "severity",
    "severity_pct",
    "low_sample",
]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="FASTALERT MCPを呼び出して特徴量CSVを作成する")
    parser.add_argument(
        "--refresh", action="store_true", help="キャッシュ済み raw_topics_*.json があっても再取得する"
    )
    args = parser.parse_args()

    municipalities = load_json(CONFIG_DIR / "municipalities.json")
    weights = load_json(CONFIG_DIR / "weights.json")

    quake_time = datetime.fromisoformat(weights["quake_time"])
    window_hours = weights["feature_window_hours"]
    after = quake_time.isoformat()
    before = (quake_time + timedelta(hours=window_hours)).isoformat()

    FEATURES_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for key, muni in municipalities.items():
        raw_path = FEATURES_DIR / f"raw_topics_{key}.json"
        if raw_path.exists() and not args.refresh:
            print(f"[{key}] キャッシュ済み {raw_path} を使用")
            topics = load_json(raw_path)
        else:
            print(f"[{key}] fastalert_topics を呼び出し中 (locations={muni['full_name']})...")
            topics = fastalert_client.fetch_topics_window_sync(
                locations=muni["full_name"],
                after=after,
                before=before,
            )
            raw_path.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{key}] {len(topics)}件のトピックを取得 -> {raw_path}")

        feature_row = features.extract_features_from_topics(topics, muni["muni_name"], quake_time)
        feature_row["muni_code"] = muni["muni_code"]
        rows.append(feature_row)

    rows = features.add_severity_percentile(rows)

    out_path = FEATURES_DIR / "fastalert_features.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in FEATURE_COLUMNS})

    print(f"完了: {out_path}")
    for row in rows:
        print(
            f"  {row['muni_name']}: severity={row['severity']:.3f} "
            f"n_signal={row['n_signal']} low_sample={row['low_sample']}"
        )


if __name__ == "__main__":
    main()
