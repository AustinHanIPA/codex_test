# Web3 监控方案调研与项目优化方向

更新时间：2026-04-24

## 1. 调研目的

本文档结合当前 `crypto_monitor` 的最新实现，以及主流 Web3 监控方案的能力形态，给出后续优化路线。

当前项目已经具备：

- 价格轮询监控。
- 链上 webhook 入口。
- Helius/QuickNode 常见 payload 归一化。
- 规则引擎。
- 结构化 AI 洞察。
- Telegram 通知。
- SQLite 持久化。
- Markdown 日报。

因此，后续优化重点应从“补功能”转向“提升可靠性、接入真实数据源、增强策略表达”。

## 2. 市面主流方案画像

### 2.1 Helius

典型能力：

- Solana Webhooks。
- WebSockets。
- 地址、交易、程序事件监控。
- 失败重试和 webhook 管理。

对本项目启发：

- 当前 `/webhooks/onchain` 已具备接入基础，并已补 token、HMAC 签名和重复事件跳过。
- 下一步应补真实 payload 完整映射、失败重放和 provider 管理。

### 2.2 QuickNode

典型能力：

- Webhooks。
- Streams。
- 历史 backfill。
- 过滤和转换。
- 更强的投递可靠性设计。

对本项目启发：

- 当前 `onchain.py` 已兼容 `data/events/transactions` 包装。
- 下一步应增加 backfill/replay 思路，避免只处理实时事件。

### 2.3 Alchemy

典型能力：

- 多链 webhook。
- 地址活动、合约事件、NFT 事件。
- at-least-once delivery。
- 签名校验。

对本项目启发：

- 当前只做 token 校验，安全性还偏轻。
- 项目已具备通用 HMAC 签名校验和事件幂等入口，后续应补 provider 原生签名规则。

### 2.4 Birdeye

典型能力：

- WebSocket 实时价格。
- 交易流。
- OHLCV。
- 钱包跟踪。

对本项目启发：

- 当前市场价格还是 REST 轮询。
- 下一步可接 WebSocket，把价格侧也从 pull 推进到 push。

### 2.5 DEX Screener

典型能力：

- token/pair/liquidity/FDV/marketCap API。
- DEX 交易对发现。
- 池子流动性数据。

对本项目启发：

- 当前 `MarketSnapshot` 已预留 `market_cap`、`volume_24h`、`liquidity_usd`。
- 可作为第二市场数据源补齐小币种市值、流动性和 DEX 维度。

### 2.6 TradingView Alerts

典型能力：

- 策略化告警。
- 服务端运行。
- 价格、指标、图形、脚本组合触发。

对本项目启发：

- 当前已有 `RuleEngine` 和 `rules.market` / `rules.onchain` 配置。
- 下一步应做更完整的 AND/OR DSL、规则管理接口和规则回测。

## 3. 行业共识

主流 Web3 监控产品基本都在向以下方向收敛：

1. Push First
   - Webhook、WebSocket、Streams 优先，REST 轮询作为兜底。

2. Multi-source Fusion
   - 价格、DEX、钱包、链上合约、社交情绪共同判断。

3. Reliability by Design
   - 重试、去重、签名校验、幂等、投递状态不可缺。

4. Rule-driven Alerts
   - 价值来自策略表达，而不是固定阈值。

5. Explainable Events
   - 告警必须能说明为什么触发、风险在哪里、建议动作是什么。

6. Replay and Reporting
   - 实时告警之外，日报、回放和复盘是产品化关键。

## 4. 当前项目状态

### 4.1 已追上主流方向的部分

- 已支持 webhook/push 入口。
- 已有标准链上事件模型 `OnchainEvent`。
- 已有标准 AI 洞察模型 `AIInsight`。
- 已有规则判断模型 `RuleDecision`。
- 已有事件和报告持久化。
- 已有日报生成和 Telegram 推送能力。
- 已有 webhook 签名校验、重复事件跳过和通知投递记录。
- 已有轻量 HTTP 控制面用于监控名单和暂停恢复。

