"""発表用デモのクイック返信候補を組み立てる。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoAddress:
    """補償額を試算するデモ住所。"""

    key: str
    label: str
    address: str

    @property
    def message(self) -> str:
        """LLMへ送る補償額質問を返す。"""
        return f"能登半島地震における{self.address}の補償額を教えてください"


@dataclass(frozen=True)
class QuickReply:
    """画面に表示するクイック返信。"""

    label: str
    message: str


DEMO_ADDRESSES = (
    DemoAddress(
        key="wajima",
        label="輪島市 河井町1部115番地",
        address="石川県輪島市河井町1部115番地",
    ),
    DemoAddress(
        key="uchinada",
        label="内灘町 大学1丁目2番地1",
        address="石川県河北郡内灘町字大学1丁目2番地1",
    ),
    DemoAddress(
        key="nagaoka",
        label="長岡市 中之島1993番地17",
        address="新潟県長岡市中之島1993番地17",
    ),
)

REASON_MESSAGE = "この補償額になった根拠を教えてください"
MATH_MESSAGE = "数式を使って理由を説明してください"
PHOTO_MESSAGE = "写真で被害の状況を教えてください"

REASON_REPLY = QuickReply(label=REASON_MESSAGE, message=REASON_MESSAGE)
MATH_REPLY = QuickReply(label=MATH_MESSAGE, message=MATH_MESSAGE)
PHOTO_REPLY = QuickReply(label=PHOTO_MESSAGE, message=PHOTO_MESSAGE)


def build_quick_replies(history: list[dict], *, has_payout: bool) -> list[QuickReply]:
    """会話の進行状況に応じた次の選択肢を返す。

    Args:
        history: Webアプリが保持する会話履歴。
        has_payout: 現在の住所について補償額を計算済みか。

    Returns:
        画面へ表示するクイック返信のリスト。
    """
    user_messages = [
        str(turn.get("content", ""))
        for turn in history
        if turn.get("role") == "user"
    ]
    selected = {
        option.key
        for option in DEMO_ADDRESSES
        if any(option.address in message for message in user_messages)
    }
    remaining = [
        QuickReply(label=option.label, message=option.message)
        for option in DEMO_ADDRESSES
        if option.key not in selected
    ]

    current_address_index = _latest_address_message_index(user_messages)
    if current_address_index is None or not has_payout:
        return remaining or _address_replies()

    follow_up_messages = user_messages[current_address_index + 1 :]
    asked_math = any("数式" in message for message in follow_up_messages)
    asked_photo = any(
        "写真" in message or "画像" in message
        for message in follow_up_messages
    )
    asked_reason = any(
        "根拠" in message or "理由" in message
        for message in follow_up_messages
    )

    if asked_photo:
        return remaining
    if asked_math:
        return [*remaining, PHOTO_REPLY]
    if asked_reason:
        return [MATH_REPLY, PHOTO_REPLY]
    return [REASON_REPLY, *remaining]


def _latest_address_message_index(messages: list[str]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        if any(option.address in messages[index] for option in DEMO_ADDRESSES):
            return index
    return None


def _address_replies() -> list[QuickReply]:
    return [
        QuickReply(label=option.label, message=option.message)
        for option in DEMO_ADDRESSES
    ]
