"""
Telegram 推送副作用。

将推荐管线的最终结果格式化后推送到 Telegram。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

import aiohttp

from config import get_config
from logger import get_notifier_logger
from pipeline.base import BaseSideEffect
from pipeline.models import ContentItem, ContentType, PipelineContext


class TelegramNotifyEffect(BaseSideEffect):
    """将管线推荐结果推送到 Telegram。"""

    effect_name = "telegram_notify"

    def __init__(self, max_items: int = 10, batch_mode: bool = True):
        self.max_items = max_items
        self.batch_mode = batch_mode
        self.logger = get_notifier_logger()
        self._session: Optional[aiohttp.ClientSession] = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def execute(
        self, items: List[ContentItem], context: PipelineContext
    ) -> None:
        """将推荐结果推送到 Telegram。"""
        config = get_config()
        tg_config = config.notification.telegram

        if not tg_config.enabled:
            self.logger.debug("Telegram 通知未启用，跳过推送")
            return

        if not items:
            self.logger.debug("无推荐内容，跳过 Telegram 推送")
            return

        # 截取推送数量
        to_push = items[: self.max_items]

        if self.batch_mode:
            # 批量模式：合并为一条摘要消息
            message = self._format_batch_message(to_push, context)
            await self._send_message(message, config)
        else:
            # 逐条模式
            for item in to_push:
                message = self._format_single_message(item)
                await self._send_message(message, config)
                await asyncio.sleep(0.5)  # 避免触发 TG 限流

    def _format_batch_message(
        self, items: List[ContentItem], context: PipelineContext
    ) -> str:
        """格式化批量摘要消息。"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        header = f"📡 **Crypto Monitor 推荐** ({now_str})\n"
        header += f"共筛选 {len(items)} 条高价值信息\n"
        header += "━" * 20 + "\n\n"

        body_lines = []
        for i, item in enumerate(items, 1):
            emoji = self._get_type_emoji(item.content_type)
            symbols_str = " ".join(f"${s}" for s in item.symbols[:3]) if item.symbols else ""
            score_str = f"[{item.score_final:.0f}分]"

            line = f"{i}. {emoji} {score_str} {item.title[:60]}"
            if symbols_str:
                line += f"\n   📌 {symbols_str}"
            if item.url:
                line += f"\n   🔗 {item.url}"

            body_lines.append(line)

        footer = "\n\n━" * 1 + "━" * 19
        footer += "\n⚠️ 仅供参考，不构成投资建议。"

        return header + "\n\n".join(body_lines) + footer

    @staticmethod
    def _format_single_message(item: ContentItem) -> str:
        """格式化单条消息。"""
        emoji = TelegramNotifyEffect._get_type_emoji(item.content_type)
        symbols_str = " ".join(f"${s}" for s in item.symbols[:3]) if item.symbols else ""

        message = f"{emoji} **{item.title[:80]}**\n\n"
        if symbols_str:
            message += f"📌 {symbols_str}\n"
        if item.body:
            message += f"{item.body[:200]}\n"
        if item.url:
            message += f"\n🔗 {item.url}\n"
        message += f"\n📊 综合评分: {item.score_final:.0f}/100"

        return message

    @staticmethod
    def _get_type_emoji(content_type: ContentType) -> str:
        """根据内容类型返回 emoji。"""
        mapping = {
            ContentType.NEWS: "📰",
            ContentType.KOL_OPINION: "🗣",
            ContentType.ONCHAIN_ALERT: "⛓",
            ContentType.PRICE_MOVEMENT: "📈",
            ContentType.RISK_WARNING: "🚨",
            ContentType.YOUTUBE_VIDEO: "🎬",
            ContentType.REDDIT_POST: "💬",
            ContentType.TWITTER_POST: "🐦",
        }
        return mapping.get(content_type, "📌")

    async def _send_message(self, text: str, config) -> bool:
        """发送消息到 Telegram。"""
        url = (
            f"{config.notification.telegram.base_url}"
            f"/bot{config.tg_bot_token}/sendMessage"
        )
        payload = {
            "chat_id": config.tg_chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_notification": False,
        }

        session = self._ensure_session()
        try:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("ok"):
                        self.logger.info("Telegram 推送成功")
                        return True
                    self.logger.error(f"Telegram API 错误: {data.get('description')}")
                else:
                    text_body = await response.text()
                    self.logger.error(
                        f"Telegram 请求失败: HTTP {response.status}, {text_body[:200]}"
                    )
        except Exception as exc:
            self.logger.error(f"Telegram 推送异常: {exc}")

        return False

    async def close(self) -> None:
        """关闭 HTTP session。"""
        if self._session and not self._session.closed:
            await self._session.close()
