"""FASTALERT MCP(リモート)を mcp-remote 経由の stdio クライアントとして呼び出す共有クライアント。

scripts/build_fastalert_features.py(オフラインでの特徴量CSV構築)と
payout_mcp.features のライブモードの両方が、この同じ経路で fastalert_topics を呼び、
同じ特徴量抽出ロジック(features.extract_features_from_topics)に流し込む。
これにより「事前にCSVを作る」と「都度MCPで作る」が完全に同一コードパスになる。

認証は ~/.mcp-auth の既存セッションを mcp-remote がそのまま利用するため、
このモジュール側では OAuth を意識しない。
"""

from __future__ import annotations

import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

FASTALERT_REMOTE_URL = "https://app.fastalert.jp/mcp/sse"

_SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["-y", "mcp-remote", FASTALERT_REMOTE_URL],
)


async def _call_fastalert_topics(session: ClientSession, **kwargs) -> dict:
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    result = await session.call_tool("fastalert_topics", kwargs)
    if result.isError:
        raise RuntimeError(f"fastalert_topics failed: {result.content}")
    text = result.content[0].text
    return json.loads(text)


async def fetch_topics_window(
    locations: str,
    after: str,
    before: str,
    categories: str | None = None,
    page_limit: int = 100,
    max_pages: int = 20,
) -> list[dict]:
    """[after, before] の期間のトピックを全ページ収集して返す。

    レスポンスの tail(ページ内最古のcreated_at)を次ページの before に渡し、
    古い方向へページングする(fastalert_topics の仕様: order_by=created_at降順がデフォルト)。
    共有クォータ保護のため max_pages で打ち切る。
    """
    topics: list[dict] = []
    cursor_before = before
    async with stdio_client(_SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for _ in range(max_pages):
                page = await _call_fastalert_topics(
                    session,
                    locations=locations,
                    after=after,
                    before=cursor_before,
                    categories=categories,
                    limit=page_limit,
                )
                page_topics = page.get("topics", [])
                if not page_topics:
                    break
                topics.extend(page_topics)
                if len(page_topics) < page_limit:
                    break
                tail = page.get("tail")
                if not tail or tail == cursor_before:
                    break
                cursor_before = tail
    return topics


def fetch_topics_window_sync(
    locations: str,
    after: str,
    before: str,
    categories: str | None = None,
    page_limit: int = 100,
    max_pages: int = 20,
) -> list[dict]:
    """fetch_topics_window の同期ラッパー(CLIスクリプトから使用)。"""
    return asyncio.run(
        fetch_topics_window(
            locations=locations,
            after=after,
            before=before,
            categories=categories,
            page_limit=page_limit,
            max_pages=max_pages,
        )
    )
