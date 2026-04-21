"""
通知服务模块
支持Telegram通知、通知限流、消息队列
"""
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import get_config
from logger import get_notifier_logger


class RateLimiter:
    """
    通知限流器
    防止消息刷屏
    """
    
    def __init__(self, max_per_minute: int = 5, min_interval: int = 60):
        """
        初始化限流器
        
        Args:
            max_per_minute: 每分钟最大通知数
            min_interval: 相同目标最小间隔（秒）
        """
        self.max_per_minute = max_per_minute
        self.min_interval = min_interval
        
        # 记录发送时间
        self._send_times: List[float] = []
        self._last_send_time: Dict[str, float] = defaultdict(float)
    
    def can_send(self, target: str = "default") -> bool:
        """
        检查是否可以发送
        
        Args:
            target: 目标标识（如币种名称）
        
        Returns:
            是否允许发送
        """
        now = time.time()
        
        # 清理过期记录（保留最近1分钟）
        self._send_times = [t for t in self._send_times if now - t < 60]
        
        # 检查每分钟限制
        if len(self._send_times) >= self.max_per_minute:
            return False
        
        # 检查目标间隔
        last_time = self._last_send_time.get(target, 0)
        if now - last_time < self.min_interval:
            return False
        
        return True
    
    def record_send(self, target: str = "default"):
        """
        记录发送
        
        Args:
            target: 目标标识
        """
        now = time.time()
        self._send_times.append(now)
        self._last_send_time[target] = now
    
    def get_wait_time(self, target: str = "default") -> float:
        """
        获取需要等待的时间
        
        Args:
            target: 目标标识
        
        Returns:
            需要等待的秒数，0表示可以立即发送
        """
        now = time.time()
        
        # 检查目标间隔
        last_time = self._last_send_time.get(target, 0)
        interval_wait = max(0, self.min_interval - (now - last_time))
        
        # 检查每分钟限制
        self._send_times = [t for t in self._send_times if now - t < 60]
        if len(self._send_times) >= self.max_per_minute:
            # 需要等待最早的记录过期
            oldest = min(self._send_times)
            rate_wait = max(0, 60 - (now - oldest))
        else:
            rate_wait = 0
        
        return max(interval_wait, rate_wait)


class TelegramNotifier:
    """
    Telegram通知服务
    """
    
    def __init__(self):
        """初始化Telegram通知服务"""
        self.config = get_config().notification
        self.logger = get_notifier_logger()
        
        # 创建带重试机制的session
        self.session = self._create_session()
        
        # 限流器
        self.rate_limiter = RateLimiter(
            max_per_minute=self.config.rate_limit.max_per_minute,
            min_interval=self.config.rate_limit.min_interval
        )
    
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
    
    def send_message(
        self,
        text: str,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False
    ) -> bool:
        """
        发送Telegram消息
        
        Args:
            text: 消息文本
            parse_mode: 解析模式 (Markdown/HTML)
            disable_notification: 是否静音
        
        Returns:
            是否发送成功
        """
        if not self.config.telegram.enabled:
            self.logger.debug("Telegram通知已禁用")
            return False
        
        config = get_config()
        
        # 构建URL
        url = (
            f"{self.config.telegram.base_url}/"
            f"bot{config.tg_bot_token}/sendMessage"
        )
        
        payload = {
            "chat_id": config.tg_chat_id,
            "text": text,
            "disable_notification": disable_notification
        }
        
        if parse_mode:
            payload["parse_mode"] = parse_mode
        
        try:
            self.logger.debug("发送Telegram消息...")
            
            response = self.session.post(
                url,
                json=payload,
                timeout=self.config.telegram.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    self.logger.info("Telegram消息发送成功")
                    return True
                else:
                    self.logger.error(f"Telegram API错误: {data.get('description')}")
                    return False
            else:
                self.logger.error(f"Telegram请求失败: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            self.logger.error("Telegram请求超时")
            return False
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Telegram请求异常: {e}")
            return False
            
        except Exception as e:
            self.logger.exception(f"Telegram发送异常: {e}")
            return False
    
    def send_alert(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str,
        ai_comment: str
    ) -> bool:
        """
        发送价格报警通知
        
        Args:
            symbol: 币种符号
            price: 当前价格
            change_percent: 波动百分比
            level: 报警级别
            ai_comment: AI点评
        
        Returns:
            是否发送成功
        """
        # 限流检查
        if not self.rate_limiter.can_send(symbol):
            wait_time = self.rate_limiter.get_wait_time(symbol)
            self.logger.warning(
                f"通知限流中，{symbol} 需等待 {wait_time:.1f} 秒"
            )
            return False
        
        # 构建消息
        direction = "📈" if change_percent > 0 else "📉"
        level_emoji = {"minor": "🔔", "moderate": "⚠️", "major": "🚨"}.get(level, "🔔")
        
        message = f"""{level_emoji} **{symbol} 异动警报**

{direction} 现价: ${price:,.4f}
📊 波动: {change_percent:+.2f}%
🎯 级别: {level.upper()}

💭 {ai_comment}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        success = self.send_message(message, parse_mode="Markdown")
        
        if success:
            self.rate_limiter.record_send(symbol)
        
        return success
    
    def send_daily_summary(self, summary: Dict) -> bool:
        """
        发送每日汇总
        
        Args:
            summary: 汇总数据
        
        Returns:
            是否发送成功
        """
        message = f"""📊 **每日行情汇总**

📈 监控币种: {summary.get('symbols_count', 0)}
🔔 今日报警: {summary.get('today_alerts', 0)}
💰 价格记录: {summary.get('total_prices', 0)}

{summary.get('top_gainers', '')}
{summary.get('top_losers', '')}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message, parse_mode="Markdown")
    
    def send_health_check(self, status: Dict) -> bool:
        """
        发送健康检查通知
        
        Args:
            status: 健康状态
        
        Returns:
            是否发送成功
        """
        status_emoji = "✅" if status.get('healthy', False) else "❌"
        
        message = f"""{status_emoji} **系统健康检查**

运行状态: {'正常' if status.get('healthy') else '异常'}
运行时间: {status.get('uptime', 'N/A')}
最后检查: {status.get('last_check', 'N/A')}

问题: {status.get('issues', '无')}
"""
        return self.send_message(message, parse_mode="Markdown")
    
    def close(self):
        """关闭session"""
        self.session.close()
        self.logger.debug("Telegram session已关闭")


class Notifier:
    """
    统一通知服务
    支持多渠道通知
    """
    
    def __init__(self):
        """初始化通知服务"""
        self.logger = get_notifier_logger()
        self.telegram = TelegramNotifier()
    
    def send_alert(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str,
        ai_comment: str
    ) -> bool:
        """
        发送报警通知
        
        Args:
            symbol: 币种符号
            price: 当前价格
            change_percent: 波动百分比
            level: 报警级别
            ai_comment: AI点评
        
        Returns:
            是否发送成功
        """
        return self.telegram.send_alert(
            symbol, price, change_percent, level, ai_comment
        )
    
    def send_daily_summary(self, summary: Dict) -> bool:
        """发送每日汇总"""
        return self.telegram.send_daily_summary(summary)
    
    def send_health_check(self, status: Dict) -> bool:
        """发送健康检查"""
        return self.telegram.send_health_check(status)
    
    def close(self):
        """关闭所有通知渠道"""
        self.telegram.close()


# 全局实例
_notifier: Optional[Notifier] = None


def get_notifier() -> Notifier:
    """获取全局通知服务实例"""
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier


def close_notifier():
    """关闭全局通知服务实例"""
    global _notifier
    if _notifier:
        _notifier.close()
        _notifier = None
