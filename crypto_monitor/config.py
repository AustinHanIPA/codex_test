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
    min_market_cap_usd: float = 0.0
    min_volume_24h_usd: float = 0.0


@dataclass
class MarketConfig:
    """市场数据源配置"""
    base_url: str = ""
    timeout: int = 8
    max_retries: int = 3
    retry_delay: int = 2


@dataclass
class BinanceConfig:
    """Binance REST 数据源配置，支持 Nginx/多 VM 代理池。"""
    base_urls: List[str] = field(default_factory=lambda: ["https://api.binance.com"])
    timeout: int = 10
    max_retries: int = 3
    retry_delay: int = 1
    page_limit: int = 1000


@dataclass
class DexConfig:
    """DEX 聚合数据源配置。"""
    enabled: bool = True
    base_url: str = ""
    chain_id: str = "solana"
    token_addresses: Dict[str, str] = field(default_factory=dict)
    timeout: int = 8
    max_retries: int = 2
    retry_delay: int = 2


@dataclass
class QuantConfig:
    """量化分析配置。"""
    enabled: bool = True
    history_hours: int = 72
    min_score_to_alert: float = 70.0


@dataclass
class ARStrategyConfig:
    """AR/AO 五维自适应策略配置。"""
    enabled: bool = True
    symbol: str = "ARUSDT"
    weekly_interval: str = "1w"
    hourly_interval: str = "1h"
    ma_fast: int = 7
    ma_slow: int = 25
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_period: int = 20
    bollinger_stddev: float = 2.0
    rsi_period: int = 14
    key_resistance: float = 2.645
    funding_rate_threshold: float = 0.0003
    step_in_slices: int = 3
    history_start_time_ms: Optional[int] = None


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
class AffiliateConfig:
    """交易返佣与 Deep Link 配置。"""
    enabled: bool = False
    referral_code: str = ""
    deep_link_template: str = ""
    free_mode: bool = False
    mask_symbol: bool = True


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
class OnchainConfig:
    """链上事件配置"""
    enabled: bool = True
    tracked_addresses: List[str] = field(default_factory=list)
    whale_transfer_threshold_usd: float = 50000.0
    webhook_auth_token: str = ""
    webhook_signature_secret: str = ""
    webhook_signature_header: str = "X-Webhook-Signature"
    max_clock_skew_seconds: int = 300


@dataclass
class RulesConfig:
    """可配置规则。"""
    enabled: bool = True
    market: List[Dict[str, Any]] = field(default_factory=list)
    onchain: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ReportingConfig:
    """报告层配置"""
    enabled: bool = True
    output_dir: str = "./reports"
    default_lookback_hours: int = 24
    major_only: bool = True
    auto_send: bool = False
    daily_hour: int = 8


@dataclass
class ServiceConfig:
    """本地 HTTP 服务配置"""
    host: str = "0.0.0.0"
    port: int = 28593
    admin_token: str = ""


@dataclass
class Config:
    """主配置类"""
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    dex: DexConfig = field(default_factory=DexConfig)
    quant: QuantConfig = field(default_factory=QuantConfig)
    ar_strategy: ARStrategyConfig = field(default_factory=ARStrategyConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    affiliate: AffiliateConfig = field(default_factory=AffiliateConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    onchain: OnchainConfig = field(default_factory=OnchainConfig)
    rules: RulesConfig = field(default_factory=RulesConfig)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)
    service: ServiceConfig = field(default_factory=ServiceConfig)
    
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
            return ""
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

    if 'binance' in config_data:
        config.binance = _dict_to_dataclass(config_data['binance'], BinanceConfig)

    if 'dex' in config_data:
        config.dex = _dict_to_dataclass(config_data['dex'], DexConfig)

    if 'quant' in config_data:
        config.quant = _dict_to_dataclass(config_data['quant'], QuantConfig)

    if 'ar_strategy' in config_data:
        config.ar_strategy = _dict_to_dataclass(config_data['ar_strategy'], ARStrategyConfig)
    
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

    if 'affiliate' in config_data:
        config.affiliate = _dict_to_dataclass(
            config_data['affiliate'], AffiliateConfig
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

    if 'onchain' in config_data:
        config.onchain = _dict_to_dataclass(
            config_data['onchain'], OnchainConfig
        )

    if 'rules' in config_data:
        config.rules = _dict_to_dataclass(
            config_data['rules'], RulesConfig
        )

    if 'reporting' in config_data:
        config.reporting = _dict_to_dataclass(
            config_data['reporting'], ReportingConfig
        )

    if 'service' in config_data:
        config.service = _dict_to_dataclass(
            config_data['service'], ServiceConfig
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
        if not config.dex.base_url:
            config.dex.base_url = f"http://{gcp_ip}/dexscreener"
        if not [item for item in config.binance.base_urls if item]:
            config.binance.base_urls = [f"http://{gcp_ip}/binance"]

    if not config.dex.base_url:
        config.dex.base_url = "https://api.dexscreener.com"

    config.binance.base_urls = [item.rstrip("/") for item in config.binance.base_urls if item]
    if not config.binance.base_urls:
        config.binance.base_urls = ["https://api.binance.com"]

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
