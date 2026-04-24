"""
AI 服务模块。

借鉴 api-doc-inspect 的思路，尽量让模型输出结构化结果，并对非标准返回做兜底解析。
"""
from __future__ import annotations

import json
import re
from string import Template
from typing import Any, Dict, Optional

import aiohttp

from config import get_config
from logger import get_ai_logger
from models import AIInsight, MarketSnapshot, OnchainEvent


class AIService:
    """Gemini 兼容模型调用封装。"""

    def __init__(self):
        root_config = get_config()
        self.config = root_config.ai
        self.api_key = root_config.gemini_api_key
        self.logger = get_ai_logger()
        self.url = (
            f"{self.config.base_url}/{self.config.model}:generateContent?key={self.api_key}"
            if self.api_key and self.config.base_url
            else ""
        )

    def _render_prompt(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str,
        style: str,
        snapshot: Optional[MarketSnapshot],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        template_text = self.config.prompt_template.strip()
        template_text = template_text.replace("${change:.2f}", "${change}")
        if not template_text:
            template_text = (
                "你是经验丰富的 Web3 交易员。${symbol} 当前价格 ${price}，近期波动 ${change}%。"
                "波动级别：${level}，风格：${style}，市值：${market_cap}。"
            )

        payload = {
            "symbol": symbol,
            "price": f"{price:,.4f}",
            "change": f"{change_percent:+.2f}",
            "level": level,
            "style": style,
            "market_cap": self._format_optional_number(snapshot.market_cap if snapshot else None),
        }
        rendered = Template(template_text).safe_substitute(payload)
        context_text = self._format_context(context or {})
        if context_text:
            return f"{rendered}\n补充上下文：{context_text}"
        return rendered

    def _render_onchain_prompt(
        self,
        event: OnchainEvent,
        level: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        context_text = self._format_context(context or {})
        return (
            "你是经验丰富的 Web3 风控分析师。请分析以下链上事件："
            f"事件类型={event.event_type}，来源={event.source}，地址={event.address}，"
            f"对手方={event.counterparty or '未知'}，代币={event.symbol or '未知'}，"
            f"金额={event.amount or '未知'}，美元价值={event.amount_usd or '未知'}，"
            f"方向={event.direction}，级别={level}。"
            f"{' 补充上下文：' + context_text if context_text else ''}"
        )

    @staticmethod
    def _format_context(context: Dict[str, Any]) -> str:
        if not context:
            return ""
        parts = []
        for key, value in context.items():
            if value in (None, "", [], {}):
                continue
            parts.append(f"{key}={value}")
        return "；".join(parts)

    @staticmethod
    def _format_optional_number(value: Optional[float]) -> str:
        if value is None:
            return "未知"
        return f"{value:,.2f}"

    @staticmethod
    def _extract_text(response_data: Dict[str, Any]) -> str:
        candidates = response_data.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                text = part.get("text")
                if text:
                    return text.strip()
        return ""

    def _parse_insight(self, text: str) -> AIInsight:
        cleaned = text.strip()
        if not cleaned:
            return AIInsight(comment="🤔 市场波动中，先继续观察。", raw_text=text)

        fenced_json = re.search(r"```json\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        candidate = fenced_json.group(1) if fenced_json else cleaned

        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return AIInsight(
                    comment=str(data.get("comment") or data.get("text") or cleaned).strip(),
                    sentiment=str(data.get("sentiment") or "neutral").strip(),
                    event_type=str(data.get("event_type") or "price_movement").strip(),
                    risk_hint=str(data.get("risk_hint") or "").strip(),
                    suggested_action=str(data.get("suggested_action") or "").strip(),
                    confidence=self._parse_confidence(data.get("confidence")),
                    raw_text=cleaned,
                )
        except json.JSONDecodeError:
            self.logger.debug("AI 返回不是标准 JSON，使用文本兜底解析")

        first_line = cleaned.splitlines()[0].strip()
        return AIInsight(comment=first_line[:120], raw_text=cleaned)

    @staticmethod
    def _parse_confidence(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(parsed, 1.0))

    def _build_payload(self, prompt: str) -> Dict[str, Any]:
        instruction = (
            "请只输出 JSON，结构为 "
            '{"comment":"50字以内短评，带 Emoji","sentiment":"bullish/bearish/neutral",'
            '"event_type":"price_movement/onchain_whale/new_pair/liquidity_change/system",'
            '"risk_hint":"一句风险提示","suggested_action":"一句操作建议","confidence":0.0}。'
        )
        return {
            "contents": [{"parts": [{"text": f"{prompt}\n{instruction}"}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 220},
        }

    async def _request_insight(
        self,
        payload: Dict[str, Any],
        session: Optional[aiohttp.ClientSession] = None,
    ) -> AIInsight:
        owns_session = session is None
        if owns_session:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            session = aiohttp.ClientSession(timeout=timeout)

        assert session is not None
        try:
            async with session.post(self.url, json=payload) as response:
                if response.status != 200:
                    self.logger.warning(f"AI 服务响应异常: HTTP {response.status}")
                    return AIInsight(comment="🤔 情绪有点乱，先盯紧下一根 K 线。", sentiment="neutral")

                data = await response.json()
                text = self._extract_text(data)
                insight = self._parse_insight(text)
                if not insight.comment:
                    insight.comment = "🤔 情绪有点乱，先盯紧下一根 K 线。"
                return insight
        except Exception as exc:
            self.logger.error(f"AI 请求异常: {exc}")
            return AIInsight(comment="🤔 市场噪音较大，继续观察量价配合。", sentiment="neutral")
        finally:
            if owns_session:
                await session.close()

    async def generate_insight(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str,
        style: str,
        snapshot: Optional[MarketSnapshot] = None,
        context: Optional[Dict[str, Any]] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> AIInsight:
        """请求结构化 AI 洞察。"""
        if not self.url:
            return AIInsight(comment="🤖 AI 未配置，已切换到默认点评。", sentiment="neutral")

        prompt = self._render_prompt(symbol, price, change_percent, level, style, snapshot, context)
        return await self._request_insight(self._build_payload(prompt), session=session)

    async def generate_onchain_insight(
        self,
        event: OnchainEvent,
        level: str,
        context: Optional[Dict[str, Any]] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> AIInsight:
        """请求链上事件结构化洞察。"""
        if not self.url:
            return AIInsight(
                comment="🤖 AI 未配置，链上事件已按规则告警。",
                sentiment="neutral",
                event_type=event.event_type or "onchain_whale",
            )

        prompt = self._render_onchain_prompt(event, level, context)
        insight = await self._request_insight(self._build_payload(prompt), session=session)
        if insight.event_type == "price_movement":
            insight.event_type = event.event_type or "onchain_whale"
        return insight

    async def generate_comment(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str,
        style: str,
        session: Optional[aiohttp.ClientSession] = None,
        snapshot: Optional[MarketSnapshot] = None,
    ) -> str:
        """兼容旧接口，仅返回短评文本。"""
        insight = await self.generate_insight(
            symbol=symbol,
            price=price,
            change_percent=change_percent,
            level=level,
            style=style,
            snapshot=snapshot,
            context=None,
            session=session,
        )
        return insight.comment


_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service


def close_ai_service() -> None:
    global _ai_service
    _ai_service = None
