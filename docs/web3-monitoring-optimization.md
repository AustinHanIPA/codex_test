# Web3 监控方案调研与项目优化方向

更新时间：2026-04-23

## 1. 调研目的

本文档基于当前代码实现，结合当前主流 Web3 监控方案，分析该项目下一阶段最值得投入的优化方向。

## 2. 当前主流方案的能力画像

## 2.1 主流方案一：节点/链上基础设施的推模式监控

代表方案：

- Helius Webhooks / WebSockets
- QuickNode Webhooks / Streams
- Alchemy Webhooks

### 这些方案的共同特点

1. 从“轮询”转向“推送”
2. 支持实时事件触发
3. 强调可靠投递
4. 支持过滤和变换
5. 支持更好的运维能力

### 关键调研结论

#### Helius

- Webhooks 面向 Solana 链上事件实时通知
- WebSockets 提供持久连接和更低延迟
- 文档明确提示可能出现重试和重复事件
- 对持续失败的 Webhook 有自动禁用机制

来源：

- [Helius Webhooks](https://www.helius.dev/docs/webhooks)
- [Helius WebSockets](https://www.helius.dev/docs/rpc/websocket)

#### QuickNode

- Webhooks 提供模板化事件监控、重试、压缩和 reorg handling
- Streams 支持实时 + 历史 backfill
- Streams 支持服务端 JavaScript 过滤
- Streams 强调 finality order 和 exactly-once delivery

来源：

- [QuickNode Webhooks](https://www.quicknode.com/docs/webhooks)
- [QuickNode Streams](https://www.quicknode.com/docs/streams)

#### Alchemy

- Webhooks 面向地址活动、合约事件、NFT 活动和自定义事件
- 支持多链
- 强调 at-least-once delivery
- 提供签名校验、静态 IP、可编程创建

来源：

- [Alchemy Webhooks Overview](https://www.alchemy.com/docs/reference/webhooks-overview)
- [Alchemy Webhooks Product Page](https://www.alchemy.com/webhooks)

## 2.2 主流方案二：市场数据与 DEX 聚合监控

代表方案：

- Birdeye
- DEX Screener

### 关键调研结论

#### Birdeye

- 提供实时 WebSocket
- 支持价格、交易、OHLCV、钱包跟踪
- 明确了连接上限与 ping-pong 要求

来源：

- [Birdeye WebSocket Docs](https://docs.birdeye.so/docs/websocket)

#### DEX Screener

- 提供代币、交易对、流动性、FDV、marketCap 等查询 API
- 官方说明其核心数据来自自建实时链上索引器

来源：

- [DEX Screener API Reference](https://docs.dexscreener.com/api/reference)
- [DEX Screener FAQ](https://docs.dexscreener.com/)

## 2.3 主流方案三：用户侧告警与策略触发

代表方案：

- TradingView Alerts

### 关键调研结论

- 告警运行在服务端
- 支持价格、技术指标、图形、策略脚本、watchlist alert
- 适合做用户层触发与策略表达

来源：

- [TradingView Alerts Introduction](https://www.tradingview.com/support/solutions/43000520149-introduction-to-tradingview-alerts/)

## 3. 从主流方案抽出的行业共识

从这些主流方案看，当前 Web3 监控产品基本都在向以下方向收敛：

1. Push First
   - 核心监控不再依赖频繁轮询，而是优先 Webhook / WebSocket / Stream

2. Real-time + Historical
   - 不仅要实时，还要支持回放和历史回填

3. Server-side Filtering
   - 尽量在上游完成过滤和预处理，减少本地资源消耗

4. Reliability by Design
   - 重试、去重、reorg handling、投递状态、签名校验都是标配

5. Multi-source Fusion
   - 价格、链上地址、合约事件、流动性、社交信号逐步融合

6. Event-driven Product
   - 输出不只是“原始数据”，而是“可用事件”和“可执行动作”

## 4. 当前项目与主流方案的差距

## 4.1 优势

1. 代码已经有清晰编排中心
2. 已有状态恢复
3. 已有 AI 层和通知层
4. 已有最小本地 HTTP 服务

## 4.2 差距

1. 数据接入方式仍以轮询为主
2. 监控信号主要是价格，没有链上事件维度
3. 没有历史 backfill 和 replay
4. 没有去重和告警幂等模型
5. 没有上游过滤能力
6. 没有用户级策略表达能力
7. 没有正式控制台和配置中心

## 5. 面向该项目的优化方向

以下方向不是泛泛建议，而是结合当前项目现状和主流方案能力提炼出来的。

## 5.1 P0：从单一价格轮询升级为多源监控

### 目标

让系统不再只盯中心化交易对价格，而是同时理解：

- DEX 价格
- 池子流动性
- 大额交易
- 钱包异动

### 建议动作

1. 保留当前价格轮询作为兜底
2. 接入 Birdeye WebSocket 用于价格和交易流
3. 接入 DEX Screener API 用于 token/pair/liquidity 补充信息
4. 统一抽象 `MarketEvent` / `OnchainEvent`

### 原因

主流方案都在做多源融合。如果只监控中心化价格，会错过很多链上先行信号。

## 5.2 P0：引入 Push 模式事件采集

### 目标

把核心信号从“定时轮询”升级为“实时推送”。

### 建议动作

1. Solana 钱包/程序事件接入 Helius Webhooks 或 WebSockets
2. 面向 EVM 链扩展时，接入 Alchemy Webhooks 或 QuickNode Webhooks
3. 为所有推送事件增加：
   - 事件 ID
   - 去重
   - 重试可见性

### 原因

主流方案在链上监控领域已经证明：推模式比高频轮询更低延迟、更省资源，也更容易产品化。

## 5.3 P0：把 AI 从“吐槽文案”升级为“事件摘要引擎”

### 目标

让 AI 不只输出一句情绪化评论，而是输出结构化事件理解。

### 建议动作

把 `AIInsight` 扩展为：

- `comment`
- `sentiment`
- `risk_hint`
- `event_type`
- `confidence`
- `suggested_action`

### 原因

主流监控产品的竞争力不在“能不能发消息”，而在“能不能把复杂事件压缩成判断”。

## 5.4 P1：建立规则引擎

### 目标

让告警从硬编码阈值升级为策略系统。

### 建议动作

1. 抽象规则：
   - 价格变化
   - 成交额变化
   - 流动性变化
   - 钱包转账
   - 合约事件

2. 支持组合条件：
   - 5 分钟涨幅 > X
   - 且成交额 > Y
   - 且买单占比 > Z

3. 支持 watchlist 级规则和 token 级规则

### 原因

TradingView 类产品的启发很明确：真正有价值的是策略表达能力，而不是固定条件。

## 5.5 P1：增加历史回放与复盘

### 目标

让系统具备“为什么发这条告警”的可解释性。

### 建议动作

1. 为关键事件保存标准化事件日志
2. 增加事件回放接口
3. 增加日报/周报
4. 增加热点币种和高价值告警列表

### 原因

QuickNode Streams 强调 backfill，行业已经证明：没有历史回放，监控系统很难向平台化演进。

## 5.6 P1：增强可靠性体系

### 目标

把当前轻量可运行系统升级为更稳健的服务。

### 建议动作

1. 事件幂等键
2. 告警去重
3. 投递状态记录
4. 请求签名校验
5. 指标监控
6. 死信重试机制

### 原因

Alchemy、QuickNode、Helius 都把“可靠投递”当作核心卖点。这不是锦上添花，而是监控系统的基础能力。

## 5.7 P2：从机器人升级为平台

### 目标

形成真正可运营的监控产品。

### 建议动作

1. 增加 Web 控制台
2. 增加用户/租户体系
3. 支持自定义监控名单
4. 支持多个通知渠道
5. 增加权限、订阅和商业化能力

### 原因

当前项目更像单用户机器人。要变成产品，控制面必须独立出来。

## 6. 推荐的目标架构

```text
Push Sources / Pull Sources
   |   \
   |    \--> WebSocket / Webhook / REST Polling
   v
Event Ingestion Layer
   v
Normalization Layer
   v
Rule Engine
   v
AI Insight Layer
   v
Notification Layer
   v
Storage + Reporting + Control Plane
```

## 7. 建议实施顺序

### 第一阶段：2 周

1. 接入第二市场数据源
2. 抽象标准事件模型
3. 扩展 AIInsight 字段
4. 补充告警幂等

### 第二阶段：4 周

1. 接入 Birdeye WebSocket
2. 接入 Helius Webhooks / WebSockets
3. 建立规则引擎
4. 增加日报生成

### 第三阶段：6-8 周

1. 搭建 Web 控制台
2. 增加用户配置 API
3. 增加多通知渠道
4. 增加回放与复盘系统

## 8. 最终判断

这个项目最值得继续走的方向，不是简单把轮询频率调高，也不是只继续润色 AI 文案，而是向以下三点收敛：

1. 多源实时事件系统
2. 规则驱动告警系统
3. AI 增强解释与复盘系统

这也是当前主流 Web3 监控方案真正形成壁垒的地方。
