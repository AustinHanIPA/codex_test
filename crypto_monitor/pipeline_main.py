#!/usr/bin/env python3
"""
加密货币推荐管线 - 管线模式入口

基于推荐管线架构运行信息流筛选：
    Query Hydration → Sources → Hydrators → Filters → Scorers → Selector → Side Effects

使用方法：
    python pipeline_main.py                    # 执行一次管线
    python pipeline_main.py --query "BTC 利好" # 带查询的管线
    python pipeline_main.py --loop             # 循环执行
    python pipeline_main.py --loop --interval 300  # 每5分钟循环
    python pipeline_main.py --no-telegram      # 不推送 Telegram
    python pipeline_main.py --json             # JSON 格式输出
"""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from logger import get_monitor_logger
from pipeline import PipelineResult, create_default_pipeline
from storage import close_storage


logger = get_monitor_logger()


def print_pipeline_banner():
    """打印管线启动横幅。"""
    banner = """
    ╔═══════════════════════════════════════════════════════╗
    ║     🔮 Crypto Monitor Pipeline v3.0 🔮               ║
    ╠═══════════════════════════════════════════════════════╣
    ║  Query Hydration → Sources → Hydrators → Filters    ║
    ║  → Scorers → Selector/Blender → Side Effects        ║
    ╚═══════════════════════════════════════════════════════╝
    """
    print(banner)


def print_result(result: PipelineResult, json_output: bool = False):
    """输出管线结果。"""
    if json_output:
        print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
        return

    print(f"\n{'═' * 60}")
    print(f"📊 管线执行结果")
    print(f"{'═' * 60}")
    print(f"  总拉取: {result.total_sourced} 条")
    print(f"  过滤后: {result.total_after_filter} 条")
    print(f"  推荐数: {result.total_selected} 条")
    print(f"  耗时: {result.duration_ms:.0f}ms")

    if result.context and result.context.source_counts:
        print(f"\n📡 来源分布:")
        for source, count in sorted(result.context.source_counts.items()):
            print(f"    {source}: {count}")

    if result.context and result.context.filter_stats:
        print(f"\n🔍 过滤统计:")
        for fname, count in sorted(result.context.filter_stats.items()):
            print(f"    {fname}: 过滤 {count} 条")

    if result.items:
        print(f"\n🏆 Top 推荐:")
        for i, item in enumerate(result.items[:10], 1):
            symbols = ", ".join(item.symbols[:3]) if item.symbols else "N/A"
            print(
                f"  {i:2d}. [{item.score_final:.0f}] {item.title[:50]}"
                f"  ({item.source} | {symbols})"
            )

    print(f"\n{'═' * 60}\n")


async def run_pipeline_once(
    query: str = "",
    enable_telegram: bool = True,
    enable_storage: bool = True,
    enable_report: bool = True,
    json_output: bool = False,
) -> PipelineResult:
    """执行一次管线。"""
    pipeline = create_default_pipeline(
        enable_telegram=enable_telegram,
        enable_storage=enable_storage,
        enable_report=enable_report,
    )

    result = await pipeline.run(query=query)
    print_result(result, json_output=json_output)
    return result


async def run_pipeline_loop(
    query: str = "",
    interval: int = 300,
    enable_telegram: bool = True,
    enable_storage: bool = True,
    enable_report: bool = True,
    json_output: bool = False,
):
    """循环执行管线。"""
    pipeline = create_default_pipeline(
        enable_telegram=enable_telegram,
        enable_storage=enable_storage,
        enable_report=enable_report,
    )

    running = True

    def handle_signal():
        nonlocal running
        running = False
        logger.info("收到停止信号，管线将在当前执行结束后退出")

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    round_count = 0
    while running:
        round_count += 1
        logger.info(f"━━━ 管线第 {round_count} 轮执行 ━━━")

        try:
            result = await pipeline.run(query=query)
            print_result(result, json_output=json_output)
        except Exception as exc:
            logger.error(f"管线执行异常: {exc}")

        if running:
            logger.info(f"等待 {interval} 秒后执行下一轮...")
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    logger.info("管线循环已停止")


async def main_async(args):
    """异步主函数。"""
    try:
        if args.loop:
            await run_pipeline_loop(
                query=args.query or "",
                interval=args.interval,
                enable_telegram=not args.no_telegram,
                enable_storage=not args.no_storage,
                enable_report=not args.no_report,
                json_output=args.json,
            )
        else:
            await run_pipeline_once(
                query=args.query or "",
                enable_telegram=not args.no_telegram,
                enable_storage=not args.no_storage,
                enable_report=not args.no_report,
                json_output=args.json,
            )
    finally:
        await close_storage()


def main():
    """CLI 入口。"""
    parser = argparse.ArgumentParser(
        description="加密货币推荐管线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--query", "-q",
        type=str,
        default="",
        help="查询关键词（如 'BTC 利好', '$SOL 链上异动'）",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="循环执行模式",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="循环间隔秒数（默认 300）",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="禁用 Telegram 推送",
    )
    parser.add_argument(
        "--no-storage",
        action="store_true",
        help="禁用数据库持久化",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="禁用报告生成",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果",
    )
    parser.add_argument(
        "--config",
        type=str,
        metavar="PATH",
        help="指定配置文件路径",
    )

    args = parser.parse_args()

    if args.config:
        load_config(args.config)

    print_pipeline_banner()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
