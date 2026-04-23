# Crypto Monitor 技术设计文档

更新时间：2026-04-23

## 1. 目标

本文档描述当前 `crypto_monitor` 的技术实现、模块边界、运行机制和后续演进方案。

## 2. 当前技术栈

- 语言：Python 3
- 异步框架：`asyncio`
- HTTP 客户端：`aiohttp`
- 本地 HTTP 服务：`aiohttp.web`
- 存储：`SQLite + aiosqlite`
- 通知：Telegram Bot API
- AI 模型：Gemini 兼容接口
- 配置：YAML + `.env`
- 日志：`logging` + `RotatingFileHandler`

## 3. 代码结构

### 3.1 入口层

- `crypto_monitor/main.py`

职责：

- 解析 CLI 参数
- 检查配置
- 启动监控引擎
- 启动本地 HTTP 服务
- 提供测试/单次运行/状态查看等运维命令

### 3.2 调度层

- `crypto_monitor/monitor.py`

职责：

- 编排行情抓取、规则判断、AI 解读、通知发送、状态落库
- 控制监控主循环
- 管理健康检查、自恢复、暂停/恢复/停止

### 3.3 基础设施层

- `crypto_monitor/market.py`
  - 抓取行情
  - 将原始 payload 归一化为 `MarketSnapshot`

- `crypto_monitor/ai_service.py`
  - 调用 Gemini
  - 生成结构化 `AIInsight`
  - 对非标准模型输出做降级解析

- `crypto_monitor/notifier.py`
  - 异步发送 Telegram 消息
  - 实现限流

- `crypto_monitor/storage.py`
  - SQLite 初始化
  - 价格/告警/状态/监控名单读写

- `crypto_monitor/logger.py`
  - 控制台日志
  - 文件滚动日志

### 3.4 领域模型层

- `crypto_monitor/models.py`

核心模型：

- `MarketSnapshot`
- `AIInsight`
- `PriceState`

## 4. 当前系统架构

```text
CLI / 本地 HTTP 服务
        |
        v
  MonitorEngine
   |    |    |    |
   |    |    |    +--> Storage (SQLite)
   |    |    +-------> Notifier (Telegram)
   |    +------------> AI Service (Gemini)
   +-----------------> Market Fetcher (行情源)
```

## 5. 核心运行流程

### 5.1 启动流程

1. `main.py` 读取配置。
2. 初始化 `MonitorEngine`。
3. 打开数据库连接。
4. 恢复监控名单和币种状态。
5. 拉起本地 HTTP 服务。
6. 进入主循环。

### 5.2 单轮执行流程

1. `market.py` 抓取全量行情。
2. 按监控名单筛选目标交易对。
3. `PriceState` 计算相对上次采样的涨跌幅。
4. 根据阈值判断是否触发告警。
5. 对需告警对象调用 `ai_service.py`。
6. `notifier.py` 异步发送消息。
7. `storage.py` 写入价格历史、告警历史和状态。

### 5.3 恢复流程

1. 启动时从 `watchlist_symbols` 恢复监控名单。
2. 启动时从 `symbol_state` 恢复最后价格和最后告警时间。

## 6. 本地 HTTP 服务

当前由 `aiohttp.web` 提供。

监听配置：

- `service.host`
- `service.port`

默认端口：

- `28593`

已提供接口：

- `GET /`
- `GET /health`
- `GET /status`

用途：

- 本地探活
- 容器健康检查
- 状态读取

## 7. 配置设计

配置来源：

1. `config.yaml`
2. `.env`

主要配置段：

- `monitor`
- `market`
- `ai`
- `notification`
- `storage`
- `logging`
- `health_check`
- `service`

原则：

- 结构化配置优先
- 敏感信息通过环境变量注入
- 运行时具备合理默认值

## 8. 数据模型与表结构

### 8.1 价格历史表 `price_history`

字段：

- `symbol`
- `price`
- `change_percent`
- `timestamp`

用途：

- 历史走势查询
- 后续日报/回测/分析基础数据

### 8.2 告警历史表 `alerts`

字段：

- `symbol`
- `price`
- `change_percent`
- `alert_level`
- `ai_comment`
- `telegram_message_id`
- `sent_at`

用途：

- 告警审计
- 复盘分析

### 8.3 状态表 `symbol_state`

字段：

- `symbol`
- `last_price`
- `last_alert_time`

用途：

- 冷却时间恢复
- 重启后延续状态

### 8.4 监控名单表 `watchlist_symbols`

字段：

- `symbol`
- `created_at`

用途：

- 持久化监控名单

## 9. 可靠性设计

### 9.1 已实现

1. 市场抓取重试
2. Telegram 异步发送
3. 单币种和总量限流
4. 健康检查与轻量自恢复
5. 状态持久化恢复
6. 批量价格写入

### 9.2 当前不足

1. 还没有真正的事件总线
2. 没有消息队列
3. 没有告警幂等键
4. 没有请求签名校验
5. 没有更细粒度监控指标

## 10. 技术债分析

### 10.1 当前技术债

1. 行情源仍偏单一
2. 监控逻辑主要围绕价格波动，尚未抽象成完整规则引擎
3. AI 仍是单轮调用，没有缓存和复用
4. 数据表结构足够 MVP，但不足以支撑复杂分析平台
5. 本地 HTTP 服务还只是运维接口，不是正式控制面 API

### 10.2 工程债

1. 仓库中仍存在历史产物和辅助文件，如 `repomix-output.xml`、`test.json`
2. 测试覆盖不够完整，缺主流程和故障注入测试
3. 还没有标准部署编排文件

## 11. 目标架构建议

建议逐步收敛成如下分层：

### 11.1 Data Plane

负责实时监控和事件处理：

- 行情采集
- 链上事件采集
- AI 分析
- 规则引擎
- 通知分发

### 11.2 Control Plane

负责配置和运营管理：

- 监控名单管理
- 规则管理
- 用户与租户管理
- 报表查询
- 通知渠道配置

### 11.3 Storage Plane

负责三类数据：

1. 热状态
   - Redis

2. 业务关系数据
   - PostgreSQL

3. 时序/事件数据
   - ClickHouse 或对象存储 + ETL

## 12. 推荐演进路径

### Step 1：继续强化当前 Python 单体

- 增强接口
- 增加规则引擎
- 增加报告层

### Step 2：拆分数据采集与控制面

- 监控引擎继续 Python
- 管理后台和 API 可独立服务化

### Step 3：事件化与多源化

- 接入 WebSocket / Webhook / Streams
- 建立统一事件模型
- 引入更强持久化和分析能力

## 13. 结论

当前代码已经具备一个“可运行的监控服务”骨架，技术方向是正确的：

- 有编排中心
- 有状态恢复
- 有 AI 层
- 有通知层
- 有健康检查

下一阶段最重要的不是推翻重写，而是把它从“单点轮询机器人”升级成“多源、低延迟、可复盘的监控系统”。
