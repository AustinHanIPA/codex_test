# AR/AO 五维自适应量化交易系统 PRD

更新时间：2026-05-08

## 1. 项目愿景

在现有 `Crypto Monitor` 基础上扩展 AR/USDT 专用策略监控能力，围绕 Arweave 与 AO 超级计算机叙事，构建“先监控、再回测、最后谨慎执行”的自适应量化系统。

当前落地边界：

- 默认只生成策略信号和风险提示。
- 不保存交易所 API Key。
- 不自动下单。
- 执行层、期现套利和做市层先保留结构化接口，待回测和风控充分验证后再开启。

## 2. 五层策略架构

### 2.1 叙事过滤层

目标：判断当前 AR/AO 是否处于“AI 驱动牛市”或“震荡/熊市”。

输入规划：

- AO 网络存储量变化。
- Arweave/AO GitHub 活跃度。
- 社交媒体热度与情绪权重。

当前状态：已在 `ARStrategySignal.layers.narrative_filter` 中保留占位输出，等待数据源接入。

### 2.2 趋势推进层

目标：用周线识别大方向和突破。

已实现：

- Binance `/api/v3/klines` 历史 K 线分页抓取。
- 周线 MA7/MA25 趋势判断。
- MACD 与 signal line 动能判断。
- 关键阻力位 `2.645` 突破识别。
- 输出 `BUY_STEP_IN`、`WATCH_BUY`、`NEUTRAL`、`RISK_OFF` 等信号。

### 2.3 均值回归层

目标：在趋势向上时识别回调补仓窗口。

已实现：

- RSI 计算。
- Bollinger Band 宽度计算。
- 趋势向上且 RSI 超卖时输出回调买入依据。

### 2.4 对冲缓冲层

目标：当 AR/USDT 永续资金费率高于阈值时，提示“现货多 + 等值合约空”的资金费率套利。

当前状态：配置中已保留 `funding_rate_threshold=0.0003`，信号输出中保留 `hedging_arb` 占位。下一步需要接入 Binance Futures funding rate 与仓位风险模型。

### 2.5 做市增强层

目标：在窄幅震荡时运行微型网格，降低持仓成本。

当前状态：信号输出中保留 `market_making` 占位。下一步需要接入盘口深度、滑点估计和最小下单约束。

## 3. 已集成能力

### 3.1 配置

新增配置：

- `binance.base_urls`：支持官方 Binance 和 Nginx 代理池。
- `binance.page_limit`：分页大小，默认 1000。
- `ar_strategy.symbol`：默认 `ARUSDT`。
- `ar_strategy.weekly_interval`：默认 `1w`。
- `ar_strategy.ma_fast` / `ma_slow`：默认 `7/25`。
- `ar_strategy.key_resistance`：默认 `2.645`。
- `ar_strategy.step_in_slices`：默认 `3`。

### 3.2 HTTP 接口

新增：

- `GET /strategies/ar`

Query 参数：

- `symbol`：默认 `ARUSDT`。
- `interval`：默认 `1w`。
- `startTime`：Binance 毫秒时间戳。
- `endTime`：Binance 毫秒时间戳。
- `max_pages`：调试时限制分页页数。

返回：

- K 线数量。
- 最新 K 线。
- AR 策略信号。
- 五层策略状态。

### 3.3 CLI

新增：

```bash
python crypto_monitor/main.py --ar-signal
```

用途：分页拉取 ARUSDT 周线历史数据，计算 MA7/MA25、MACD、RSI、Bollinger，并输出策略信号 JSON。

## 4. 技术设计

新增模块：

- `crypto_monitor/binance.py`：异步 Binance Kline 拉取器，支持分页、重试、超时和 Nginx 代理池轮询。
- `crypto_monitor/ar_strategy.py`：AR/AO 专用策略引擎。
- `models.BinanceKline`：Binance Kline 领域模型。
- `models.ARStrategySignal`：五层策略信号模型。

架构位置：

```text
HTTP / CLI
   |
   v
BinanceKlineFetcher ----> BinanceKline[]
   |
   v
ARStrategyEngine -------> ARStrategySignal
   |
   v
JSON API / CLI Output / Future Alert Pipeline
```

## 5. 路线图

### Phase 1: MVP

已完成：

- Binance 历史 K 线分页抓取。
- ARUSDT 周线 MA7/MA25。
- MACD、RSI、Bollinger 指标。
- HTTP/CLI 信号入口。
- Nginx 代理池配置入口。

### Phase 2: Strategy

待完成：

- AO 网络数据源。
- GitHub 活跃度抓取。
- 社媒热度聚合。
- 回测引擎与参数扫描。
- 将 AR 策略信号接入现有告警规则和日报。

### Phase 3: Execution

待完成：

- Binance API Key 加密加载。
- 只读、模拟盘、实盘三模式隔离。
- Step-in 分批建仓计划。
- 止盈、止损、最大回撤熔断。
- 多 VM 主备执行锁。

### Phase 4: Optim

待完成：

- Funding rate 期现套利。
- 盘口 spread 做市策略。
- 多 VM/Nginx 代理池健康探测。
- 策略表现归因和自动降权。

## 6. 风险与安全边界

- 当前系统不自动交易，避免未经回测的策略直接触发资金风险。
- Nginx 代理池仅用于稳定性和故障切换，不建议用于规避交易所风控。
- 后续接入下单必须先实现模拟盘、最大仓位、每日亏损上限、幂等订单 ID 和人工确认开关。
- API Key 必须通过环境变量或密钥管理服务注入，不写入配置文件和 Git。
