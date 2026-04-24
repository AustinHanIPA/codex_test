# HANDOFF

## 当前目标
把 `crypto_monitor` 维护成一个可运营的 Web3 监控 MVP：价格监控 + 链上 webhook + 配置化规则 + AI 摘要 + Telegram 通知 + 投递审计 + 日报 + 轻量控制面。

## 已完成
- 本地服务已监听在 `28593`，并提供健康检查、状态、统计、监控名单、告警、链上事件、投递记录、webhook 和日报接口。
- 监控主链路已异步化，包含行情抓取、Telegram 通知、SQLite 存储。
- 配置层已扩展出 `onchain`、`rules`、`reporting`、`service.port=28593`、`service.admin_token` 等字段。
- 领域模型已补充 `MarketSnapshot`、`AIInsight`、`OnchainEvent`。
- `RuleEngine` 已接入主流程，并支持轻量 `rules.market` / `rules.onchain` 配置规则。
- webhook 已支持 token、HMAC-SHA256 签名和事件去重。
- 已新增链上 provider payload 归一化、结构化 AI 输出、Markdown 日报、通知投递记录。
- 已整理并更新反向需求、技术设计、Web3 优化方向和 api-doc-inspect 启发文档。

## 待办
- 接入真实 Helius/QuickNode webhook 样本，继续完善 `onchain.py` 字段映射。
- 增加失败通知重试和死信列表。
- 接入 DEX Screener / Birdeye，补齐 DEX 价格、流动性和市值。
- 将规则 DSL 从轻量 `all` 条件扩展到完整 AND/OR 和规则管理接口。
- 接入 Notion 日报。
- 增加 Web 控制台、多用户和多渠道通知。

## 关键文件
- [main.py](/Users/yy/Downloads/aiCode/crypto_monitor/main.py)
- [monitor.py](/Users/yy/Downloads/aiCode/crypto_monitor/monitor.py)
- [config.py](/Users/yy/Downloads/aiCode/crypto_monitor/config.py)
- [config.yaml](/Users/yy/Downloads/aiCode/crypto_monitor/config.yaml)
- [models.py](/Users/yy/Downloads/aiCode/crypto_monitor/models.py)
- [rules.py](/Users/yy/Downloads/aiCode/crypto_monitor/rules.py)
- [onchain.py](/Users/yy/Downloads/aiCode/crypto_monitor/onchain.py)
- [ai_service.py](/Users/yy/Downloads/aiCode/crypto_monitor/ai_service.py)
- [market.py](/Users/yy/Downloads/aiCode/crypto_monitor/market.py)
- [storage.py](/Users/yy/Downloads/aiCode/crypto_monitor/storage.py)
- [reporting.py](/Users/yy/Downloads/aiCode/crypto_monitor/reporting.py)
- [docs/reverse-prd.md](/Users/yy/Downloads/aiCode/docs/reverse-prd.md)
- [docs/technical-design.md](/Users/yy/Downloads/aiCode/docs/technical-design.md)
- [docs/web3-monitoring-optimization.md](/Users/yy/Downloads/aiCode/docs/web3-monitoring-optimization.md)

## 注意事项
- `.env`、日志、`__pycache__`、数据库文件不要重新提交进 Git。
- 目前项目是 Python 单体，重写成 Java/Spring Boot 不是当前优先级。
- 如果要跨电脑继续做，先 `git pull` 同步代码，再让 Codex 读取这份摘要和上面的文档。
- 运行验证优先看 `crypto_monitor/venv/bin/python -m unittest discover -s tests -v`，`pnpm` 在这个仓库里通常不是主工具链。
