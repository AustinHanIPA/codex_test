# api-doc-inspect 架构分析与 aiCode 优化方向

更新时间：2026-04-24

## 1. 结论

`api-doc-inspect` 对 `aiCode/crypto_monitor` 最有价值的启发，不是某个具体工具，而是它的工作流形态：

1. 输入、分析、输出分层清晰。
2. 中间产物结构化。
3. 模型输出不可信时有解析兜底。
4. 结果可落盘、可复查、可继续消费。
5. 最终输出面向人阅读，而不是只停在脚本日志。

这些原则已经逐步迁移到当前项目。

## 2. 对当前项目的启发

当前 `crypto_monitor` 已经不是单一脚本，而是一个结构化监控服务：

- 市场输入：`market.py`
- 链上输入：`onchain.py`
- 领域模型：`models.py`
- 规则判断：`rules.py`
- AI 分析：`ai_service.py`
- 通知输出：`notifier.py`
- 数据落盘：`storage.py`
- 报告输出：`reporting.py`
- 编排中心：`monitor.py`
- 服务入口：`main.py`

这与 `api-doc-inspect` 的启发高度一致：每一步都产生稳定对象，后续模块消费对象，而不是互相传递不可控字符串。

## 3. 已落地能力

### 3.1 结构化领域模型

已通过 `models.py` 抽象：

- `MarketSnapshot`
- `OnchainEvent`
- `AIInsight`
- `PriceState`

价值：

- 市场、链上、AI、状态不再混在临时字典里。
- 后续接 DEX、钱包、社交数据时有稳定扩展点。

### 3.2 模型输出结构化和兜底

`ai_service.py` 已支持：

- 要求 Gemini 输出 JSON。
- 解析 `comment/sentiment/event_type/risk_hint/suggested_action/confidence`。
- 支持 fenced JSON。
- 非 JSON 时取首行文本兜底。
- AI 未配置或失败时返回默认 `AIInsight`。

这对应 `api-doc-inspect` 的 parser 思路：模型输出可以增强系统，但不能成为系统稳定性的单点。

### 3.3 数据源归一化

`market.py` 已将市场数据归一化为 `MarketSnapshot`。

`onchain.py` 已将 Helius/QuickNode 常见 webhook payload 归一化为 `OnchainEvent`：

- 支持单条和批量。
- 支持 `tokenTransfers`。
- 支持 `data/events/transactions` 包装。
- 支持事件别名映射。

### 3.4 规则引擎

`rules.py` 已提供 `RuleEngine`：

- 价格阈值判断。
- 市值和成交额过滤。
- 巨鲸转账判断。
- 追踪地址判断。
- 输出 `RuleDecision`。

这让告警判断从 `if/else` 变成可继续扩展的独立层。

### 3.5 报告层

`reporting.py` 已生成 Markdown 日报：

- 汇总市场告警。
- 汇总链上事件。
- 支持 `major_only` 过滤。
- 保存到本地 `reports/`。
- 保存到 SQLite。
- 可通过 Telegram 推送。

这一步把项目从“只发实时消息”推进到“可复盘的监控产品”。

## 4. 当前代码链路

```text
Market / Webhook Payload
        |
        v
Normalization
        |
        v
MarketSnapshot / OnchainEvent
        |
        v
RuleEngine
        |
        v
AIInsight
        |
        v
Telegram + SQLite + Markdown Report
```

## 5. 与 api-doc-inspect 的对应关系

| api-doc-inspect 思路 | crypto_monitor 当前实现 |
| --- | --- |
| 文档抓取 | `market.py` / `onchain.py` |
| 结构化分析 | `rules.py` / `ai_service.py` |
| 解析兜底 | `_parse_insight()` |
| 中间产物落盘 | `storage.py` |
| 人类可读报告 | `reporting.py` |
| 可单跑入口 | CLI / HTTP 接口 |

## 6. 后续优化方向

### 6.1 结果缓存

为 AI 洞察增加缓存键：

- `symbol`
- `event_type`
- `rule_level`
- `event_id`
- 时间窗口

目标是减少重复调用模型，降低成本和延迟。

### 6.2 事件幂等

在处理 webhook 前检查 `event_id` 是否已经存在，避免 provider 重试造成重复告警。

### 6.3 报告增强

将当前 Markdown 日报扩展为：

- Telegram 精简版。
- Notion 完整版。
- HTML 归档版。

### 6.4 规则配置化

把当前 `RuleEngine` 中的代码规则迁移到配置：

- 阈值。
- AND/OR 条件。
- watchlist 级规则。
- token 级规则。

### 6.5 多数据源 provider

继续按 `onchain.py` 的思路扩展：

- Helius provider。
- QuickNode provider。
- DEX Screener provider。
- Birdeye WebSocket provider。

## 7. 最终判断

`api-doc-inspect` 的核心价值已经被迁移成当前项目的几个关键方向：结构化、兜底解析、可落盘、可复盘、可扩展。下一轮最值得投入的是事件幂等、provider 级安全校验、AI 缓存和规则配置化。
