# -*- coding: utf-8 -*-
"""
server.py — 地震保険即時支払いデモ用 独自MCPサーバ(Model Context Protocol準拠)
===============================================================================
公開ツール:
  - geocode_address              : 住所→緯度経度・自治体判定(新規質問の起点。stateを初期化)
  - get_intensity                 : 震度取得(mock=固定値 / live=最寄り観測点)
  - compute_features               : FASTALERT特徴量取得(mock=事前CSV / live=fastalert_topicsを都度呼び出し)
  - calculate_payout              : 補償額計算(P = sigmoid(w0+w1*S_i+Σ_k w_k*ratio_k) x 再調達価額)
  - explain_payout                 : 直近の計算の根拠を平易な日本語の文章で返す
  - get_damage_image               : 根拠で寄与が大きかった被害カテゴリの実画像URLを1枚返す
  - estimate_payout_for_address    : 上記を1コールで実行する複合ツール(フォールバック用)

設計:
  - 全ツールは data/app_state/latest.json を介して結果を受け渡す。引数省略時はここから補完する。
  - モード(mock/live)は data/app_state/config.json(FastAPI側が書く)を読んで切り替える。
  - compute_features の live モードは payout_mcp.fastalert_client 経由で fastalert_topics を
    直接呼び出す(LLM側のFASTALERT統合には依存しない)。同じ集計ロジックを
    scripts/build_fastalert_features.py のCSV事前構築とも共有している。

実行: python3 -m payout_mcp.server   (stdio トランスポート。PYTHONPATH=src が必要)
依存: mcp, numpy 不要。requirements は pyproject.toml 側で管理。
"""

import asyncio
import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from payout_mcp import damage_images, fastalert_client, features, geocode, intensity, payout, state

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    _IMPORT_ERR = None
except Exception as e:  # pragma: no cover
    Server = None
    _IMPORT_ERR = e


def _repo_root() -> Path:
    env = os.environ.get("PAYOUT_REPO_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


CONFIG_DIR = _repo_root() / "config"
FEATURES_CSV = _repo_root() / "data" / "features" / "fastalert_features.csv"
IMAGE_URLS_JSON = _repo_root() / "data" / "images" / "image_urls.json"

_INT_FEATURE_FIELDS = {"n_signal", "n_types"}


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _municipalities() -> dict:
    return _load_json(CONFIG_DIR / "municipalities.json")


def _weights() -> dict:
    return _load_json(CONFIG_DIR / "weights.json")


def _find_muni_by_name(muni_name: str) -> dict | None:
    for muni in _municipalities().values():
        if muni["muni_name"] == muni_name:
            return muni
    return None


def _find_muni_by_code(muni_code: str) -> dict | None:
    for muni in _municipalities().values():
        if muni["muni_code"] == muni_code:
            return muni
    return None


def _row_to_feature_dict(row: dict) -> dict:
    result = {}
    for key, value in row.items():
        if key in ("muni_code", "muni_name"):
            result[key] = value
        elif key == "low_sample":
            result[key] = value == "True"
        elif key in _INT_FEATURE_FIELDS:
            result[key] = int(value)
        elif value in ("", "None"):
            result[key] = None
        else:
            result[key] = float(value)
    return result


# ----------------------------- ツール入力スキーマ -----------------------------
GEOCODE_ADDRESS_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {"type": "string", "description": "問い合わせ対象の住所(例: 石川県輪島市河井町)"},
    },
    "required": ["address"],
}

GET_INTENSITY_SCHEMA = {
    "type": "object",
    "properties": {
        "muni_name": {"type": "string", "description": "自治体名(省略時は直近のgeocode_address結果から補完)"},
        "station_intensities": {
            "type": "array",
            "description": (
                "liveモード時のみ必須。fastalert_earthquake_detail のレスポンスにある "
                "stationIntensities配列をそのまま渡す。"
            ),
            "items": {"type": "object"},
        },
    },
}

