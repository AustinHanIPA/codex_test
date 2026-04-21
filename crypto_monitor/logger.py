"""
日志模块
支持彩色控制台输出、文件滚动日志
"""
import logging
import sys
from pathlib import Path
from typing import Optional

try:
    import colorlog
    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False

from logging.handlers import RotatingFileHandler

from config import LoggingConfig, get_config


# 日志颜色配置
LOG_COLORS = {
    'DEBUG': 'cyan',
    'INFO': 'green',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'red,bg_white',
}


def setup_logger(name: str, config: Optional[LoggingConfig] = None) -> logging.Logger:
    """
    设置日志记录器
    
    Args:
        name: 日志记录器名称
        config: 日志配置，默认从全局配置获取
    
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    if config is None:
        config = get_config().logging
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.level.upper()))
    
    # 清除已有的处理器
    logger.handlers.clear()
    
    # 控制台处理器
    if config.console.enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, config.level.upper()))
        
        if config.console.colored and HAS_COLORLOG:
            # 彩色日志
            formatter = colorlog.ColoredFormatter(
                f"%(log_color)s{config.format}",
                log_colors=LOG_COLORS,
            )
        else:
            # 普通日志
            formatter = logging.Formatter(config.format)
        
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # 文件处理器
    if config.file.enabled:
        # 确保日志目录存在
        log_path = Path(config.file.path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            config.file.path,
            maxBytes=config.file.max_bytes,
            backupCount=config.file.backup_count,
            encoding='utf-8',
        )
        file_handler.setLevel(getattr(logging, config.level.upper()))
        file_handler.setFormatter(logging.Formatter(config.format))
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器
    
    Args:
        name: 日志记录器名称
    
    Returns:
        logging.Logger: 日志记录器
    """
    logger = logging.getLogger(name)
    
    # 如果日志记录器没有处理器，则设置
    if not logger.handlers:
        return setup_logger(name)
    
    return logger


class LoggerAdapter:
    """
    日志适配器，提供便捷的日志方法
    """
    
    def __init__(self, name: str):
        self.logger = get_logger(name)
        self.name = name
    
    def debug(self, msg: str, *args, **kwargs):
        """调试日志"""
        self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        """信息日志"""
        self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """警告日志"""
        self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """错误日志"""
        self.logger.error(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        """严重错误日志"""
        self.logger.critical(msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """异常日志（自动包含堆栈信息）"""
        self.logger.exception(msg, *args, **kwargs)


# 预定义的日志记录器
def get_market_logger() -> LoggerAdapter:
    """获取市场数据日志记录器"""
    return LoggerAdapter("crypto_monitor.market")


def get_ai_logger() -> LoggerAdapter:
    """获取AI服务日志记录器"""
    return LoggerAdapter("crypto_monitor.ai")


def get_notifier_logger() -> LoggerAdapter:
    """获取通知服务日志记录器"""
    return LoggerAdapter("crypto_monitor.notifier")


def get_monitor_logger() -> LoggerAdapter:
    """获取监控引擎日志记录器"""
    return LoggerAdapter("crypto_monitor.monitor")


def get_storage_logger() -> LoggerAdapter:
    """获取存储服务日志记录器"""
    return LoggerAdapter("crypto_monitor.storage")
