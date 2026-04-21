"""
配置管理模块
支持环境变量、YAML配置文件，提供类型安全的配置访问
"""
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv


@dataclass
class ThresholdConfig:
    """波动阈值配置"""
    minor: float = 0.5
    moderate: float = 1.5
    major: float = 3.0

    def get_level(self, change: float) -> tuple[str, str]:
        """
        根据波动幅度返回级别和风格
        
        Returns:
            (level, style): 级别和对应的风格描述
        """
        abs_change = abs(change)
        if abs_change >= self.major:
            return "major", "紧急或热血"
        elif abs_change >= self.moderate:
            return "moderate", "专业分析"
        else:
            return "minor", "嘲讽或戏谑"


@dataclass
class MonitorConfig:
    """监控配置"""
    watch_list: List[str] = field(default_factory=lambda: ["WIF", "SOL", "PEPE", "BOME", "BTC"])
    interval: int = 30
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    cooldown: int = 60


@dataclass
class MarketConfig:
    """市场数据源配置"""
    base_url: str = ""
    timeout: int = 8
    max_retries: int = 3
    retry_delay: int = 2


@dataclass
class AIConfig:
    """AI服务配置"""
    provider: str = "gemini"
    model: str = "gemini-1.5-flash"
    base_url: str = ""
    timeout: int = 15
    prompt_template: str = ""


@dataclass
class RateLimitConfig:
    """通知限流配置"""
    max_per_minute: int = 5
    min_interval: int = 60


@dataclass
class TelegramConfig:
    """Telegram配置"""
    enabled: bool = True
    base_url: str = ""
    timeout: int = 10


@dataclass
class NotificationConfig:
    """通知配置"""
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)


@dataclass
class SQLiteConfig:
    """SQLite配置"""
    path: str = "./data/crypto_monitor.db"


@dataclass
class StorageConfig:
    """存储配置"""
    type: str = "sqlite"
    sqlite: SQLiteConfig = field(default_factory=SQLiteConfig)
    history_retention_days: int = 30


@dataclass
class FileLogConfig:
    """文件日志配置"""
    enabled: bool = True
    path: str = "./logs/crypto_monitor.log"
    max_bytes: int = 10485760  # 10MB
    backup_count: int = 5


@dataclass
class ConsoleLogConfig:
    """控制台日志配置"""
    enabled: bool = True
    colored: bool = True


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: FileLogConfig = field(default_factory=FileLogConfig)
    console: ConsoleLogConfig = field(default_factory=ConsoleLogConfig)


@dataclass
class HealthCheckConfig:
    """健康检查配置"""
    enabled: bool = True
    interval: int = 300
    max_failures: int = 3
    auto_restart: bool = True


@dataclass
class Config:
    """主配置类"""
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    
    # 敏感信息（从环境变量读取）
    gcp_ip: str = ""
    gemini_api_key: str = ""
    tg_bot_token: str = ""
    tg_chat_id: str = ""


# 需要用环境变量替换的配置键名
ENV_VAR_KEYS = {'base_url', 'path'}

# 模板占位符（运行时替换，不在此处理）
TEMPLATE_PLACEHOLDERS = {'symbol', 'price', 'change', 'level', 'style'}


def _substitute_env_vars(value: str, key_name: str = '') -> str:
    """
    替换字符串中的环境变量占位符
    支持格式: ${VAR_NAME}
    
    Args:
        value: 配置值
        key_name: 配置键名，用于判断是否需要替换
    """
    if not isinstance(value, str):
        return value
    
    # 匹配 ${VAR_NAME} 格式
    pattern = r'\$\{([^}]+)\}'
    
    def replacer(match):
        var_name = match.group(1)
        
        # 提取实际变量名（去掉 : 后面的格式化部分）
        actual_var = var_name.split(':')[0]
        
        # 如果是模板占位符，保持原样
        if actual_var in TEMPLATE_PLACEHOLDERS:
            return match.group(0)  # 返回原始匹配
        
        env_value = os.getenv(actual_var, "")
        if not env_value:
            raise ValueError(f"环境变量 {actual_var} 未设置")
        return env_value
    
    return re.sub(pattern, replacer, value)