COMPUTE_FEATURES_SCHEMA = {
    "type": "object",
    "properties": {
        "muni_name": {"type": "string", "description": "自治体名(省略時は直近のgeocode_address結果から補完)"},
        "since_hours": {
            "type": "number",
            "default": 72,
            "description": "liveモード時: 現在時刻から遡る時間窓(時間、既定72)",
        },
    },
}

CALCULATE_PAYOUT_SCHEMA = {
    "type": "object",
    "properties": {
        "s_i": {"type": "number", "description": "計測震度スカラー(省略時は直近のget_intensity結果から補完)"},
    },
}

EXPLAIN_PAYOUT_SCHEMA = {"type": "object", "properties": {}}

GET_DAMAGE_IMAGE_SCHEMA = {"type": "object", "properties": {}}

ESTIMATE_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {"type": "string", "description": "問い合わせ対象の住所"},
    },
    "required": ["address"],
}


# ----------------------------- ツール実体 -----------------------------
def run_geocode_address(args: dict) -> dict:
    address = args["address"]
    geo = geocode.geocode_address(address)
    if "error" in geo:
        return geo

    rev = geocode.reverse_geocode(geo["lat"], geo["lon"])
    muni = _find_muni_by_code(rev["muni_code"]) if "muni_code" in rev else None

    result = {
        "lat": geo["lat"],
        "lon": geo["lon"],
        "matched_address": geo["matched_address"],
        "muni_name": muni["muni_name"] if muni else None,
        "muni_code": rev.get("muni_code"),
        "in_demo_area": muni is not None,
    }
    if muni is None:
        result["note"] = "本デモの対象自治体(輪島市・長岡市・内灘町)以外の住所です。参考値として処理を続行します。"

    # 直前の質問(query/intensity/features/payout)はhistoryへ退避し、地図上には残す。
    state.archive_and_start_query({"address": address, **result})
    return result


def run_get_intensity(args: dict) -> dict:
    latest = state.read_latest()
    muni_name = args.get("muni_name") or latest.get("query", {}).get("muni_name")
    mode = state.read_config().get("intensity_mode", "mock")

    if mode == "mock":
        muni = _find_muni_by_name(muni_name) if muni_name else None
        if muni is None:
            return {"error": f"mockモード用の自治体が特定できません: muni_name={muni_name}"}
        mock = muni["mock_intensity"]
        result = {
            "shindo_class": mock["shindo_class"],
            "s_i": mock["s_i"],
            "source": "mock",
            "station_name": None,
            "distance_km": None,
        }
    else:
        station_intensities = args.get("station_intensities")
        if not station_intensities:
            return {
                "error": (
                    "liveモードです。先に fastalert_earthquakes と fastalert_earthquake_detail を呼び、"
                    "得られた stationIntensities をこのツールの station_intensities 引数に渡してください。"
                )
            }
        lat = latest.get("query", {}).get("lat")
        lon = latest.get("query", {}).get("lon")
        if lat is None or lon is None:
            return {"error": "先に geocode_address を呼んでください(緯度経度が未取得です)。"}
        nearest = intensity.nearest_station_intensity(lat, lon, station_intensities)
        result = {**nearest, "source": "nearest_station"}

    state.merge_latest({"intensity": result})
    return result


