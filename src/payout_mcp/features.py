"""FASTALERT topics レスポンスから市区町村単位の被害特徴量を計算する。

fastalert_topics の実レスポンス(topics[].category/head/location.city/items[])を
直接の入力とする。1トピック=1事象としてAPI側で既にグルーピング済みのため、
配布CSV由来の実装で必要だった「Topic IDで畳む」処理は不要(topics配列がその単位そのもの)。

このモジュールはMCP非依存(mcp パッケージに依存しない)。
scripts/build_fastalert_features.py(オフラインCSV構築)と
payout_mcp.server の compute_features ツール(ライブ計算)の両方から同じ関数を呼ぶ。
"""

from __future__ import annotations

from datetime import datetime, timedelta

# 地震と無関係、または被害シグナルとして数えないカテゴリ(仕様書 §特徴量について に準拠)
NOISE_CATEGORIES = {
    "地震情報",
    "緊急車両出動",
    "話題",
    "混雑情報",
    "道路渋滞",
    "鉄道トラブル",
    "交通事故",
    "事故",
    "危険走行",
    "不審者情報",
}

# 細分類カテゴリ → 集計用の被害タイプへのマージ表(仕様書の分類方針 + 実データで観測された細分類名に対応)
CATEGORY_MERGE_MAP = {
    "倒壊": "倒壊",
    "地震被害": "倒壊",
    "損壊": "倒壊",
    "破損被害": "倒壊",
    "断水": "断水",
    "水道設備トラブル": "断水",
    "停電": "停電",
    "電力設備トラブル": "停電",
    "電線切断": "停電",
    "火災": "火災",
    "車両火災": "火災",
    "道路損壊": "道路被害",
    "液状化": "液状化",
    "土砂災害": "土砂災害",
    "倒木": "土砂災害",
    "救助要請": "救助要請",
    "災害": "津波",
    "自然現象": "地盤変状",
}

DAMAGE_TYPES = [
    "倒壊",
    "液状化",
    "道路被害",
    "土砂災害",
    "救助要請",
    "停電",
    "断水",
    "火災",
    "津波",
    "地盤変状",
]

# severity算出用の重み: 人命・住家に直結する事象ほど重い(値が大きい)
SEVERITY_WEIGHTS = {
    "倒壊": 1.0,
    "救助要請": 1.0,
    "火災": 0.9,
    "津波": 0.8,
    "土砂災害": 0.7,
    "液状化": 0.5,
    "地盤変状": 0.4,
    "道路被害": 0.4,
    "断水": 0.3,
    "停電": 0.3,
}

LOW_SAMPLE_THRESHOLD = 5

_SNS_URL_MARKERS = ("twitter.com", "x.com", "instagram.com", "tiktok.com")


def _is_sns_item(item: dict) -> bool:
    """item.url からSNS由来かを推定する。

    実APIには CSV版の `kind` 列に相当するフィールドが無いため、
    投稿URLのドメインで代替判定する(URLが無い場合は消防発表等の非SNS源とみなす)。
    """
    url = (item.get("url") or "").lower()
    return any(marker in url for marker in _SNS_URL_MARKERS)


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def extract_features_from_topics(topics: list[dict], muni_name: str, quake_time: datetime) -> dict:
    """1市区町村分の topics 配列から特徴量dictを1件生成する(severity_pctは未設定)。"""
    signal_topics = []
    type_counts: dict[str, int] = {t: 0 for t in DAMAGE_TYPES}
    sns_item_count = 0
    total_item_count = 0

    for topic in topics:
        category = topic.get("category")
        if category in NOISE_CATEGORIES:
            continue
        merged_type = CATEGORY_MERGE_MAP.get(category)
        if merged_type is None:
            continue  # マージ表・ノイズ表のいずれにも無いカテゴリ(「その他」)はn_signalから除外
        signal_topics.append(topic)
        type_counts[merged_type] += 1
        for item in topic.get("items", []):
            total_item_count += 1
            if _is_sns_item(item):
                sns_item_count += 1

    n_signal = len(signal_topics)
    n_types = sum(1 for t in DAMAGE_TYPES if type_counts[t] > 0)

    ratios = {
        f"ratio_{t}": (type_counts[t] / n_signal if n_signal else 0.0) for t in DAMAGE_TYPES
    }
    severity = sum(ratios[f"ratio_{t}"] * SEVERITY_WEIGHTS[t] for t in DAMAGE_TYPES)

    if signal_topics:
        earliest = min(_parse_iso(t["created_at"]) for t in signal_topics)
        t_first_h = (earliest - quake_time).total_seconds() / 3600.0
    else:
        t_first_h = None

    src_sns_ratio = (sns_item_count / total_item_count) if total_item_count else 0.0

    return {
        "muni_name": muni_name,
        **ratios,
        "n_signal": n_signal,
        "n_types": n_types,
        "t_first_h": t_first_h,
        "src_sns_ratio": src_sns_ratio,
        "severity": severity,
        "severity_pct": None,
        "low_sample": n_signal < LOW_SAMPLE_THRESHOLD,
    }


def add_severity_percentile(rows: list[dict]) -> list[dict]:
    """複数自治体分のfeature行に対し、severityのデータセット内パーセンタイルを付与する。"""
    if not rows:
        return rows
    order = sorted(range(len(rows)), key=lambda i: rows[i]["severity"])
    n = len(rows)
    for rank, idx in enumerate(order):
        pct = 100.0 if n == 1 else round(rank / (n - 1) * 100, 1)
        rows[idx]["severity_pct"] = pct
    return rows
