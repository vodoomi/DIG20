"""チャット経路(独自MCPツール)と地図経路(FastAPI)を橋渡しする状態ファイルの読み書き。

data/app_state/config.json: FastAPIが書き、MCPツールが読む(モード設定)。
data/app_state/latest.json:  MCPツールが書き、FastAPIが読む(直近の計算結果)。

デモは単一セッション・単一ユーザーを前提としており、並行書き込みに対するロックは行わない。
書き込みはtmpファイル+os.replaceで原子的に行う。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_STATE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "app_state"

DEFAULT_CONFIG = {"intensity_mode": "mock", "features_mode": "mock"}


def _state_dir() -> Path:
    env_dir = os.environ.get("PAYOUT_STATE_DIR")
    d = Path(env_dir) if env_dir else DEFAULT_STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write(path: Path, data: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def read_latest() -> dict:
    path = _state_dir() / "latest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def merge_latest(patch: dict) -> dict:
    """latest.jsonをpatchの内容で浅くマージして保存する。"""
    current = read_latest()
    current.update(patch)
    _atomic_write(_state_dir() / "latest.json", current)
    return current


def reset_latest() -> None:
    _atomic_write(_state_dir() / "latest.json", {})


def archive_and_start_query(query: dict) -> dict:
    """新しい住所質問を開始する。

    直前のquery一式(query/intensity/features/payout)が残っていれば、消さずにhistory配列へ
    退避してから新しいqueryで始める。地図に過去の建物位置を残したまま次の質問に進むための機構。
    """
    current = read_latest()
    history = current.get("history", [])
    if current.get("query"):
        entry = {k: current[k] for k in ("query", "intensity", "features", "payout") if k in current}
        history.append(entry)

    new_state = {"history": history, "query": query}
    _atomic_write(_state_dir() / "latest.json", new_state)
    return new_state


def read_config() -> dict:
    path = _state_dir() / "config.json"
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    return json.loads(path.read_text(encoding="utf-8"))


def write_config(config: dict) -> dict:
    merged = {**DEFAULT_CONFIG, **config}
    _atomic_write(_state_dir() / "config.json", merged)
    return merged