async def run_compute_features(args: dict) -> dict:
    latest = state.read_latest()
    muni_name = args.get("muni_name") or latest.get("query", {}).get("muni_name")
    if not muni_name:
        return {"error": "muni_nameが指定されておらず、直近のgeocode_address結果もありません。"}

    mode = state.read_config().get("features_mode", "mock")

    if mode == "mock":
        if not FEATURES_CSV.exists():
            return {
                "error": (
                    f"特徴量CSVがありません: {FEATURES_CSV}。"
                    "scripts/build_fastalert_features.py を実行してください。"
                )
            }
        with FEATURES_CSV.open(newline="", encoding="utf-8") as f:
            row = next((r for r in csv.DictReader(f) if r["muni_name"] == muni_name), None)
        if row is None:
            return {"error": f"特徴量CSVに{muni_name}の行がありません。"}
        result = _row_to_feature_dict(row)
        result["source"] = "cached_csv"
    else:
        muni = _find_muni_by_name(muni_name)
        if muni is None:
            return {"error": f"liveモードは本デモ対象自治体(輪島市・長岡市・内灘町)のみ対応しています: {muni_name}"}
        since_hours = args.get("since_hours", 72)
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=since_hours)
        # サーバーは既にイベントループ内で動作しているため、同期ラッパー(asyncio.run)ではなく
        # 非同期版を直接awaitする(build_fastalert_features.pyはスクリプトなのでsync版を使う)。
        topics = await fastalert_client.fetch_topics_window(
            locations=muni["full_name"],
            after=window_start.isoformat(),
            before=now.isoformat(),
        )
        result = features.extract_features_from_topics(topics, muni_name, window_start)
        result["muni_code"] = muni["muni_code"]
        result["severity_pct"] = None  # 単独自治体のみの取得のためデータセット内比較は不可
        result["source"] = "live_topics"

    state.merge_latest({"features": result})
    return result


def run_calculate_payout(args: dict) -> dict:
    latest = state.read_latest()
    weights = _weights()

    s_i = args.get("s_i", latest.get("intensity", {}).get("s_i"))
    if s_i is None:
        return {"error": "s_iが指定されておらず、直近のget_intensity結果もありません。"}

    features_result = latest.get("features")
    if not features_result:
        return {"error": "compute_featuresの結果がありません。先にcompute_featuresを呼んでください。"}

    result = payout.calculate_payout(s_i, features_result, weights)
    state.merge_latest({"payout": result})
    return result


def _feature_label(key: str) -> str:
    for prefix in payout.FEATURE_KEY_PREFIXES:
        if key.startswith(prefix):
            return key[len(prefix):]
    return key


def _describe_observed_features(features_result: dict, limit: int = 3) -> str:
    """観測された被害特徴量(値>0)を大きい順に列挙する。重みの有無とは無関係(実際の被害状況の説明)。"""
    observed = sorted(
        (
            (key, value)
            for key, value in features_result.items()
            if key.startswith(payout.FEATURE_KEY_PREFIXES)
            and isinstance(value, (int, float))
            and value > 0
        ),
        key=lambda kv: kv[1],
        reverse=True,
    )
    if not observed:
        return "際立って大きな被害情報は確認されませんでした"
    names = [_feature_label(key) for key, _ in observed[:limit]]
    return "・".join(names) + "に関する被害情報が目立ちました"


def _describe_weighted_features(top_features: list, limit: int = 3) -> str:
    """補償額の算定に実際に効いた(寄与>0の)特徴量の説明。"""
    if not top_features:
        return "補償額の算定では被害投稿による上乗せはなく、揺れの強さが主な根拠です"
    names = [_feature_label(key) for key, _ in top_features[:limit]]
    return "補償額の算定では、モデルが特に重視する" + "・".join(names) + "の情報を揺れの強さに加えて反映しました"


def _build_explanation(intensity_result: dict, features_result: dict, payout_result: dict) -> str:
    """数式や重みの生数値を出さず、平易な日本語の文章で補償額の根拠を説明する。"""
    shindo_class = intensity_result.get("shindo_class", "不明")
    shindo_desc = intensity.describe_shindo(shindo_class) if intensity_result else "揺れの情報が不明"
    feature_desc = _describe_observed_features(features_result)
    weighted_desc = _describe_weighted_features(
        payout_result.get("contributions", {}).get("top_features", [])
    )
    ratio_pct = round(payout_result["payout_ratio"] * 100)

    low_sample_note = ""
    if features_result and features_result.get("low_sample"):
        low_sample_note = " なお、この地域は被害投稿の件数自体が少ないため、参考値としてご利用ください。"

    return (
        f"この地域は震度{shindo_class}相当({shindo_desc})の揺れに見舞われました。"
        f"SNS等から集めた被害投稿を見ると、{feature_desc}。{weighted_desc}。"
        f"揺れの強さとこうした被害状況を総合的に評価した結果、建物の再調達価額(2,000万円)に対して"
        f"約{ratio_pct}%を支払う水準と判断し、{payout_result['payout_yen_formatted']}という"
        f"補償額を算出しました。{low_sample_note}"
    )


