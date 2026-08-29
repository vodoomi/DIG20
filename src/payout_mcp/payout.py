"""補償額計算式。MCP非依存の純ロジック。

支払率 P_i(w) = 1 / (1 + exp(-(w0 + w1*S_i + Σ_k w_k*x_k)))
支払額 = P_i(w) x 保険金額(法人向け1,000万円)

FASTALERT特徴量は単一のスカラーに集約せず、被害タイプ別の値(ratio_*/nsi_*)
それぞれに重みを持たせ、その合成寄与をそのまま補償額計算に使う(config/weights.jsonのfeature_weights)。
重みは事前最適化の結果ではなく暫定値。
"""

from __future__ import annotations

import math


def sigmoid(z: float) -> float:
    """ロジットを0から1の支払率へ変換する。"""
    return 1.0 / (1.0 + math.exp(-z))


def format_yen(amount: float) -> str:
    """円単位の金額を万円単位の表示へ変換する。"""
    man = amount / 10000
    return f"約{man:,.0f}万円"


FEATURE_KEY_PREFIXES = ("ratio_", "nsi_")


def calculate_payout(s_i: float, features: dict, weights: dict) -> dict:
    """震度と被害特徴量から支払率および補償額を計算する。

    Args:
        s_i: 計測震度スカラー。
        features: ``compute_features`` の結果。``ratio_*`` / ``nsi_*`` を含む。
        weights: 切片、各重み、保険金額を含む設定。

    Returns:
        支払率、補償額、計算内訳を含む辞書。
    """
    w0, w1 = weights["w0"], weights["w1"]
    feature_weights = weights["feature_weights"]
    insured_amount = weights["insured_amount_yen"]

    # 内訳には重み辞書のキーだけでなく観測された全特徴量を出す。
    # 重み未設定の特徴量は寄与0(=算定に未反映)であることを明示するため。
    observed_keys = [
        key for key in features
        if key.startswith(FEATURE_KEY_PREFIXES) and key not in feature_weights
    ]
    feature_contributions = {
        key: feature_weights.get(key, 0.0) * (features.get(key) or 0.0)
        for key in [*feature_weights, *observed_keys]
    }
    feature_total = sum(feature_contributions.values())

    z = w0 + w1 * s_i + feature_total
    ratio = sigmoid(z)
    amount = ratio * insured_amount

    top_features = sorted(
        ((key, value) for key, value in feature_contributions.items() if value > 0),
        key=lambda kv: kv[1],
        reverse=True,
    )

    return {
        "payout_ratio": ratio,
        "payout_yen": round(amount),
        "payout_yen_formatted": format_yen(amount),
        "weights": {"w0": w0, "w1": w1, "feature_weights": feature_weights},
        "insured_amount_yen": insured_amount,
        "formula": (
            "支払額 = 1 / (1 + exp(-(w0 + w1*S_i + Σ_k w_k*x_k))) "
            "× 保険金額"
        ),
        "contributions": {
            "w0": w0,
            "w1*S_i": w1 * s_i,
            "feature_total": feature_total,
            "feature_breakdown": feature_contributions,
            "top_features": top_features,
            "z": z,
        },
    }
