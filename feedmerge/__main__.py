"""选择日期、采集公开来源并生成每日 Markdown。"""

import argparse
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from .collect import READERS, collect
from .digest import make_digest
from .site import ROOT, load_archive, render


ZONE = ZoneInfo("Asia/Shanghai")


def read_sources():
    """保持来源的状态和执行配置一致，拒绝重复的订阅名。"""
    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    names = set()
    for source in sources:
        name = source["name"]
        if not name or name in names or source["mode"] not in {"active", "reference", "pending"}:
            raise ValueError(f"订阅配置无效 {name}")
        if source["mode"] == "active" and (source.get("adapter") not in READERS or not source.get("url")):
            raise ValueError(f"缺少可用适配器或地址 {name}")
        names.add(name)
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, help="目标日期，默认北京时间昨天")
    parser.add_argument("--history-url", help="已发布的 archive-data.json 地址")
    parser.add_argument("--render-only", action="store_true", help="仅从现有存档生成站点")
    parser.add_argument("--refresh", action="store_true", help="重新生成指定日期")
    parser.add_argument("--check-sources", action="store_true", help="检查来源和日期命中，不调用 DeepSeek")
    args = parser.parse_args()
    day = args.date or datetime.now(ZONE).date() - timedelta(days=1)

    try:
        sources = read_sources()
        status = {}
        if args.check_sources:
            entries, status = collect(sources, day, ZONE)
            for name, state in status.items():
                print(f"{name}: {state}")
            print(f"{day}: {len(entries)} 条日期匹配")
            return 0 if any(s.startswith("成功") for s in status.values()) else 1
        archive = load_archive(args.history_url)
        if not args.render_only and (day.isoformat() not in archive or args.refresh):
            entries, status = collect(sources, day, ZONE)
            for name, state in status.items():
                print(f"{name}: {state}")
            if not any(s.startswith("成功") for s in status.values()):
                raise RuntimeError("本轮没有成功读取任何订阅源")
            if entries or day.isoformat() not in archive:
                archive[day.isoformat()] = make_digest(day, entries, status)
            print(f"{day}: {len(entries)} 条用于摘要")
        render(archive, sources, status)
        return 0
    except (requests.RequestException, RuntimeError, ValueError, TypeError, KeyError, IndexError) as error:
        reason = type(error).__name__ if isinstance(error, requests.RequestException) else str(error)
        parser.exit(1, f"FeedMerge 运行失败。{reason}\n")


if __name__ == "__main__":
    raise SystemExit(main())
