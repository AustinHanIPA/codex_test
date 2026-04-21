"""
监控引擎模块
核心监控逻辑，支持动态币种管理、健康检查、自恢复机制
"""
import asyncio
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from config import get_config, MonitorConfig
from logger import get_monitor_logger
from market import get_fetcher, close_fetcher
from ai_service import get_ai_service, close_ai_service
from notifier import get_notifier, close_notifier
from storage import get_storage, close_storage


class PriceState:
    """
    币种价格状态管理
    """
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.last_price: float = 0.0
        self.last_alert_time: Optional[datetime] = None
        self.last_check_time: Optional[datetime] = None
        self.consecutive_changes: List[float] = []  # 连续波动记录
        self.max_consecutive: int = 5
    
    def update_price(self, price: float) -> float:
        """
        更新价格，返回波动百分比
        
        Args:
            price: 新价格
        
        Returns:
            波动百分比
        """
        if self.last_price == 0.0:
            self.last_price = price
            self.last_check_time = datetime.now()
            return 0.0
        
        change = ((price - self.last_price) / self.last_price) * 100
        
        # 记录连续波动
        self.consecutive_changes.append(change)
        if len(self.consecutive_changes) > self.max_consecutive:
            self.consecutive_changes.pop(0)
        
        self.last_price = price
        self.last_check_time = datetime.now()
        
        return change
    
    def get_trend(self) -> str:
        """
        分析连续波动趋势
        
        Returns:
            趋势描述: 'up', 'down', 'stable', 'volatile'
        """
        if len(self.consecutive_changes) < 3:
            return 'stable'
        
        avg_change = sum(self.consecutive_changes) / len(self.consecutive_changes)
        
        # 判断趋势
        if avg_change > 0.5:
            return 'up'
        elif avg_change < -0.5:
            return 'down'
        elif max(abs(c) for c in self.consecutive_changes) > 1.0:
            return 'volatile'
        else:
            return 'stable'
    
    def can_alert(self, cooldown: int) -> bool:
        """
        检查是否可以发送报警
        
        Args:
            cooldown: 冷却时间（秒）
        
        Returns:
            是否可以报警
        """
        if self.last_alert_time is None:
            return True
        
        elapsed = (datetime.now() - self.last_alert_time).total_seconds()
        return elapsed >= cooldown
    
    def mark_alerted(self):
        """标记已报警"""
        self.last_alert_time = datetime.now()


