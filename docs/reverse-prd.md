# Crypto Monitor 反向需求文档

更新时间：2026-04-24

## 1. 文档目标

本文档基于当前代码实现反向抽取产品需求，用于帮助后续开发保持同一个方向：

1. 明确系统当前已经具备的能力。
2. 明确下一阶段产品化应该补齐的能力。
3. 把需求拆成可验证、可落地的功能边界。

当前分析范围覆盖：

- `crypto_monitor/main.py`
- `crypto_monitor/monitor.py`
- `crypto_monitor/market.py`
- `crypto_monitor/binance.py`
- `crypto_monitor/ar_strategy.py`
- `crypto_monitor/onchain.py`
- `crypto_monitor/rules.py`
- `crypto_monitor/ai_service.py`
- `crypto_monitor/notifier.py`
- `crypto_monitor/storage.py`
- `crypto_monitor/reporting.py`
- `crypto_monitor/models.py`
- `crypto_monitor/config.py`

## 2. 产品定位

### 2.1 一句话定义

`Crypto Monitor` 是一个面向 Web3 交易者和社群运营者的多源事件监控系统，将价格波动、链上事件、规则判断和 AI 解读转化为实时告警与日报复盘。

### 2.2 当前阶段定位

当前项目已经从“价格轮询机器人”演进为“轻量多源监控服务”：

- 价格数据仍以 REST 轮询为主。
- AR/AO 专用策略已接入 Binance K 线数据和五层策略信号。
- 链上事件通过 webhook/push 入口接入。
- 告警判断从硬编码阈值演进为 `RuleEngine`。
- AI 输出从短文本升级为结构化 `AIInsight`。
- 存储层开始沉淀价格、告警、链上事件和报告。
- 本地 HTTP 服务提供健康检查、状态查询、链上事件接入和日报触发。

### 2.3 目标用户

1. 个人交易者：希望减少盯盘时间，快速识别价格和链上异动。
2. Web3 社群运营者：希望把监控结果包装成群通知、日报和复盘内容。
3. 策略研究者：希望积累事件数据，用于后续回放、复盘和规则优化。
4. 运维者：希望服务能长期稳定运行，并具备可观测和可恢复能力。

## 3. 当前已实现需求

### 3.1 监控名单管理

系统应支持：

- 通过配置文件初始化监控币种。
- 通过 CLI 添加和移除监控币种。
- 将监控名单持久化到 SQLite。
- 重启后恢复监控名单。

### 3.2 价格监控

系统应支持：

- 定时抓取市场价格。
- 将原始市场数据归一化为 `MarketSnapshot`。
- 计算相对上次采样的涨跌幅。
- 保存价格历史。
- 在触发规则后进入告警链路。

### 3.3 规则判断

系统应支持：

- 使用 `RuleEngine` 统一判断价格和链上事件。
- 基于 `minor/moderate/major` 三级阈值判断价格异动。
- 支持最小市值、最小 24h 成交额等过滤条件。
- 支持巨鲸转账阈值判断。
- 支持 `config.yaml` 中的 `rules.market` 和 `rules.onchain` 配置化规则。
- 输出规则原因 `rule_reasons` 和规则标签 `rule_tags`。
- 输出命中的规则 ID `matched_rules`。

### 3.4 AR/AO 策略监控

系统应支持：

- 通过 Binance `/api/v3/klines` 分页抓取历史 K 线。
- 支持 Binance 官方地址和 Nginx 代理池地址。
- 默认分析 `ARUSDT` 周线。
- 计算 MA7、MA25、MACD、RSI、Bollinger Band 宽度。
- 识别 MA 趋势、MACD 动能、关键阻力位突破和趋势内超卖回调。
- 输出 `BUY_STEP_IN`、`WATCH_BUY`、`NEUTRAL`、`RISK_OFF` 或 `INSUFFICIENT_DATA`。
- 通过 `GET /strategies/ar` 查询策略信号。
- 通过 `python crypto_monitor/main.py --ar-signal` 本地输出策略信号。

### 3.5 链上事件接入

系统应支持：

- `POST /webhooks/onchain` 接收链上事件。
- 支持单条或批量 payload。
- 支持 Helius 风格 `tokenTransfers`。
- 支持 QuickNode 风格 `data/events/transactions` 包装。
- 将事件归一化为 `OnchainEvent`。
- 支持 webhook token 校验。
- 支持 HMAC-SHA256 webhook 签名校验。
- 支持基于 `event_id` 的重复事件跳过。
- 保存链上事件及规则判断结果。

### 3.6 AI 洞察

系统应支持：

- 调用 Gemini 兼容接口生成结构化分析。
- 对价格告警生成 AI 洞察。
- 对链上事件生成 AI 洞察。
- 当模型未配置或调用失败时使用默认降级评论。
- 解析并保存以下字段：
  - `comment`
  - `sentiment`
  - `event_type`
  - `risk_hint`
  - `suggested_action`
  - `confidence`