def run_explain_payout(args: dict) -> dict:
    latest = state.read_latest()
    if "payout" not in latest:
        return {"error": "まだ補償額が計算されていません。先に一連のツールを実行してください。"}

    intensity_result = latest.get("intensity", {})
    features_result = latest.get("features", {})
    payout_result = latest["payout"]

    return {
        "explanation_ja": _build_explanation(intensity_result, features_result, payout_result),
        "s_i": intensity_result.get("s_i"),
        "shindo_class": intensity_result.get("shindo_class"),
        "features": features_result,
        "weights": payout_result["weights"],
        "contributions": payout_result["contributions"],
        "formula": payout_result["formula"],
        "payout_ratio": payout_result["payout_ratio"],
        "payout_yen_formatted": payout_result["payout_yen_formatted"],
        "low_sample": features_result.get("low_sample"),
        "data_sources": {
            "intensity_source": intensity_result.get("source"),
            "features_source": features_result.get("source"),
        },
    }


def run_get_damage_image(args: dict) -> dict:
    if not IMAGE_URLS_JSON.exists():
        return {"error": f"被害画像インデックスがありません: {IMAGE_URLS_JSON}"}

    latest = state.read_latest()
    result = damage_images.pick_damage_image(
        latest,
        damage_images.load_image_index(IMAGE_URLS_JSON),
        validate_url=damage_images.url_is_alive,  # 元ツイート削除で404の画像はスキップ
    )
    if "error" in result:
        return result

    # チャット欄にそのまま貼れば<img>として表示されるMarkdownを添えて返す。
    # LLMにURLを書き写させると打ち間違いが起きるため、この文字列を無加工で使わせる。
    result["markdown"] = (
        f"![{result['muni_name']}の{result['category']}の被害画像]({result['image_url']})\n\n"
        f"*{result['muni_name']}・カテゴリ「{result['category']}」の被害投稿画像"
        f"([出典]({result['source_url']}))*"
    )
    state.merge_latest({"damage_image": result})
    return result


async def run_estimate_payout_for_address(args: dict) -> dict:
    geo = run_geocode_address({"address": args["address"]})
    if "error" in geo:
        return geo
    if not geo["in_demo_area"]:
        return {"error": geo.get("note", "対象自治体外です"), "geocode": geo}

    intensity_result = run_get_intensity({"muni_name": geo["muni_name"]})
    if "error" in intensity_result:
        return intensity_result

    features_result = await run_compute_features({"muni_name": geo["muni_name"]})
    if "error" in features_result:
        return features_result

    payout_result = run_calculate_payout({"s_i": intensity_result["s_i"]})

    return {
        "geocode": geo,
        "intensity": intensity_result,
        "features": features_result,
        "payout": payout_result,
    }


_TOOL_HANDLERS = {
    "geocode_address": run_geocode_address,
    "get_intensity": run_get_intensity,
    "compute_features": run_compute_features,
    "calculate_payout": run_calculate_payout,
    "explain_payout": run_explain_payout,
    "get_damage_image": run_get_damage_image,
    "estimate_payout_for_address": run_estimate_payout_for_address,
}


