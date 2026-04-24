#!/usr/bin/env python3
"""
加密货币监控系统 - 主入口

功能特性：
- 多币种价格监控
- 多级波动阈值报警
- AI智能点评
- Telegram实时推送
- 数据持久化存储
- 健康检查与自恢复

使用方法：
    python main.py              # 启动监控
    python main.py --test       # 测试模式
    python main.py --add BTC    # 添加监控币种
    python main.py --remove BTC # 移除监控币种
    python main.py --status     # 查看状态
"""
import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path

from aiohttp import web

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent))

from config import get_config, load_config
from monitor import MonitorEngine
from market import close_fetcher, get_fetcher
from ai_service import get_ai_service
from notifier import close_notifier, get_notifier
from storage import close_storage, get_storage


def print_banner():
    """打印启动横幅"""
    banner = """
    ╔═══════════════════════════════════════════════════════╗
    ║        🔮 加密货币智能监控系统 v2.0 🔮                 ║
    ╠═══════════════════════════════════════════════════════╣
    ║  • 多币种实时监控    • 多级波动阈值报警              ║
    ║  • AI智能点评        • Telegram实时推送              ║
    ║  • 数据持久化存储    • 健康检查与自恢复              ║
    ╚═══════════════════════════════════════════════════════╝
    """
    print(banner)


def check_config():
    """检查配置是否完整"""
    config = get_config()
    
    issues = []
    
    if not config.gcp_ip:
        issues.append("❌ GCP_IP 未设置")
    else:
        print(f"✅ GCP_IP: {config.gcp_ip}")
    
    if not config.gemini_api_key:
        issues.append("❌ GEMINI_API_KEY 未设置")
    else:
        print(f"✅ GEMINI_API_KEY: {'*' * 8}{config.gemini_api_key[-4:]}")
    
    if not config.tg_bot_token:
        issues.append("❌ TG_BOT_TOKEN 未设置")
    else:
        print(f"✅ TG_BOT_TOKEN: {'*' * 8}{config.tg_bot_token[-4:]}")
    
    if not config.tg_chat_id:
        issues.append("❌ TG_CHAT_ID 未设置")
    else:
        print(f"✅ TG_CHAT_ID: {config.tg_chat_id}")
    
    print(f"\n📊 监控币种: {', '.join(config.monitor.watch_list)}")
    print(f"🌐 监听地址: {config.service.host}:{config.service.port}")
    print(f"⏱️  检查间隔: {config.monitor.interval}秒")
    print(f"🎯 波动阈值: 小{config.monitor.thresholds.minor}% / "
          f"中{config.monitor.thresholds.moderate}% / "
          f"大{config.monitor.thresholds.major}%")
    
    if issues:
        print("\n⚠️  配置问题:")
        for issue in issues:
            print(f"  {issue}")
        print("\n请复制 .env.example 为 .env 并填写必要配置")
        return False
    
    return True


