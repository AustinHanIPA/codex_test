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
from models import AIInsight, MarketSnapshot


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
        return Template(template_text).safe_substitute(payload)

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
                    risk_hint=str(data.get("risk_hint") or "").strip(),
                    raw_text=cleaned,
                )
        except json.JSONDecodeError:
            self.logger.debug("AI 返回不是标准 JSON，使用文本兜底解析")

        first_line = cleaned.splitlines()[0].strip()
        return AIInsight(comment=first_line[:120], raw_text=cleaned)

    async def generate_insight(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str,
        style: str,
        snapshot: Optional[MarketSnapshot] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> AIInsight:
        """请求结构化 AI 洞察。"""
        if not self.url:
            return AIInsight(comment="🤖 AI 未配置，已切换到默认点评。", sentiment="neutral")

        prompt = self._render_prompt(symbol, price, change_percent, level, style, snapshot)
        instruction = (
            "请你只输出 JSON，结构为 "
            '{"comment":"50字以内短评，带 Emoji","sentiment":"bullish/bearish/neutral","risk_hint":"一句风险提示"}。'
        )
        payload = {
            "contents": [{"parts": [{"text": f"{prompt}\n{instruction}"}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 160},
        }

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
