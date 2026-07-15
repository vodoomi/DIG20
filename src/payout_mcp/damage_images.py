"""補償額根拠に対応する被害画像の選択ロジック。MCP非依存の純ロジック。

data/images/image_urls.json(fastalert_topic_detailで事前収集した添付メディアURL一覧)から、
補償額計算で寄与が最大だった被害タイプに対応するFASTALERTカテゴリの画像を1枚選ぶ。

被害タイプ(nsi_倒壊などのfeatureキー)は集計用にマージされた名前なので、
features.CATEGORY_MERGE_MAP を逆引きして元のFASTALERTカテゴリ集合に展開してから
画像を検索する(例: 地盤変状→自然現象、倒壊→倒壊/地震被害/損壊/破損被害)。
"""

from __future__ import annotations

import json
import random
import urllib.request
from collections.abc import Callable
from pathlib import Path

from payout_mcp.features import CATEGORY_MERGE_MAP
from payout_mcp.payout import FEATURE_KEY_PREFIXES

# マージ後の被害タイプ → 元のFASTALERTカテゴリ集合
DAMAGE_TYPE_TO_CATEGORIES: dict[str, set[str]] = {}
for _raw, _merged in CATEGORY_MERGE_MAP.items():
    DAMAGE_TYPE_TO_CATEGORIES.setdefault(_merged, set()).add(_raw)


def load_image_index(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)["topics"]


def _feature_label(key: str) -> str:
    for prefix in FEATURE_KEY_PREFIXES:
        if key.startswith(prefix):
            return key[len(prefix):]
    return key


def ranked_damage_types(latest: dict) -> list[str]:
    """補償額の根拠として影響が大きかった順に被害タイプ名を返す。

    第一候補は payout.contributions.top_features(寄与>0の重み付き特徴量、降順)。
    寄与が付かなかった被害タイプも、観測された特徴量の値が大きい順に後続候補として
    続ける(重みが疎で寄与が1タイプしか無い場合に画像が見つからないと困るため)。
    """
    ranked: list[str] = []

    payout_result = latest.get("payout") or {}
    for key, _value in payout_result.get("contributions", {}).get("top_features", []):
        label = _feature_label(key)
        if label not in ranked:
            ranked.append(label)

    features_result = latest.get("features") or {}
    observed = sorted(
        (
            (key, value)
            for key, value in features_result.items()
            if key.startswith(FEATURE_KEY_PREFIXES)
            and isinstance(value, (int, float))
            and value > 0
        ),
        key=lambda kv: kv[1],
        reverse=True,
    )
    for key, _value in observed:
        label = _feature_label(key)
        if label not in ranked:
            ranked.append(label)

    return ranked


def url_is_alive(url: str, timeout: float = 5.0) -> bool:
    """画像URLが今も生きているかをHEADで確認する(元ツイート削除で404になることがある)。"""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return 200 <= res.status < 300
    except Exception:
        return False


def _image_attachments(topic: dict) -> list[dict]:
    return [
        att
        for att in topic.get("attachments", [])
        if att.get("type") == "image" and att.get("image_url")
    ]


def pick_damage_image(
    latest: dict,
    image_index: list[dict],
    rng: random.Random | None = None,
    validate_url: Callable[[str], bool] | None = None,
    max_validation_tries: int = 5,
) -> dict:
    """直近の補償額計算に対応する被害画像を1枚ランダムに選ぶ。

    validate_url を渡すと、選んだURLが死んでいた場合に同カテゴリの別候補へ引き直す
    (max_validation_tries回まで。全滅なら次点の被害タイプへ進む)。
    返り値: image_url・被害タイプ・FASTALERTカテゴリ・出典等を含むdict。
    候補が見つからない場合は {"error": ...}。
    """
    rng = rng or random.Random()

    muni_name = (latest.get("query") or {}).get("muni_name")
    if not muni_name:
        return {"error": "先に住所の問い合わせ(geocode_address)を行ってください。"}
    if "payout" not in latest:
        return {"error": "まだ補償額が計算されていません。先に補償額を計算してください。"}

    muni_topics = [
        t for t in image_index if (t.get("location") or {}).get("city") == muni_name
    ]
    if not muni_topics:
        return {"error": f"{muni_name}の被害画像はデータに含まれていません(対象: 輪島市・長岡市・内灘町)。"}

    for damage_type in ranked_damage_types(latest):
        categories = DAMAGE_TYPE_TO_CATEGORIES.get(damage_type, {damage_type})
        candidates = [
            (topic, att)
            for topic in muni_topics
            if topic.get("category") in categories
            for att in _image_attachments(topic)
        ]
        rng.shuffle(candidates)
        if validate_url is not None:
            candidates = candidates[:max_validation_tries]
            candidates = next(
                ([c] for c in candidates if validate_url(c[1]["image_url"])), []
            )
        if candidates:
            topic, att = candidates[0]
            return {
                "muni_name": muni_name,
                "damage_type": damage_type,
                "category": topic["category"],
                "image_url": att["image_url"],
                "topic_id": topic["topic_id"],
                "topic_head": topic.get("head"),
                "source_url": att.get("source_url"),
                "published_at": att.get("published_at"),
                "fastalert_url": topic.get("fastalert_url"),
            }

    return {
        "error": (
            f"{muni_name}では、補償額の根拠となった被害タイプに対応する画像が見つかりませんでした。"
        )
    }