async def create_http_server(engine: MonitorEngine) -> tuple[web.AppRunner, web.TCPSite]:
    """创建本地监听服务，用于健康检查和状态查看。"""
    config = get_config()

    async def index(_request: web.Request) -> web.Response:
        return web.json_response(
            {
                "name": "crypto-monitor",
                "status": "ok" if engine.failure_count < config.health_check.max_failures else "degraded",
                "endpoints": ["/", "/health", "/status", "/webhooks/onchain", "/reports/daily"],
            }
        )

    async def health(_request: web.Request) -> web.Response:
        payload = {
            "status": "ok" if engine.failure_count < config.health_check.max_failures else "degraded",
            "running": engine.running,
            "paused": engine.paused,
            "failure_count": engine.failure_count,
            "last_success": engine.last_success_time.isoformat() if engine.last_success_time else None,
        }
        return web.json_response(payload)

    async def status(_request: web.Request) -> web.Response:
        return web.json_response(engine.get_status())

    async def onchain_webhook(request: web.Request) -> web.Response:
        token = config.onchain.webhook_auth_token
        if token:
            provided = request.headers.get("X-Webhook-Token") or request.query.get("token")
            if provided != token:
                return web.json_response({"error": "unauthorized"}, status=401)

        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid json"}, status=400)

        source = request.query.get("source", "webhook")
        result = await engine.process_onchain_payload(payload, source=source)
        return web.json_response(result)

    async def daily_report(request: web.Request) -> web.Response:
        raw_hours = request.query.get("hours")
        lookback_hours = int(raw_hours) if raw_hours and raw_hours.isdigit() else None
        send = request.query.get("send", "").lower() in {"1", "true", "yes"}
        result = await engine.generate_daily_report(lookback_hours=lookback_hours, send=send)
        return web.json_response(result)

    app = web.Application()
    app.add_routes([
        web.get("/", index),
        web.get("/health", health),
        web.get("/status", status),
        web.post("/webhooks/onchain", onchain_webhook),
        web.post("/reports/daily", daily_report),
    ])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=config.service.host, port=config.service.port)
    await site.start()
    print(f"🌐 Python 服务已监听 http://{config.service.host}:{config.service.port}")
    return runner, site


async def test_connection():
    """测试各服务连接"""
    print("\n🔍 测试服务连接...\n")

    try:
        # 测试市场数据
        print("1. 测试市场数据服务...")
        fetcher = get_fetcher()
        prices = await fetcher.get_all_prices()
        if prices:
            print(f"   ✅ 成功获取 {len(prices)} 个交易对价格")
            if 'BTCUSDT' in prices:
                print(f"   💰 BTC 当前价格: ${prices['BTCUSDT']:,.2f}")
        else:
            print("   ❌ 市场数据服务连接失败")
            return False

        # 测试AI服务
        print("\n2. 测试AI服务...")
        ai = get_ai_service()
        comment = await ai.generate_comment("BTC", 60000.0, 2.5, "minor", "嘲讽或戏谑")
        if comment:
            print(f"   ✅ AI服务正常")
            print(f"   🤖 测试点评: {comment}")
        else:
            print("   ⚠️  AI服务可能存在问题（将使用备用评论）")

        # 测试Telegram
        print("\n3. 测试Telegram通知...")
        notifier = get_notifier()
        test_sent = await notifier.telegram.send_message(
            "🧪 测试消息 - 加密货币监控系统已启动",
            disable_notification=True
        )
        if test_sent:
            print("   ✅ Telegram通知正常")
        else:
            print("   ⚠️  Telegram通知可能存在问题")

        # 测试数据库
        print("\n4. 测试数据库...")
        storage = await get_storage()
        stats = await storage.get_statistics()
        print(f"   ✅ 数据库连接正常")
        print(f"   📊 价格记录: {stats.get('total_prices', 0)}")
        print(f"   📊 报警记录: {stats.get('total_alerts', 0)}")

        print("\n✅ 所有服务测试完成")
        return True
    finally:
        await close_fetcher()
        await close_notifier()
        await close_storage()


async def add_symbol(symbol: str):
    """添加监控币种"""
    engine = MonitorEngine()
    await engine.initialize()
    await engine.add_symbol(symbol.upper())
    print(f"✅ 已添加 {symbol.upper()} 到监控列表")
    await engine.cleanup()


async def remove_symbol(symbol: str):
    """移除监控币种"""
    engine = MonitorEngine()
    await engine.initialize()
    await engine.remove_symbol(symbol.upper())
    print(f"✅ 已从监控列表移除 {symbol.upper()}")
    await engine.cleanup()


