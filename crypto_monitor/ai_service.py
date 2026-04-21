"""
AI服务模块
支持Gemini等AI模型，提供价格波动点评功能
"""
import re
from typing import Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import get_config
from logger import get_ai_logger


class AIService:
    """
    AI服务
    提供智能价格波动点评功能
    """
    
    def __init__(self):
        """初始化AI服务"""
        self.config = get_config().ai
        self.logger = get_ai_logger()
        
        # 创建带重试机制的session
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """创建带重试机制的requests session"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def generate_comment(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str = "minor",
        style: str = "嘲讽或戏谑"
    ) -> str:
        """
        生成价格波动点评
        
        Args:
            symbol: 币种符号
            price: 当前价格
            change_percent: 波动百分比
            level: 波动级别 (minor/moderate/major)
            style: 评论风格
        
        Returns:
            AI生成的点评内容
        """
        config = get_config()
        
        # 构建API URL
        url = (
            f"{self.config.base_url}/"
            f"{self.config.model}:generateContent"
            f"?key={config.gemini_api_key}"
        )
        
        # 构建提示词
        prompt = self._build_prompt(symbol, price, change_percent, level, style)
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.9,
                "maxOutputTokens": 100,
            }
        }
        
        try:
            self.logger.debug(f"请求AI点评: {symbol} {change_percent:+.2f}%")
            
            response = self.session.post(
                url,
                json=payload,
                timeout=self.config.timeout
            )
            
            if response.status_code != 200:
                self.logger.warning(f"AI请求失败: HTTP {response.status_code}")
                return self._get_fallback_comment(level)
            
            data = response.json()
            
            # 解析响应
            comment = self._parse_response(data)
            
            if comment:
                self.logger.debug(f"AI点评生成成功: {comment[:50]}...")
                return comment
            else:
                return self._get_fallback_comment(level)
                
        except requests.exceptions.Timeout:
            self.logger.error("AI请求超时")
            return self._get_fallback_comment(level)
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"AI请求异常: {e}")
            return self._get_fallback_comment(level)
            
        except Exception as e:
            self.logger.exception(f"AI处理异常: {e}")
            return self._get_fallback_comment(level)
    
    def _build_prompt(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str,
        style: str
    ) -> str:
        """
        构建AI提示词
        
        Args:
            symbol: 币种符号
            price: 当前价格
            change_percent: 波动百分比
            level: 波动级别
            style: 评论风格
        
        Returns:
            构建好的提示词
        """
        # 使用配置中的模板
        template = self.config.prompt_template
        
        if template:
            # 替换模板变量
            prompt = template.format(
                symbol=symbol,
                price=price,
                change=change_percent,
                level=level,
                style=style
            )
        else:
            # 使用默认模板
            direction = "暴涨" if change_percent > 0 else "暴跌"
            intensity = "小幅" if level == "minor" else "大幅" if level == "major" else "明显"
            
            prompt = f"""你是经验丰富的 Web3 交易员。
{symbol} 当前价格 ${price:,.4f}，{intensity}{direction} {abs(change_percent):.2f}%。

请用{style}的网感语境写一句简短点评：
- 带 Emoji 表情
- 50 字以内
- 有趣、有料、有态度
"""
        
        return prompt
    
    def _parse_response(self, data: dict) -> Optional[str]:
        """
        解析AI响应
        
        Args:
            data: API响应数据
        
        Returns:
            解析出的文本内容
        """
        try:
            candidates = data.get('candidates', [])
            if not candidates:
                return None
            
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if not parts:
                return None
            
            text = parts[0].get('text', '').strip()
            
            # 清理可能的多余内容
            text = self._clean_text(text)
            
            return text if text else None
            
        except (KeyError, IndexError, TypeError) as e:
            self.logger.error(f"AI响应解析失败: {e}")
            return None
    
    def _clean_text(self, text: str) -> str:
        """
        清理AI生成的文本
        
        Args:
            text: 原始文本
        
        Returns:
            清理后的文本
        """
        # 移除可能的前后引号
        text = text.strip('"\'')
        
        # 移除多余空白
        text = ' '.join(text.split())
        
        # 限制长度（保留Emoji）
        if len(text) > 100:
            text = text[:97] + '...'
        
        return text
    
    def _get_fallback_comment(self, level: str) -> str:
        """
        获取备用评论（当AI服务不可用时）
        
        Args:
            level: 波动级别
        
        Returns:
            备用评论
        """
        fallbacks = {
            "minor": [
                "🤔 小风小浪，稳住别慌~",
                "😏 这点波动，洒洒水啦~",
                "🤷 正常波动，继续观察~",
            ],
            "moderate": [
                "⚠️ 波动加大，注意仓位！",
                "📊 行情有变化，密切关注中...",
                "👀 这波有点意思，盯紧了！",
            ],
            "major": [
                "🚨 重大波动！请立即检查仓位！",
                "💥 大动作来了！系好安全带！",
                "🔥 行情剧烈波动，保持冷静！",
            ]
        }
        
        import random
        return random.choice(fallbacks.get(level, fallbacks["minor"]))
    
    def close(self):
        """关闭session"""
        self.session.close()
        self.logger.debug("AI服务session已关闭")


class MockAIService(AIService):
    """
    模拟AI服务（用于测试）
    """
    
    def generate_comment(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str = "minor",
        style: str = "嘲讽或戏谑"
    ) -> str:
        """生成模拟评论"""
        direction = "📈" if change_percent > 0 else "📉"
        return f"{direction} {symbol} {'上涨' if change_percent > 0 else '下跌'} {abs(change_percent):.2f}% [模拟AI点评]"


# 全局实例
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """获取全局AI服务实例"""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service


def close_ai_service():
    """关闭全局AI服务实例"""
    global _ai_service
    if _ai_service:
        _ai_service.close()
        _ai_service = None