class MonitorEngine:
    """
    监控引擎
    核心监控逻辑实现
    """
    
    def __init__(self):
        """初始化监控引擎"""
        self.config = get_config()
        self.logger = get_monitor_logger()
        
        # 组件
        self.fetcher = get_fetcher()
        self.ai_service = get_ai_service()
        self.notifier = get_notifier()
        self.storage = None  # 异步初始化
        
        # 状态
        self.price_states: Dict[str, PriceState] = {}
        self.watch_list: Set[str] = set(self.config.monitor.watch_list)
        self.running = False
        self.paused = False
        
        # 健康检查
        self.start_time: Optional[datetime] = None
        self.failure_count = 0
        self.last_success_time: Optional[datetime] = None
        
        # 回调
        self._on_alert_callbacks: List[Callable] = []
        self._on_price_update_callbacks: List[Callable] = []
    
    async def initialize(self):
        """异步初始化"""
        self.storage = await get_storage()
        
        # 从数据库恢复状态
        await self._restore_states()
        
        self.logger.info(
            f"监控引擎初始化完成，监听币种: {list(self.watch_list)}"
        )
    
    async def _restore_states(self):
        """从数据库恢复币种状态"""
        if self.storage:
            states = await self.storage.get_all_symbol_states()
            for symbol, state in states.items():
                if symbol in self.watch_list:
                    price_state = PriceState(symbol)
                    price_state.last_price = state['last_price']
                    price_state.last_alert_time = state['last_alert_time']
                    self.price_states[symbol] = price_state
                    self.logger.info(
                        f"恢复 {symbol} 状态: 价格 {state['last_price']}"
                    )
    
    def add_symbol(self, symbol: str):
        """
        添加监控币种
        
        Args:
            symbol: 币种符号
        """
        if symbol not in self.watch_list:
            self.watch_list.add(symbol)
            self.price_states[symbol] = PriceState(symbol)
            self.logger.info(f"添加监控币种: {symbol}")
    
    def remove_symbol(self, symbol: str):
        """
        移除监控币种
        
        Args:
            symbol: 币种符号
        """
        if symbol in self.watch_list:
            self.watch_list.discard(symbol)
            self.price_states.pop(symbol, None)
            self.logger.info(f"移除监控币种: {symbol}")
    
    def get_watch_list(self) -> List[str]:
        """获取当前监控币种列表"""
        return list(self.watch_list)
    
    def on_alert(self, callback: Callable):
        """注册报警回调"""
        self._on_alert_callbacks.append(callback)
    
    def on_price_update(self, callback: Callable):
        """注册价格更新回调"""
        self._on_price_update_callbacks.append(callback)
    
    async def _trigger_alert_callbacks(self, data: Dict[str, Any]):
        """触发报警回调"""
        for callback in self._on_alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(f"报警回调执行失败: {e}")
    
    async def _trigger_price_update_callbacks(self, data: Dict[str, Any]):
        """触发价格更新回调"""
        for callback in self._on_price_update_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(f"价格更新回调执行失败: {e}")
    
    async def check_prices(self) -> Dict[str, Dict[str, Any]]:
        """
        检查价格波动
        
        Returns:
            各币种检查结果
        """
        results = {}
        
        # 获取全市场数据
        price_map = self.fetcher.get_all_prices()
        
        if not price_map:
            self.failure_count += 1
            self.logger.warning(
                f"获取市场数据失败，连续失败次数: {self.failure_count}"
            )
            return results
        
        # 重置失败计数
        self.failure_count = 0
        self.last_success_time = datetime.now()
        
        # 检查每个币种
        for symbol in list(self.watch_list):
            pair_name = f"{symbol}USDT"
            current_price = price_map.get(pair_name)
            
            if current_price is None:
                self.logger.warning(f"未找到交易对: {pair_name}")
                continue
            
            # 获取或创建状态
            if symbol not in self.price_states:
                self.price_states[symbol] = PriceState(symbol)
            
            state = self.price_states[symbol]
            
            # 更新价格并计算波动
            change = state.update_price(current_price)
            
            result = {
                'symbol': symbol,
                'price': current_price,
                'change': change,
                'trend': state.get_trend(),
                'should_alert': False,
                'alert_level': None
            }
            
            # 检查是否需要报警
            if change != 0.0:
                abs_change = abs(change)
                thresholds = self.config.monitor.thresholds
                
                # 确定报警级别
                if abs_change >= thresholds.major:
                    result['alert_level'] = 'major'
                elif abs_change >= thresholds.moderate:
                    result['alert_level'] = 'moderate'
                elif abs_change >= thresholds.minor:
                    result['alert_level'] = 'minor'
                
                # 检查是否可以报警（冷却时间）
                if result['alert_level'] and state.can_alert(self.config.monitor.cooldown):
                    result['should_alert'] = True
            
            results[symbol] = result
            
            # 保存价格记录
            if self.storage:
                await self.storage.save_price(symbol, current_price, change)
            
            # 触发价格更新回调
            await self._trigger_price_update_callbacks(result)
        
        return results
    
    async def process_alert(self, result: Dict[str, Any]) -> bool:
        """
        处理报警
        
        Args:
            result: 检查结果
        
        Returns:
            是否处理成功
        """
        symbol = result['symbol']
        price = result['price']
        change = result['change']
        level = result['alert_level']
        
        self.logger.info(
            f"🚨 {symbol} 波动达 {change:+.2f}%，触发 {level} 级报警"
        )
        
        # 获取波动级别和风格
        thresholds = self.config.monitor.thresholds
        _, style = thresholds.get_level(change)
        
        # 生成AI点评
        ai_comment = self.ai_service.generate_comment(
            symbol, price, change, level, style
        )
        
        # 发送通知
        success = self.notifier.send_alert(
            symbol, price, change, level, ai_comment
        )
        
        if success:
            # 更新状态
            state = self.price_states.get(symbol)
            if state:
                state.mark_alerted()
            
            # 保存报警记录
            if self.storage:
                await self.storage.save_alert(
                    symbol, price, change, level, ai_comment
                )
                await self.storage.update_symbol_state(
                    symbol, price, datetime.now()
                )
            
            # 触发报警回调
            await self._trigger_alert_callbacks({
                'symbol': symbol,
                'price': price,
                'change': change,
                'level': level,
                'ai_comment': ai_comment,
                'sent_at': datetime.now().isoformat()
            })
        
        return success
    
    async def run_once(self) -> Dict[str, Any]:
        """
        执行一次监控检查
        
        Returns:
            检查结果汇总
        """
        results = await self.check_prices()
        
        alerts = []
        for symbol, result in results.items():
            if result.get('should_alert'):
                alert_success = await self.process_alert(result)
                alerts.append({
                    'symbol': symbol,
                    'success': alert_success
                })
        
        return {
            'total_checked': len(results),
            'alerts_triggered': len(alerts),
            'alerts': alerts,
            'timestamp': datetime.now().isoformat(),
            'results': results  # 包含详细价格结果
        }
    
    async def run_forever(self):
        """
        持续运行监控循环
        """
        self.running = True
        self.start_time = datetime.now()
        
        self.logger.info(f"🚀 监控引擎启动，间隔: {self.config.monitor.interval}秒")
        
        while self.running:
            try:
                if not self.paused:
                    summary = await self.run_once()
                    
                    # 打印状态
                    self._print_status(summary)
                    
                    # 健康检查
                    if self.config.health_check.enabled:
                        await self._health_check()
                
                # 等待下次检查
                await asyncio.sleep(self.config.monitor.interval)
                
            except asyncio.CancelledError:
                self.logger.info("监控循环被取消")
                break
            except Exception as e:
                self.logger.exception(f"监控循环异常: {e}")
                await asyncio.sleep(5)  # 异常后等待5秒
    
    def _print_status(self, summary: Dict[str, Any]):
        """打印状态信息"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        checked = summary['total_checked']
        alerts = summary['alerts_triggered']
        
        status = "⏸️ 暂停" if self.paused else "✅ 运行中"
        
        print(
            f"[{timestamp}] {status} | "
            f"检查: {checked} | 报警: {alerts}"
        )
        
        # 打印各币种价格详情
        results = summary.get('results', {})
        for symbol, result in results.items():
            price = result.get('price', 0)
            change = result.get('change', 0)
            change_str = f"{change:+.2f}%"
            
            # 根据波动方向选择 emoji
            if change > 0:
                emoji = "📈"
            elif change < 0:
                emoji = "📉"
            else:
                emoji = "➖"
            
            print(f"  {emoji} {symbol}: ${price:,.4f} ({change_str})")
    
    async def _health_check(self):
        """
        健康检查
        """
        max_failures = self.config.health_check.max_failures
        
        if self.failure_count >= max_failures:
            self.logger.error(
                f"连续失败 {self.failure_count} 次，触发健康检查"
            )
            
            # 发送健康检查通知
            self.notifier.send_health_check({
                'healthy': False,
                'uptime': str(datetime.now() - self.start_time) if self.start_time else 'N/A',
                'last_check': self.last_success_time.isoformat() if self.last_success_time else 'N/A',
                'issues': f'连续失败 {self.failure_count} 次'
            })
            
            # 自恢复
            if self.config.health_check.auto_restart:
                self.logger.info("尝试自恢复...")
                self.fetcher.clear_cache()
                self.failure_count = 0
    
    def pause(self):
        """暂停监控"""
        self.paused = True
        self.logger.info("监控已暂停")
    
    def resume(self):
        """恢复监控"""
        self.paused = False
        self.logger.info("监控已恢复")
    
    def stop(self):
        """停止监控"""
        self.running = False
        self.logger.info("监控引擎停止")
    
    def get_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        uptime = None
        if self.start_time:
            uptime = str(datetime.now() - self.start_time)
        
        return {
            'running': self.running,
            'paused': self.paused,
            'uptime': uptime,
            'watch_list': list(self.watch_list),
            'watch_list_count': len(self.watch_list),
            'failure_count': self.failure_count,
            'last_success': self.last_success_time.isoformat() if self.last_success_time else None,
            'start_time': self.start_time.isoformat() if self.start_time else None,
        }
    
    async def cleanup(self):
        """清理资源"""
        self.logger.info("清理资源...")
        
        # 保存状态到数据库
        if self.storage:
            for symbol, state in self.price_states.items():
                await self.storage.update_symbol_state(
                    symbol, state.last_price, state.last_alert_time
                )
            
            # 清理过期数据
            await self.storage.cleanup_old_data(
                self.config.storage.history_retention_days
            )
        
        # 关闭连接
        close_fetcher()
        close_ai_service()
        close_notifier()
        await close_storage()
        
        self.logger.info("资源清理完成")


async def main():
    """主函数"""
    engine = MonitorEngine()
    await engine.initialize()
    
    # 注册信号处理
    def signal_handler(sig, frame):
        print("\n收到停止信号...")
        engine.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await engine.run_forever()
    finally:
        await engine.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
