"""国土地理院APIを使った住所⇔緯度経度変換。MCP非依存の純ロジック。"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

ADDRESS_SEARCH_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"
REVERSE_GEOCODER_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"


def geocode_address(address: str, timeout: float = 10.0) -> dict:
    """住所文字列から緯度経度を取得する(先頭ヒットを採用)。

    戻り値: {"lat": float, "lon": float, "matched_address": str} | {"error": str}
    """
    url = f"{ADDRESS_SEARCH_URL}?{urllib.parse.urlencode({'q': address})}"
    with urllib.request.urlopen(url, timeout=timeout) as res:
        results = json.loads(res.read().decode("utf-8"))

    if not results:
        return {"error": f"住所が見つかりませんでした: {address}"}

    top = results[0]
    lon, lat = top["geometry"]["coordinates"]
    return {
        "lat": lat,
        "lon": lon,
        "matched_address": top["properties"]["title"],
    }


def reverse_geocode(lat: float, lon: float, timeout: float = 10.0) -> dict:
    """緯度経度から自治体コード(muniCd)を取得する。

    戻り値: {"muni_code": str, "town_name": str} | {"error": str}
    """
    params = {"lat": lat, "lon": lon}
    url = f"{REVERSE_GEOCODER_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as res:
        body = json.loads(res.read().decode("utf-8"))

    result = body.get("results")
    if not result:
        return {"error": f"緯度経度から自治体を特定できませんでした: lat={lat}, lon={lon}"}

    return {"muni_code": result["muniCd"], "town_name": result.get("lv01Nm", "")}
