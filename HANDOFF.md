# HANDOFF

## 当前目标
把 `crypto_monitor` 从单体监控服务升级为**推荐管线架构**（Pipeline v3.0），实现多源信息聚合、智能筛选和个性化推荐：Query Hydration → Sources → Hydrators → Filters → Scorers → Selector/Blender → Side Effects。

## 已完成
- 本地服务已监听在 `28593`，并提供健康检查、状态、统计、监控名单、告警、链上事件、投递记录、webhook 和日报接口。
- 监控主链路已异步化，包含行情抓取、Telegram 通知、SQLite 存储。
- 配置层已扩展出 `onchain`、`rules`、`reporting`、`service.port=28593`、`service.admin_token` 等字段。
- 领域模型已补充 `MarketSnapshot`、`AIInsight`、`OnchainEvent`。
- `RuleEngine` 已接入主流程，并支持轻量 `rules.market` / `rules.onchain` 配置规则。
- webhook 已支持 token、HMAC-SHA256 签名和事件去重。
- 已新增链上 provider payload 归一化、结构化 AI 输出、Markdown 日报、通知投递记录。
- 已集成 AR/AO 五维策略 MVP：Binance K 线分页抓取、MA7/MA25、MACD、RSI、Bollinger、`GET /strategies/ar` 和 `--ar-signal`。
- **[NEW] 推荐管线架构（Pipeline v3.0）已完成全部 7 层实现：**
  - **Query Hydration**: 查询扩展器，加载用户画像、解析 symbols、生成 PipelineContext
  - **Sources (7个)**: Market / Onchain / Twitter / News / KOL / YouTube / Reddit
  - **Hydrators (5个)**: Price / Volume / Sentiment / Project / RiskTag
  - **Filters (4个)**: Duplicate / Scam / Stale / LowCredibility
  - **Scorers (4个)**: Hotness / Credibility / Impact / Relevance
  - **Selector/Blender (2个)**: WeightedSelector（加权排序）/ DiversityBlender（多样性混排）
  - **Side Effects (3个)**: TelegramNotify / Storage / Report
  - **Orchestrator**: 管线编排器，支持并发 Source/Scorer、顺序 Hydrator/Filter、超时控制
  - **Factory**: `create_default_pipeline()` 一键组装完整管线
  - **pipeline_main.py**: 独立 CLI 入口，支持 `--query`、`--loop`、`--json` 等参数
  - **main.py** 新增 `--pipeline` / `--pipeline-query` 参数集成管线模式

## 待办
- 为各 Source 接入真实 API（当前为骨架实现，返回模拟数据）。
- SentimentHydrator 接入 Gemini AI 进行真实情绪分析。
- 接入真实 Helius/QuickNode webhook 样本，继续完善 `onchain.py` 字段映射。
- 为 AR 策略接入 AO 存储量、GitHub 活跃度、社媒权重、资金费率和盘口深度数据源。
- 增加 AR 策略回测、模拟盘和最大回撤熔断后，再考虑执行层。
- 增加失败通知重试和死信列表。
- 接入 DEX Screener / Birdeye，补齐 DEX 价格、流动性和市值。
- 将规则 DSL 从轻量 `all` 条件扩展到完整 AND/OR 和规则管理接口。
- 管线 HTTP API 暴露（`POST /pipeline/run`）。
- 用户反馈闭环：记录点击/忽略行为，反哺 RelevanceScorer。
- 增加 Web 控制台、多用户和多渠道通知。

## 关键文件
- [main.py](crypto_monitor/main.py) — 原始主入口（含 `--pipeline` 集成）
- [pipeline_main.py](crypto_monitor/pipeline_main.py) — 管线独立入口
- [pipeline/__init__.py](crypto_monitor/pipeline/__init__.py) — 管线包入口
- [pipeline/models.py](crypto_monitor/pipeline/models.py) — ContentItem / UserProfile / PipelineContext
- [pipeline/base.py](crypto_monitor/pipeline/base.py) — 各层抽象基类
- [pipeline/orchestrator.py](crypto_monitor/pipeline/orchestrator.py) — 管线编排器
- [pipeline/factory.py](crypto_monitor/pipeline/factory.py) — 默认管线工厂
- [pipeline/query_hydration/](crypto_monitor/pipeline/query_hydration/) — 查询扩展层
- [pipeline/sources/](crypto_monitor/pipeline/sources/) — 数据源层（7个）
- [pipeline/hydrators/](crypto_monitor/pipeline/hydrators/) — 元数据补充层（5个）
- [pipeline/filters/](crypto_monitor/pipeline/filters/) — 过滤层（4个）
- [pipeline/scorers/](crypto_monitor/pipeline/scorers/) — 打分层（4个）
- [pipeline/selectors/](crypto_monitor/pipeline/selectors/) — 选择混排层（2个）
- [pipeline/side_effects/](crypto_monitor/pipeline/side_effects/) — 副作用层（3个）
- [monitor.py](crypto_monitor/monitor.py) — 原始监控引擎
- [config.py](crypto_monitor/config.py) / [config.yaml](crypto_monitor/config.yaml)
- [storage.py](crypto_monitor/storage.py) / [notifier.py](crypto_monitor/notifier.py)
- [onchain.py](crypto_monitor/onchain.py) / [binance.py](crypto_monitor/binance.py) / [ar_strategy.py](crypto_monitor/ar_strategy.py)

## 架构图

```
用户请求 / 定时触发
        ↓
┌─────────────────────────────────────────────────────────┐
│  Query Hydration: 加载用户画像、解析 symbols             │
├─────────────────────────────────────────────────────────┤
│  Sources (并发): Market | Onchain | Twitter | News |    │
│                  KOL | YouTube | Reddit                  │
├─────────────────────────────────────────────────────────┤
│  Hydrators (顺序): Price → Volume → Sentiment →        │
│                     Project → RiskTag                    │
├─────────────────────────────────────────────────────────┤
│  Filters (顺序): Duplicate → Scam → Stale → LowCred   │
├─────────────────────────────────────────────────────────┤
│  Scorers (并发): Hotness | Credibility | Impact |       │
│                   Relevance                              │
├─────────────────────────────────────────────────────────┤
│  Selector/Blender: 加权综合 + 多样性混排                 │
├─────────────────────────────────────────────────────────┤
│  Side Effects (并发): Telegram | Storage | Report       │
└─────────────────────────────────────────────────────────┘
        ↓
   PipelineResult (推荐列表)
```

## 注意事项
- `.env`、日志、`__pycache__`、`.venv`、数据库文件不要重新提交进 Git。
- 目前项目是 Python 单体，重写成 Java/Spring Boot 不是当前优先级。
- AR 策略当前只输出信号，不自动下单；执行层必须先做回测、模拟盘、仓位上限和人工确认开关。
- 管线各 Source 当前为骨架实现（返回空列表或模拟数据），需逐个接入真实 API。
- 运行管线：`cd crypto_monitor && source .venv/bin/activate && python pipeline_main.py --query "BTC"`
- 如果要跨电脑继续做，先 `git pull` 同步代码，再让 AI 读取这份摘要。
