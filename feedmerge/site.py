"""把摘要和订阅目录渲染为 VitePress 页面。"""

import html
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
STATE = SITE / "public" / "archive-data.json"


def safe_text(value):
    """转义来源和模型文字，使其只作为 Markdown 页面上的文本。"""
    value = html.escape(str(value), quote=False)
    value = value.replace("{", "｛").replace("}", "｝")
    value = re.sub(r"[\n\r]+", " ", value)
    return re.sub(r"([\\\x60*_{}\[\]()!|~])", r"\\\1", value)


def safe_link(label, url):
    text = safe_text(label)
    safe_url = quote(url, safe=":/?#[]@!$&'*+,;=%")
    return f"[{text}](<{safe_url}>)"


def load_archive(url=None):
    """读取本地或已发布的摘要存档。发布地址 404 表示尚无已发布存档。"""
    if url:
        response = requests.get(url, headers={"Cache-Control": "no-cache"}, timeout=(6, 20))
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        archive = response.json()
    elif STATE.exists():
        archive = json.loads(STATE.read_text(encoding="utf-8"))
    else:
        return {}
    if archive["version"] != 2 or not isinstance(archive["days"], dict):
        raise ValueError("日报存档版本或格式不兼容")
    for key, digest in archive["days"].items():
        if date.fromisoformat(key).isoformat() != key or digest["date"] != key:
            raise ValueError("存档中的日期不匹配")
    return archive["days"]


def write(path, content):
    """原子替换单个文件，避免读者拿到半写入的 Markdown 或 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="\n")
    temp.replace(path)


def format_daily(digest):
    sections = [
        f'# {digest["date"]} 每日简报',
        f'北京时间 · 入选素材 {digest["collected"]} 条 · '
        f'成功读取 {digest["successful_sources"]} / {digest["total_sources"]} 个订阅源',
    ]
    if not digest["items"]:
        sections.append("这一天的可用订阅样本中没有找到符合条件的更新。")
    for point in digest["items"]:
        source = point["source"]
        link = safe_link(source["name"], source["url"])
        sections.append(f'- {safe_text(point["summary"])} {link}')
    return "\n\n".join(sections) + "\n"


def render(archive, sources, status):
    """更新日报、首页和订阅目录。存档只保留摘要、引用和采集状态。"""
    dates = sorted(archive, reverse=True)
    if dates and not status:
        status = archive[dates[0]].get("source_status", {})
    lines = ["# 每日简报", "来自公开订阅的中文摘要，按北京时间归档。"]
    if dates:
        lines.append(f"- [最新简报 · {dates[0]}](daily/{dates[0]}.md)")
        lines.append("## 历史简报")
        lines.extend(f"- [{day}](daily/{day}.md)" for day in dates)
    else:
        lines.append("首期简报将在采集任务完成后发布。")
    for day in dates:
        write(SITE / "daily" / f"{day}.md", format_daily(archive[day]))
    write(SITE / "index.md", "\n\n".join(lines) + "\n")

    counts = {mode: sum(source["mode"] == mode for source in sources) for mode in ("active", "reference", "pending")}
    listing = [
        "# 订阅来源", "",
        f'自动采集 {counts["active"]} 个，参考资料 {counts["reference"]} 个，待接入 {counts["pending"]} 个。',
        "", "| 来源 | 平台 | 状态 |", "| --- | --- | --- |",
    ]
    labels = {"active": "自动采集", "reference": "参考资料", "pending": "待接入"}
    for source in sources:
        name = safe_link(source["name"], source["url"]) if source.get("url") else safe_text(source["name"])
        state = status.get(source["name"]) or source.get("note") or labels[source["mode"]]
        listing.append(f'| {name} | {safe_text(source["platform"])} | {safe_text(state)} |')
    write(SITE / "sources.md", "\n".join(listing) + "\n")
    write(STATE, json.dumps({"version": 2, "days": archive}, ensure_ascii=False, indent=2) + "\n")