def _process_config_values(config: Dict[str, Any]) -> Dict[str, Any]:
    """递归处理配置值，替换环境变量"""
    result = {}
    for key, value in config.items():
        if isinstance(value, dict):
            result[key] = _process_config_values(value)
        elif isinstance(value, str):
            result[key] = _substitute_env_vars(value, key)
        elif isinstance(value, list):
            result[key] = [
                _substitute_env_vars(item, key) if isinstance(item, str) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def _dict_to_dataclass(data: Dict[str, Any], dataclass_type: type) -> Any:
    """将字典转换为dataclass实例"""
    if not isinstance(data, dict):
        return data
    
    # 获取dataclass的字段信息
    fields = {f.name: f.type for f in dataclass_type.__dataclass_fields__.values()}
    
    kwargs = {}
    for field_name, field_type in fields.items():
        if field_name in data:
            value = data[field_name]
            # 检查字段类型是否是dataclass
            if hasattr(field_type, '__dataclass_fields__'):
                kwargs[field_name] = _dict_to_dataclass(value, field_type)
            else:
                kwargs[field_name] = value
    
    return dataclass_type(**kwargs)


def load_config(config_path: Optional[str] = None, env_path: Optional[str] = None) -> Config:
    """
    加载配置
    
    Args:
        config_path: YAML配置文件路径，默认为 ./config.yaml
        env_path: .env文件路径，默认为 ./.env
    
    Returns:
        Config: 配置对象
    """
    # 加载环境变量
    if env_path is None:
        env_path = str(Path(__file__).parent / ".env")
    load_dotenv(env_path)
    
    # 读取敏感信息
    gcp_ip = os.getenv("GCP_IP", "")
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    tg_bot_token = os.getenv("TG_BOT_TOKEN", "")
    tg_chat_id = os.getenv("TG_CHAT_ID", "")
    
    # 加载YAML配置
    if config_path is None:
        config_path = str(Path(__file__).parent / "config.yaml")
    
    config_data = {}
    if Path(config_path).exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f) or {}
    
    # 替换环境变量
    config_data = _process_config_values(config_data)
    
    # 构建配置对象
    config = Config()
    
    # 映射YAML配置到dataclass
    if 'monitor' in config_data:
        config.monitor = _dict_to_dataclass(config_data['monitor'], MonitorConfig)
        if 'thresholds' in config_data['monitor']:
            config.monitor.thresholds = _dict_to_dataclass(
                config_data['monitor']['thresholds'], ThresholdConfig
            )
    
    if 'market' in config_data:
        config.market = _dict_to_dataclass(config_data['market'], MarketConfig)
    
    if 'ai' in config_data:
        config.ai = _dict_to_dataclass(config_data['ai'], AIConfig)
    
    if 'notification' in config_data:
        config.notification = _dict_to_dataclass(
            config_data['notification'], NotificationConfig
        )
        if 'telegram' in config_data['notification']:
            config.notification.telegram = _dict_to_dataclass(
                config_data['notification']['telegram'], TelegramConfig
            )
        if 'rate_limit' in config_data['notification']:
            config.notification.rate_limit = _dict_to_dataclass(
                config_data['notification']['rate_limit'], RateLimitConfig
            )
    
    if 'storage' in config_data:
        config.storage = _dict_to_dataclass(config_data['storage'], StorageConfig)
        if 'sqlite' in config_data['storage']:
            config.storage.sqlite = _dict_to_dataclass(
                config_data['storage']['sqlite'], SQLiteConfig
            )
    
    if 'logging' in config_data:
        config.logging = _dict_to_dataclass(config_data['logging'], LoggingConfig)
        if 'file' in config_data['logging']:
            config.logging.file = _dict_to_dataclass(
                config_data['logging']['file'], FileLogConfig
            )
        if 'console' in config_data['logging']:
            config.logging.console = _dict_to_dataclass(
                config_data['logging']['console'], ConsoleLogConfig
            )
    
    if 'health_check' in config_data:
        config.health_check = _dict_to_dataclass(
            config_data['health_check'], HealthCheckConfig
        )
    
    # 设置敏感信息
    config.gcp_ip = gcp_ip
    config.gemini_api_key = gemini_api_key
    config.tg_bot_token = tg_bot_token
    config.tg_chat_id = tg_chat_id
    
    # 构建完整URL
    if gcp_ip:
        if not config.market.base_url:
            config.market.base_url = f"http://{gcp_ip}/mexc/api/v3/ticker/price"
        if not config.ai.base_url:
            config.ai.base_url = f"http://{gcp_ip}/gemini/v1beta/models"
        if not config.notification.telegram.base_url:
            config.notification.telegram.base_url = f"http://{gcp_ip}/tg"
    
    return config


# 全局配置实例
_config: Optional[Config] = None


def get_config(reload: bool = False) -> Config:
    """
    获取全局配置实例
    
    Args:
        reload: 是否重新加载配置
    
    Returns:
        Config: 配置对象
    """
    global _config
    if _config is None or reload:
        _config = load_config()
    return _config
