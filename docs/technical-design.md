# Crypto Monitor 技术设计文档

更新时间：2026-04-24

## 1. 设计目标

当前系统目标是以较小的 Python 单体实现一个可长期演进的 Web3 多源监控服务。设计重点是：

1. 保留轻量部署和快速迭代能力。
2. 用结构化模型串联市场数据、链上事件、规则判断、AI 洞察、通知和报告。
3. 让后续接入 Helius、QuickNode、Birdeye、DEX Screener、Notion 时尽量只扩展对应模块。

## 2. 技术栈

- 语言：Python 3
- 异步运行：`asyncio`
- HTTP 客户端：`aiohttp`
- 本地 HTTP 服务：`aiohttp.web`
- 存储：`SQLite + aiosqlite`
- AI：Gemini 兼容接口
- 通知：Telegram Bot API
- 配置：YAML + `.env`
- 日志：`logging` + `RotatingFileHandler`
- 测试：`unittest`

## 3. 模块结构

### 3.1 入口层

- `crypto_monitor/main.py`

职责：

- 解析 CLI 参数。
- 初始化配置。
- 启动 `MonitorEngine`。
- 启动本地 HTTP 服务。
- 注册健康检查、状态查询、链上 webhook、日报接口。

### 3.2 应用编排层

- `crypto_monitor/monitor.py`

职责：

- 编排价格监控主循环。
- 调用规则引擎。
- 调用 AI 服务生成洞察。
- 发送 Telegram 通知。
- 写入存储。
- 处理链上 webhook。
- 生成和推送日报。
- 维护健康检查和资源清理。

### 3.3 领域层

- `crypto_monitor/models.py`
- `crypto_monitor/rules.py`

核心模型：

- `MarketSnapshot`
- `OnchainEvent`
- `AIInsight`
- `PriceState`
- `RuleDecision`

规则能力：

- 价格涨跌幅三级判断。
- 市值和 24h 成交额过滤。
- 链上巨鲸转账判断。
- 追踪地址活动判断。
- 输出规则原因和标签。

### 3.4 数据接入层

- `crypto_monitor/market.py`
- `crypto_monitor/onchain.py`

`market.py` 负责：

- 抓取市场价格。
- 重试和超时控制。
- 归一化为 `MarketSnapshot`。

`onchain.py` 负责：

- 接收单条或批量 payload。
- 兼容 Helius 风格 `tokenTransfers`。
- 兼容 QuickNode 风格包装结构。
- 归一化为 `OnchainEvent`。

### 3.5 AI 层

- `crypto_monitor/ai_service.py`

职责：

- 渲染价格事件 prompt。
- 渲染链上事件 prompt。
- 要求模型输出 JSON。
- 解析 `comment/sentiment/event_type/risk_hint/suggested_action/confidence`。
- 对非 JSON 输出进行兜底。
- 对模型未配置或请求失败进行降级。

### 3.6 通知层

- `crypto_monitor/notifier.py`

职责：

- Telegram 异步发送。
- 价格告警通知。
- 链上事件通知。
- 健康检查通知。
- 日报推送。
- 总量和目标级限流。

### 3.7 存储层

- `crypto_monitor/storage.py`

职责：

- 初始化 SQLite 表。
- 自动补充 `alerts` 扩展字段。
- 保存价格、告警、状态、监控名单、链上事件、报告。
- 查询告警历史和链上事件。
- 清理过期数据。

### 3.8 报告层

- `crypto_monitor/reporting.py`

职责：

- 查询近期市场告警和链上事件。
- 按配置过滤高价值事件。
- 生成 Markdown 日报。
- 写入本地 `reports/`。
- 保存报告记录到 SQLite。

## 4. 当前架构

```text
CLI / HTTP API
      |
      v
MonitorEngine
      |
      +--> MarketDataFetcher ----> MarketSnapshot
      |
      +--> OnchainAdapter -------> OnchainEvent
      |
      +--> RuleEngine -----------> RuleDecision
      |
      +--> AIService ------------> AIInsight
      |
      +--> Notifier -------------> Telegram
      |
      +--> Storage --------------> SQLite
      |
      +--> ReportService --------> Markdown + SQLite
```

## 5. 核心流程

### 5.1 价格监控流程

1. `run_forever()` 按 `monitor.interval` 调用 `run_once()`。
2. `check_prices()` 调用 `market.py` 获取行情。
3. 按监控名单筛选交易对。
4. `PriceState` 计算相邻采样涨跌幅。
5. `RuleEngine.evaluate_market()` 判断是否满足告警条件。
6. 保存价格历史。
7. `process_alert()` 调用 AI 生成结构化洞察。
8. Telegram 发送价格告警。
9. SQLite 保存告警和状态。

### 5.2 链上事件流程

1. 外部 provider 调用 `POST /webhooks/onchain`。
2. `main.py` 做 token 校验和 JSON 解析。
3. `MonitorEngine.process_onchain_payload()` 接收 payload。
4. `onchain.py` 将 provider payload 归一化为 `OnchainEvent`。
5. `RuleEngine.evaluate_onchain()` 判断巨鲸转账或追踪地址活动。
6. AI 生成链上事件洞察。
7. Telegram 发送链上事件告警。
8. SQLite 保存原始事件、规则结果和 AI 输出。

