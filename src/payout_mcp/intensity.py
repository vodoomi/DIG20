"""震度階級⇔計測震度スカラー変換、および最寄り観測点抽出。MCP非依存の純ロジック。"""

from __future__ import annotations

import math

# 気象庁震度階級 → 計測震度区間の中央値(震度7のみ上限が定義されないため幅0.5と仮定した代表値)
SHINDO_TO_S = {
    "1": 1.0,
    "2": 2.0,
    "3": 3.0,
    "4": 4.0,
    "5弱": 4.75,
    "5強": 5.25,
    "6弱": 5.75,
    "6強": 6.25,
    "7": 6.75,
}

# FASTALERT等が返す表記ゆれ(INTENSITY5LOWER等)を正規化するための対応表
_ALIASES = {
    "1": "1",
    "INTENSITY1": "1",
    "2": "2",
    "INTENSITY2": "2",
    "3": "3",
    "INTENSITY3": "3",
    "4": "4",
    "INTENSITY4": "4",
    "5-": "5弱",
    "5弱": "5弱",
    "INTENSITY5LOWER": "5弱",
    "5+": "5強",
    "5強": "5強",
    "INTENSITY5UPPER": "5強",
    "6-": "6弱",
    "6弱": "6弱",
    "INTENSITY6LOWER": "6弱",
    "6+": "6強",
    "6強": "6強",
    "INTENSITY6UPPER": "6強",
    "7": "7",
    "INTENSITY7": "7",
}


def normalize_shindo_class(raw: str) -> str:
    key = raw.strip()
    if key in _ALIASES:
        return _ALIASES[key]
    upper = key.upper()
    if upper in _ALIASES:
        return _ALIASES[upper]
    raise ValueError(f"未知の震度表記: {raw}")


def shindo_to_s(shindo_class: str) -> float:
    return SHINDO_TO_S[normalize_shindo_class(shindo_class)]


# 気象庁の震度階級関連解説表に基づく平易な言い換え(数学的な素養がない人向けの説明用)
SHINDO_DESCRIPTIONS = {
    "1": "屋内で静かにしている人の一部が気づく程度のごく弱い揺れ",
    "2": "屋内で静かにしている人の多くが気づく弱い揺れ",
    "3": "屋内にいるほとんどの人が感じる揺れ",
    "4": "多くの人が驚き、吊り下げ物が大きく揺れる程度の揺れ",
    "5弱": "多くの人が身の安全を図ろうとする程度の揺れ",
    "5強": "物につかまらないと歩くのが難しい程度の強い揺れ",
    "6弱": "立っていることが困難になる激しい揺れ",
    "6強": "はわないと動くことができない、耐震性の低い建物が傾くこともある非常に激しい揺れ",
    "7": "耐震性の低い建物は倒壊のおそれがある極めて激しい揺れ",
}


def describe_shindo(shindo_class: str) -> str:
    """震度階級を数学的な数値を出さずに言葉で説明する。"""
    normalized = normalize_shindo_class(shindo_class)
    return SHINDO_DESCRIPTIONS.get(normalized, f"震度{normalized}相当の揺れ")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


def nearest_station_intensity(lat: float, lon: float, station_intensities: list[dict]) -> dict:
    """station_intensities(fastalert_earthquake_detailのstationIntensities[])から最寄りを選ぶ。

    各要素は {"intensity": str, "name": str, "location": {"lat": float, "lng": float}} を想定。
    """
    if not station_intensities:
        raise ValueError("station_intensitiesが空です")

    best = None
    best_dist = math.inf
    for station in station_intensities:
        loc = station.get("location", {})
        s_lat, s_lon = loc.get("lat"), loc.get("lng")
        if s_lat is None or s_lon is None:
            continue
        dist = haversine_km(lat, lon, s_lat, s_lon)
        if dist < best_dist:
            best_dist = dist
            best = station

    if best is None:
        raise ValueError("有効な座標を持つ観測点がありませんでした")

    shindo_class = normalize_shindo_class(str(best["intensity"]))
    return {
        "shindo_class": shindo_class,
        "s_i": SHINDO_TO_S[shindo_class],
        "station_name": best.get("name"),
        "distance_km": round(best_dist, 2),
    }