### 4.2 仍存在的差距

- 尚未对接真实 Helius/QuickNode 项目配置。
- 缺少 provider 原生签名规则适配。
- 缺少失败投递重试和死信队列。
- 缺少 backfill/replay。
- 市场数据仍主要依赖单一 REST 源。
- 规则 DSL 还不完整，缺少 Web 管理界面。
- 没有完整 Web 控制台、用户体系和多租户。

## 5. 优化方向

### 5.1 P0：事件可靠性

目标：

- 避免重复 webhook 造成重复告警。
- 避免伪造请求触发通知。
- 记录每次投递结果。

建议动作：

1. 增加失败事件重放入口。
2. 增加 provider 原生签名校验。
3. 将 Telegram 重试次数和最终失败原因落库。
4. 增加死信队列和人工重放接口。

### 5.2 P0：真实 provider 接入

目标：

- 让当前 `/webhooks/onchain` 接入真实数据源。

建议动作：

1. 配置 Helius webhook 指向 `/webhooks/onchain?source=helius`。
2. 配置 QuickNode webhook/stream 指向 `/webhooks/onchain?source=quicknode`。
3. 根据真实样本继续完善 `onchain.py` 字段映射。
4. 为 provider payload 增加 fixture 测试。

### 5.3 P1：市场数据多源化

目标：

- 从 CEX 价格扩展到 DEX 价格、流动性和交易对发现。

建议动作：

1. 增加 DEX Screener provider。
2. 将 `liquidity_usd`、`market_cap`、`volume_24h` 填充到 `MarketSnapshot`。
3. 增加 Birdeye WebSocket 作为实时价格流。
4. 保留现有 REST 轮询作为兜底。

### 5.4 P1：规则配置化

目标：

- 从代码规则升级为用户可配置策略。

建议动作：

1. 在 `config.yaml` 中增加 `rules` 配置段。
2. 支持 AND/OR 组合条件。
3. 支持 watchlist 级规则和 token 级规则。
4. 保存触发规则 ID，便于复盘。

示例规则：

```yaml
rules:
  - id: fomo-major
    level: major
    all:
      - price_change_5m_gt: 10
      - buy_ratio_gt: 70
      - whale_buy_usd_gt: 50000
```

### 5.5 P1：报告产品化

目标：

- 把日报从本地 Markdown 升级为可运营内容。

建议动作：

1. 接入 Notion。
2. 增加 Telegram 精简版日报和 Markdown 完整版日报。
3. 增加日报质量字段：高价值事件数、重复告警数、AI 置信度分布。
4. 增加周报和重大事件复盘。

### 5.6 P2：控制面

目标：

- 从单用户机器人升级为可管理平台。

建议动作：

1. 增加 REST 管理 API。
2. 增加 Web 控制台。
3. 支持用户、租户、策略、通知渠道配置。
4. 增加权限和审计日志。

## 6. 推荐路线图

### 第一阶段：可靠事件闭环

- 失败通知重试。
- 死信列表。
- provider 原生签名适配。
- Helius/QuickNode 真实样本 fixture。

### 第二阶段：多源数据

- DEX Screener provider。
- Birdeye WebSocket。
- 流动性和市值规则。
- 链上事件 backfill。

### 第三阶段：策略和报告

- 规则配置化。
- Notion 日报。
- 历史回放。
- 周报和复盘。

### 第四阶段：平台化

- Web 控制台。
- 多用户。
- 多渠道通知。
- 商业化订阅。

## 7. 当前项目最该优先做的三件事

1. 接入真实 Helius/QuickNode webhook 样本并完善适配器。
2. 增加失败通知重试和死信队列。
3. 把规则 DSL 和控制面做成可运营能力。

## 8. 结论

当前项目方向已经与主流 Web3 监控方案对齐：push 入口、统一事件、签名校验、事件去重、配置化规则、AI 解释、投递审计和报告层都已经出现。下一阶段的竞争力不在于继续加更多提示词，而在于把失败重放、多源数据和策略表达打磨扎实。
