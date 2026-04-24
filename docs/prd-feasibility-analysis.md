# PRD v2.0 需求拆分与可行性分析

更新时间：2026-04-24

## 1. 分析范围

本文基于《加密货币智能监控系统 PRD v2.0》、当前 `crypto_monitor` 代码，以及主流 Web3 工具能力，对需求点进行拆分和可行性评估。

参考的主流工具方向：

- MEXC：中心化交易所价格源
- DEX Screener：DEX pair、流动性、成交额、FDV、市值
- Helius：Solana webhook / wallet activity
- DefiLlama：TVL、费用、收入、DEX volume 等公开 DeFi 指标
- mempool.space：BTC mempool fee / backlog
- Telegram Bot：通知分发
- Gemini：AI 洞察
- Nginx + Docker Compose：GCP 网络堡垒与部署

## 2. 可行性分级

- `>= 80%`：当前项目架构能直接落地，外部依赖少，已整合进项目或本轮实现。
- `60%-79%`：技术可行，但需要真实 API key、付费账号、样本数据或较多产品设计。
- `< 60%`：当前阶段不适合直接接入，容易引入合规、成本、平台权限或维护风险。

## 3. 需求拆分矩阵

| 需求点 | 主流工具/实现 | 可行性 | 判断 | 本轮处理 |
| --- | --- | ---: | --- | --- |
| MEXC 异步价格轮询 | MEXC API + aiohttp | 95% | 已有基础，稳定可控 | 已有 |
| DEX 聚合补充流动性/市值 | DEX Screener tokens API | 90% | 公开 API，无 key，字段契合 `MarketSnapshot` | 已整合 |
| Helius 链上 webhook | Helius Webhooks | 85% | 当前已有通用 webhook、签名、去重；真实样本需继续补 | 已有基础 |
| RSI / Bollinger / MACD | 量化指标库或纯 Python | 90% | 不必强依赖 pandas，MVP 可用纯 Python 实现 | 已整合 |
| Volume Spike | 价格历史 + volume_24h | 85% | 需要保存历史成交额，当前可做近似 | 已整合 |
| AI 结合量化上下文 | Gemini + `AIInsight` | 95% | 已有 context 机制 | 已整合 |
| Telegram 防刷屏 | 时间窗限流 | 95% | 已有 RateLimiter，可按 PRD 调整为 10 分钟 | 已整合 |
| Deep Link / 返佣链接 | Trojan/Banana Gun/PepeBoost link template | 85% | 链接生成可配置，真实合作需线下申请 | 已整合配置 |
| 免费群脱敏展示 | 通知模板 | 85% | 可配置，不影响核心信号 | 已整合配置 |
| Docker 化部署 | Dockerfile + Compose | 90% | 与当前 Python 单体匹配 | 已整合 |
| GCP Nginx 网关 | Nginx reverse proxy | 90% | 配置可落地，真实域名/证书另配 | 已整合 |
| DefiLlama TVL | DefiLlama API | 75% | 公共数据可用，但和 meme 币告警的映射需产品设计 | 暂缓 |
| mempool.space gas/fees | mempool.space API | 75% | BTC fee 信号可接，但与 Solana meme 主场关联弱 | 暂缓 |
| InviteMemberBot 订阅自动化 | InviteMemberBot | 65% | 需要真实 Bot、频道和支付配置 | 暂缓 |
| X/Twitter 自动发帖 | X API | 55% | 权限、风控和内容合规成本较高 | 暂缓 |
| VIP 群完整商业闭环 | Telegram + 支付 + CRM | 60% | 需要运营配置，不应写死在核心代码 | 暂缓 |
| WebSocket K 线 | Birdeye / exchange WS | 70% | 架构可行，但需要长连接生命周期和样本测试 | 暂缓 |
| 每周胜率复盘 | SQLite + AI | 75% | 需要定义命中、止盈止损、时间窗口 | 暂缓 |

## 4. 本轮已整合的 `>=80%` 需求

### 4.1 DEX Screener 市场增强

新增 `dex` 配置段，通过 token address 从 DEX Screener 获取：

- DEX 价格
- 24h 成交额
- 流动性
- FDV / 市值
- pair 原始数据

整合点：

- `crypto_monitor/config.py`
- `crypto_monitor/config.yaml`
- `crypto_monitor/market.py`

### 4.2 量化分析引擎

新增 `quant_engine.py`，输出 `QuantSignal`：

- RSI
- Bollinger Bands position
- MACD / signal
- Volume Spike
- `STRONG_BUY` / `BUY` / `NEUTRAL` / `SELL` / `STRONG_SELL`

整合点：

- `crypto_monitor/quant_engine.py`
- `crypto_monitor/models.py`
- `crypto_monitor/monitor.py`
- `crypto_monitor/rules.py`

### 4.3 AI 量化上下文

价格告警调用 AI 时会携带：

- 规则原因
- 规则标签
- 量化信号
- RSI / MACD / Bollinger / Volume Spike

目标是让 AI 不只是润色文案，而是基于硬指标做解释。

### 4.4 通知模板商业化基础

新增 `affiliate` 配置段：

- `enabled`
- `referral_code`
- `deep_link_template`
- `free_mode`
- `mask_symbol`

Telegram 告警会在开启后加入：

- 脱敏标的
- 量化信号
- Deep Link
- 风险提示

### 4.5 Docker + GCP Gateway

新增：

- `Dockerfile`
- `docker-compose.yml`
- `nginx.conf`

网关代理：

- Telegram
- Gemini
- DEX Screener
- MEXC

## 5. 暂缓需求与原因

### 5.1 InviteMemberBot

可行但需要真实 Telegram 频道、支付策略、Bot token 和运营流程。当前更适合通过配置和文档对接，不应硬编码。

### 5.2 X/Twitter 自动发帖

需要 X API 权限，自动化营销内容存在账号风控风险。建议等信号质量稳定后再做。

### 5.3 DefiLlama / mempool.space

数据公开且质量好，但和当前 Solana meme 监控的主链路关联度不如 DEX Screener 与 Helius。建议作为下一阶段“宏观环境信号”接入。

### 5.4 每周胜率复盘

技术可行，但需要先定义：

- 信号生效时间
- 评价窗口
- 胜率标准
- 止盈止损规则
- 是否按价格源或 DEX pair 统计

## 6. 下一阶段建议

1. 用真实 DEX Screener token 地址验证 DEX 增强字段。
2. 用真实 Helius webhook 样本补充 `onchain.py` 映射。
3. 增加失败通知重放和死信列表。
4. 定义胜率复盘标准，再实现周报。
5. 接入 Notion 或 Telegram 长文日报。