### 5.3 日报流程

1. 手动调用 `POST /reports/daily`，或主循环根据 `reporting.auto_send` 自动触发。
2. `ReportService` 查询近期告警和链上事件。
3. 按 `reporting.major_only` 过滤。
4. 生成 Markdown。
5. 写入 `reports/` 并保存到 `reports` 表。
6. 如果 `send=true` 或自动发送开启，则推送到 Telegram。

## 6. HTTP 接口

默认监听：

- `0.0.0.0:28593`

接口：

- `GET /`
  - 返回服务名称、状态和接口列表。

- `GET /health`
  - 返回运行状态、暂停状态、失败次数、最近成功时间。

- `GET /status`
  - 返回监控名单、运行状态、失败次数、启动时间。

- `POST /webhooks/onchain`
  - 接收链上事件。
  - 支持 query：`source=helius|quicknode|webhook`
  - 支持鉴权：`X-Webhook-Token` 或 `?token=...`

- `POST /reports/daily`
  - 生成日报。
  - 支持 query：`hours=24`
  - 支持 query：`send=true`

## 7. 配置结构

主要配置段：

- `monitor`
- `market`
- `ai`
- `notification`
- `storage`
- `logging`
- `health_check`
- `onchain`
- `reporting`
- `service`

新增重点配置：

- `onchain.enabled`
- `onchain.tracked_addresses`
- `onchain.whale_transfer_threshold_usd`
- `onchain.webhook_auth_token`
- `reporting.enabled`
- `reporting.output_dir`
- `reporting.default_lookback_hours`
- `reporting.major_only`
- `reporting.auto_send`
- `reporting.daily_hour`
- `service.port`

## 8. 数据库设计

### 8.1 `price_history`

保存价格采样记录：

- `symbol`
- `price`
- `change_percent`
- `timestamp`

### 8.2 `alerts`

保存价格告警和 AI 结构化结果：

- `symbol`
- `price`
- `change_percent`
- `alert_level`
- `ai_comment`
- `sentiment`
- `event_type`
- `risk_hint`
- `suggested_action`
- `confidence`
- `rule_reasons`
- `rule_tags`
- `telegram_message_id`
- `sent_at`

### 8.3 `symbol_state`

保存运行状态：

- `symbol`
- `last_price`
- `last_alert_time`
- `updated_at`

### 8.4 `watchlist_symbols`

保存监控名单：

- `symbol`
- `created_at`

### 8.5 `onchain_events`

保存链上事件：

- `event_id`
- `source`
- `event_type`
- `symbol`
- `address`
- `counterparty`
- `amount`
- `amount_usd`
- `direction`
- `tx_signature`
- `description`
- `rule_level`
- `rule_reasons`
- `rule_tags`
- `ai_comment`
- `sentiment`
- `risk_hint`
- `suggested_action`
- `confidence`
- `observed_at`
- `raw`

### 8.6 `reports`

保存报告：

- `report_type`
- `title`
- `content`
- `lookback_hours`
- `generated_at`

## 9. Schema 迁移说明

当前没有独立 migration 框架，采用启动时自动建表和补列：

- `CREATE TABLE IF NOT EXISTS` 创建新表。
- `PRAGMA table_info(alerts)` 检查旧表字段。
- 缺失字段通过 `ALTER TABLE alerts ADD COLUMN` 补齐。

本轮自动扩展包括：

- `alerts` 新增结构化 AI 字段和规则字段。
- 新增 `onchain_events` 表。
- 新增 `reports` 表。

## 10. 可靠性设计

已实现：

- 市场抓取重试。
- Telegram 异步发送和重试。
- 通知限流。
- AI JSON 解析兜底。
- 数据库自动建表和轻量迁移。
- 监控名单和价格状态恢复。
- 健康检查和轻量自恢复。
- webhook token 校验。

仍需补齐：

- webhook 签名校验。
- 事件幂等和重复投递去重。
- Telegram 投递状态落库。
- 死信队列或失败重放。
- Prometheus 指标。

## 11. 测试设计

当前测试覆盖：

- AI JSON 和文本兜底解析。
- 市场快照归一化。
- 规则引擎市场和链上判断。
- Helius/QuickNode payload 归一化。
- 监控名单持久化。
- 批量价格写入。
- 链上事件存储。
- 日报生成。

推荐继续补充：

- `MonitorEngine` 主流程 mock 测试。
- webhook 鉴权测试。
- 通知失败降级测试。
- 自动日报调度测试。

## 12. 演进建议

### Step 1：事件可靠性

- `event_id` 去重。
- webhook 签名校验。
- 投递结果持久化。

### Step 2：多数据源

- 接入 Helius 真实 webhook 配置。
- 接入 QuickNode Streams。
- 接入 DEX Screener / Birdeye。

### Step 3：产品化控制面

- 管理 API。
- Web 控制台。
- 规则配置界面。
- 多通知渠道。

## 13. 结论

当前项目已经具备“价格监控 + 链上 webhook + 规则引擎 + AI 洞察 + Telegram + SQLite + 日报”的最小闭环。下一阶段不需要推翻重写，重点应放在事件可靠性、多源数据接入和规则配置化上。
