# HANDOFF

## 当前目标
把 `crypto_monitor` 继续演进成一个面向 Web3 的多源监控服务：从单一价格轮询，升级到价格 + 链上事件 + 规则引擎 + AI 摘要 + 报告输出的一体化链路。

## 已完成
- 本地服务已监听在 `28593`，并提供 `/`、`/health`、`/status`。
- 监控主链路已异步化，包含行情抓取、Telegram 通知、SQLite 存储。
- 配置层已扩展出 `onchain`、`reporting`、`service.port=28593` 等字段。
- 领域模型已补充 `MarketSnapshot`、`AIInsight`、`OnchainEvent`。
- 已新增 `RuleEngine`，用于价格阈值和链上事件的初步规则判断。
- 已整理反向需求、技术设计和 Web3 优化方向文档。

## 待办
- 把 `RuleEngine` 真正接入 `MonitorEngine` 的主流程，避免规则只停留在独立模块。
- 接入链上事件采集源，优先做 webhook / push 模式，再补轮询兜底。
- 扩展 AI 输出为结构化事件摘要，加入 `event_type`、`suggested_action`、`confidence`、`risk_hint` 等字段的稳定生成。
- 增加报告层，支持每日定时汇总，后续可接 Notion。
- 补充存储层对链上事件和日报的持久化。
- 增加主流程测试，覆盖告警触发、冷却、生效、失败降级和状态恢复。

## 关键文件
- [main.py](/Users/yy/Downloads/aiCode/crypto_monitor/main.py)
- [monitor.py](/Users/yy/Downloads/aiCode/crypto_monitor/monitor.py)
- [config.py](/Users/yy/Downloads/aiCode/crypto_monitor/config.py)
- [config.yaml](/Users/yy/Downloads/aiCode/crypto_monitor/config.yaml)
- [models.py](/Users/yy/Downloads/aiCode/crypto_monitor/models.py)
- [rules.py](/Users/yy/Downloads/aiCode/crypto_monitor/rules.py)
- [ai_service.py](/Users/yy/Downloads/aiCode/crypto_monitor/ai_service.py)
- [market.py](/Users/yy/Downloads/aiCode/crypto_monitor/market.py)
- [storage.py](/Users/yy/Downloads/aiCode/crypto_monitor/storage.py)
- [docs/reverse-prd.md](/Users/yy/Downloads/aiCode/docs/reverse-prd.md)
- [docs/technical-design.md](/Users/yy/Downloads/aiCode/docs/technical-design.md)
- [docs/web3-monitoring-optimization.md](/Users/yy/Downloads/aiCode/docs/web3-monitoring-optimization.md)

## 注意事项
- `.env`、日志、`__pycache__`、数据库文件不要重新提交进 Git。
- 目前项目是 Python 单体，重写成 Java/Spring Boot 不是当前优先级。
- 如果要跨电脑继续做，先 `git pull` 同步代码，再让 Codex 读取这份摘要和上面的文档。
- 运行验证优先看 `crypto_monitor/venv/bin/python -m unittest discover -s tests -v`，`pnpm` 在这个仓库里通常不是主工具链。