### 3.7 通知能力

系统应支持：

- Telegram 异步发送。
- 价格告警通知。
- 链上事件告警通知。
- 健康检查通知。
- 日报内容推送。
- 通知投递结果记录。
- 总量限流和同目标冷却。

### 3.8 存储能力

系统应保存：

- 价格历史 `price_history`
- 告警历史 `alerts`
- 运行状态 `symbol_state`
- 监控名单 `watchlist_symbols`
- 链上事件 `onchain_events`
- 报告记录 `reports`
- 通知投递记录 `notification_deliveries`

### 3.9 报告能力

系统应支持：

- 生成 Markdown 日报。
- 汇总市场告警和链上事件。
- 汇总通知投递失败。
- 按 `major_only` 过滤高价值事件。
- 通过 `POST /reports/daily` 手动生成日报。
- 通过 `POST /reports/daily?send=true` 生成并推送日报。
- 按 `reporting.auto_send` 和 `reporting.daily_hour` 自动生成并推送。

### 3.9 运维接口

本地服务监听默认端口 `28593`，应提供：

- `GET /`
- `GET /health`
- `GET /status`
- `GET /statistics`
- `GET /watchlist`
- `POST /watchlist`
- `DELETE /watchlist/{symbol}`
- `GET /alerts`
- `GET /events/onchain`
- `GET /notifications`
- `POST /control/pause`
- `POST /control/resume`
- `POST /webhooks/onchain`
- `POST /reports/daily`
- `GET /strategies/ar`

## 4. 用户故事

### 4.1 交易者

1. 作为交易者，我希望在价格出现显著波动时收到即时通知。
2. 作为交易者，我希望链上巨鲸转账也能触发告警。
3. 作为交易者，我希望告警里包含风险提示和建议动作。
4. 作为交易者，我希望系统避免同一币种在短时间内重复刷屏。
5. 作为 AR 交易者，我希望系统基于 AO 叙事、周线趋势和回调指标给出分批建仓信号。

### 4.2 社群运营者

1. 作为运营者，我希望每天自动生成高价值事件日报。
2. 作为运营者，我希望日报可以直接推送到 Telegram。
3. 作为运营者，我希望未来能接入 Notion 或 Web 控制台。

### 4.3 运维者

1. 作为运维者，我希望服务有健康检查接口。
2. 作为运维者，我希望重启后恢复监控名单和价格状态。
3. 作为运维者，我希望外部 webhook 有 token 和签名校验。
4. 作为运维者，我希望日志、数据库、报告产物不会误提交到 Git。
5. 作为运维者，我希望增删监控名单、暂停和恢复服务可以通过本地 HTTP 控制面完成。

## 5. 非功能需求

### 5.1 稳定性

- 外部请求失败时应有重试或降级。
- 模型输出异常时应能兜底解析。
- 数据库 schema 扩展应自动完成。
- 主循环异常不应导致服务静默退出。

### 5.2 性能

- 单轮价格检查应在监控间隔内完成。
- 价格写入应批量提交。
- 通知发送不应阻塞市场抓取链路太久。
- webhook 批量事件应逐条归一化和持久化。

### 5.3 可扩展性

- 新增链上 provider 时应优先扩展 `onchain.py`。
- 新增规则时应优先扩展 `rules.py`。
- 新增报告输出渠道时应复用 `reporting.py` 的 Markdown 内容。
- 新增 AI provider 时应避免改动 `MonitorEngine` 主流程。

## 6. 当前未完成需求

1. AR 策略尚未接入 AO 网络存储量、GitHub 活跃度和社媒权重。
2. AR 策略尚未接入资金费率、盘口深度和真实执行层。
3. Notion 日报未接入。
4. WebSocket/Streams 模式未接入。
5. 规则仍是轻量配置，还没有完整 AND/OR DSL 和规则管理界面。
6. Web 控制台、用户体系和多租户未实现。
7. 失败通知还没有重试队列和死信处理。
8. 历史回放、回测和告警质量评估未实现。

## 7. 优先级建议

### P0

- 失败投递重试和死信列表。
- 真实 Helius/QuickNode webhook 样本适配。
- DEX Screener / Birdeye 第二数据源。
- Notion 日报。

### P1

- 规则 DSL 增强和管理接口。
- 增加事件查询和回放接口。
- 增加告警质量统计。

### P2

- Web 控制台。
- 多用户与租户隔离。
- 策略回测。
- 订阅和商业化能力。

## 8. 成功指标

- 告警延迟：链上事件到 Telegram 通知尽量控制在秒级。
- 告警质量：重复告警下降，高价值告警占比提升。
- 稳定性：服务可持续运行并自动恢复轻量故障。
- 可复盘性：每个告警都能追溯规则原因、AI 输出和原始事件。
- 产品化：日报、回放、规则配置逐步成为可运营能力。