async def show_status():
    """显示系统状态"""
    engine = MonitorEngine()
    await engine.initialize()
    
    status = engine.get_status()
    
    print("\n📊 系统状态:")
    print(f"  运行状态: {'✅ 运行中' if status['running'] else '⏹️ 已停止'}")
    print(f"  暂停状态: {'⏸️ 暂停' if status['paused'] else '▶️ 运行'}")
    print(f"  运行时长: {status['uptime'] or 'N/A'}")
    print(f"  监控币种: {', '.join(status['watch_list'])}")
    print(f"  失败次数: {status['failure_count']}")
    print(f"  最后成功: {status['last_success'] or 'N/A'}")
    
    # 获取统计信息
    storage = await get_storage()
    stats = await storage.get_statistics()
    
    print("\n📈 数据统计:")
    print(f"  总价格记录: {stats.get('total_prices', 0)}")
    print(f"  总报警记录: {stats.get('total_alerts', 0)}")
    print(f"  今日报警: {stats.get('today_alerts', 0)}")
    print(f"  监控币种数: {stats.get('monitored_symbols', 0)}")
    
    await engine.cleanup()


async def run_monitor():
    """运行监控引擎"""
    print_banner()
    
    if not check_config():
        sys.exit(1)
    
    if not await test_connection():
        print("\n⚠️  部分服务连接失败，请检查配置")
        # 可以选择继续运行或退出
        # sys.exit(1)
    
    print("\n" + "=" * 60)
    print("🚀 启动监控引擎...")
    print("=" * 60 + "\n")
    
    engine = MonitorEngine()
    await engine.initialize()
    runner, _site = await create_http_server(engine)
    
    # 注册信号处理
    loop = asyncio.get_event_loop()
    
    def handle_signal():
        print("\n\n⏹️  收到停止信号，正在优雅关闭...")
        engine.stop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)
    
    try:
        await engine.run_forever()
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断")
    finally:
        await runner.cleanup()
        await engine.cleanup()
        print("\n👋 监控引擎已关闭，再见！")


async def run_once():
    """执行一次检查"""
    engine = MonitorEngine()
    await engine.initialize()
    
    print("🔍 执行单次检查...\n")
    
    result = await engine.run_once()
    
    print("\n检查结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    await engine.cleanup()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="加密货币智能监控系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python main.py              # 启动监控
    python main.py --test       # 测试模式
    python main.py --once       # 执行一次检查
    python main.py --add BTC    # 添加监控币种
    python main.py --remove BTC # 移除监控币种
    python main.py --status     # 查看状态
    python main.py --check      # 检查配置
        """
    )
    
    parser.add_argument(
        '--test', 
        action='store_true',
        help='测试模式，检查各服务连接'
    )
    
    parser.add_argument(
        '--once',
        action='store_true',
        help='执行一次检查'
    )
    
    parser.add_argument(
        '--add',
        type=str,
        metavar='SYMBOL',
        help='添加监控币种'
    )
    
    parser.add_argument(
        '--remove',
        type=str,
        metavar='SYMBOL',
        help='移除监控币种'
    )
    
    parser.add_argument(
        '--status',
        action='store_true',
        help='显示系统状态'
    )
    
    parser.add_argument(
        '--check',
        action='store_true',
        help='检查配置'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        metavar='PATH',
        help='指定配置文件路径'
    )
    
    parser.add_argument(
        '--env',
        type=str,
        metavar='PATH',
        help='指定环境变量文件路径'
    )
    
    args = parser.parse_args()
    
    # 加载配置
    if args.config or args.env:
        load_config(args.config, args.env)
    
    # 执行对应操作
    if args.test:
        print_banner()
        check_config()
        asyncio.run(test_connection())
    
    elif args.once:
        asyncio.run(run_once())
    
    elif args.add:
        asyncio.run(add_symbol(args.add))
    
    elif args.remove:
        asyncio.run(remove_symbol(args.remove))
    
    elif args.status:
        asyncio.run(show_status())
    
    elif args.check:
        print_banner()
        check_config()
    
    else:
        # 默认：启动监控
        asyncio.run(run_monitor())


if __name__ == "__main__":
    main()