# ----------------------------- MCPサーバ -----------------------------
def build_server():
    app = Server("payout")

    @app.list_tools()
    async def list_tools():
        return [
            Tool(
                name="geocode_address",
                description=(
                    "住所を緯度経度に変換し、本デモ対象の自治体(輪島市・長岡市・内灘町)かどうかを判定する。"
                    "補償額を尋ねる質問が来たら最初に呼ぶツール。以降のツール呼び出しの状態を初期化する。"
                ),
                inputSchema=GEOCODE_ADDRESS_SCHEMA,
            ),
            Tool(
                name="get_intensity",
                description=(
                    "対象自治体の震度(計測震度スカラー)を取得する。現在のモードがmockなら固定値表を、"
                    "liveならfastalert_earthquake_detailのstationIntensitiesから最寄り観測点を選ぶ"
                    "(liveの場合は先にFASTALERT側のfastalert_earthquakes/fastalert_earthquake_detailを呼び、"
                    "station_intensities引数に渡すこと)。"
                ),
                inputSchema=GET_INTENSITY_SCHEMA,
            ),
            Tool(
                name="compute_features",
                description=(
                    "対象自治体のFASTALERT被害特徴量(severity等)を取得する。現在のモードがmockなら"
                    "事前構築済みCSVを、liveならこのMCP自身がfastalert_topicsを直接呼び出してその場で"
                    "集計する(この場合LLM側でfastalert_topicsを呼ぶ必要は無い)。"
                ),
                inputSchema=COMPUTE_FEATURES_SCHEMA,
            ),
            Tool(
                name="calculate_payout",
                description=(
                    "震度と被害タイプ別の特徴量(compute_featuresの結果)から補償額を計算する。"
                    "特徴量は単一指標に集約せず、倒壊・断水・火災などタイプ別の構成比をそのまま使う。"
                    "重みは事前最適化ではなく暫定値(config/weights.json)。"
                ),
                inputSchema=CALCULATE_PAYOUT_SCHEMA,
            ),
            Tool(
                name="explain_payout",
                description=(
                    "直近に計算した補償額の根拠を返す。震度・被害タイプ別の特徴量(features)・重み"
                    "(weights)・各項の寄与(contributions: w1*S_i, feature_breakdown, feature_total, z等)・"
                    "計算式(formula)をすべて含む。『この補償額になった根拠を教えてください』という"
                    "追加質問には、これらの数値と計算ロジックを具体的に示しながら説明すること。"
                    "引数は不要で、状態ファイルの内容だけから完結して答えられる。"
                ),
                inputSchema=EXPLAIN_PAYOUT_SCHEMA,
            ),
            Tool(
                name="get_damage_image",
                description=(
                    "直近の補償額算定で影響が大きかった被害カテゴリの実際の被害画像を1枚ランダムに返す"
                    "(FASTALERTで収集済みのSNS投稿画像)。『被害の様子を画像で見せて』のような依頼が"
                    "来たら、余計なことを考えずにこのツールを1回呼ぶこと。引数は不要。"
                    "回答には、返り値の markdown フィールドの文字列を一字も変えずにそのまま貼り付ける"
                    "(URLを書き写したり要約したりしない)。"
                ),
                inputSchema=GET_DAMAGE_IMAGE_SCHEMA,
            ),
            Tool(
                name="estimate_payout_for_address",
                description=(
                    "geocode_address→get_intensity→compute_features→calculate_payoutを1回で実行する複合ツール。"
                    "個別ツールでの段階実行がうまく編成できない場合、またはmockモードでの近道として使う。"
                ),
                inputSchema=ESTIMATE_SCHEMA,
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict):
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            result = {"error": f"unknown tool: {name}"}
        else:
            try:
                result = handler(arguments or {})
                if asyncio.iscoroutine(result):
                    result = await result
            except (ValueError, FileNotFoundError, KeyError) as e:
                result = {"error": str(e)}
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    return app


async def _main():
    if Server is None:
        raise SystemExit(f"mcp パッケージが必要です: uv add mcp  (詳細: {_IMPORT_ERR})")
    app = build_server()
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
