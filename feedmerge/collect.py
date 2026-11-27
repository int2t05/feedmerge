"""读取公开订阅，统一发布日期、原文 URL 和摘要素材。"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass(frozen=True)
class Entry:
    source: str
    url: str
    title: str
    excerpt: str
    published: datetime


def clean(value):
    value = value or ""
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True) if "<" in value and ">" in value else unescape(value)
    return " ".join(text.split())


def canonical(value):
    """统一帖子域名并清除营销参数，保留文章识别参数。"""
    parts = urlsplit(value or "")
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return ""
    host = parts.netloc.lower()
    if host in {"fxtwitter.com", "www.fxtwitter.com", "fixupx.com", "twitter.com"}:
        host = "x.com"
    if host in {"www.bilibili.com", "bilibili.com", "www.douyin.com", "douyin.com", "weibo.com", "m.weibo.cn"}:
        return ""
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.startswith("utm_") and k not in {"spm", "from"}]
    return urlunsplit((parts.scheme, host, parts.path, urlencode(sorted(query)), ""))


def parse_date(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except ValueError:
            return None
    return result if result.tzinfo else None


def fetch(url):
    """用有限的超时读取一个公开地址。"""
    retry = Retry(total=1, status_forcelist=(502, 503, 504), respect_retry_after_header=False)
    with requests.Session() as client:
        client.mount("https://", HTTPAdapter(max_retries=retry))
        result = client.get(url, timeout=(5, 15), headers={
            "User-Agent": "FeedMerge/0.1",
            "Accept": "application/rss+xml, application/atom+xml, text/html, */*",
        })
        result.raise_for_status()
        return result


def make_entry(source, url, title, excerpt, date):
    date = parse_date(date)
    url = canonical(url)
    excerpt = clean(excerpt)[:2000]
    title = clean(title)[:170] or excerpt[:75]
    return Entry(source, url, title, excerpt, date) if url and title and excerpt and date else None


def read_feed(source, response):
    parsed = feedparser.parse(response.content)
    if not parsed.version:
        raise ValueError("响应不是 RSS 或 Atom")
    return [
        make_entry(source, urljoin(response.url, item.get("link", "")), item.get("title"),
                   (item.get("content") or [{}])[0].get("value") or item.get("summary"),
                   item.get("published") or item.get("updated"))
        for item in parsed.entries[:35] if item.get("link")
    ]


def next_data(response):
    document = BeautifulSoup(response.content, "html.parser")
    script = document.select_one("script#__NEXT_DATA__")
    if not script or not script.string:
        raise ValueError("公开页缺少结构化数据")
    return json.loads(script.string)["props"]["pageProps"]


def read_podcast(source, response):
    # 播客只收节目简介和原页链接，不转写音频。
    return [
        make_entry(source, urljoin(response.url, f'/episode/{episode["eid"]}'), episode.get("title"),
                   episode.get("shownotes") or episode.get("description"), episode.get("pubDate"))
        for episode in next_data(response)["podcast"]["episodes"][:25]
        if episode.get("payType") in {None, "FREE"}
    ]


def read_jike(source, response):
    return [
        make_entry(source, urljoin(response.url, f'/originalPosts/{post["id"]}'), "",
                   post.get("content"), post.get("createdAt"))
        for post in next_data(response)["posts"][:25] if post.get("type") == "ORIGINAL_POST"
    ]


READERS = {"rss": read_feed, "podcast": read_podcast, "jike": read_jike}


def collect_one(source):
    try:
        url = source["url"]
        try:
            response = fetch(url)
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout):
            if urlsplit(url).hostname != "fixupx.com":
                raise
            # FxEmbed 提供两个公开域名，主域偶发失败时试一次备用域。
            response = fetch(url.replace("https://fixupx.com/", "https://fxtwitter.com/", 1))
        entries = [entry for entry in READERS[source["adapter"]](source["name"], response) if entry]
        if not entries:
            return [], "无包含正文和有效日期的条目"
        return entries, f"成功，{len(entries)} 条可选"
    except requests.HTTPError as error:
        return [], f"HTTP {error.response.status_code}"
    except requests.RequestException:
        return [], "网络请求失败或超时"
    except (ValueError, KeyError, TypeError, AttributeError):
        return [], "响应格式与当前适配器不符"


def collect(sources, day, zone):
    """对来源并发取样，按北京时间日期过滤和去重。"""
    active = [source for source in sources if source.get("adapter") in READERS]
    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = list(pool.map(collect_one, active))
    status = {}
    candidates = {}
    for source, (entries, state) in zip(active, fetched, strict=True):
        status[source["name"]] = state
        today = [entry for entry in entries if entry.published.astimezone(zone).date() == day]
        if today:
            candidates[source["name"]] = sorted(today, key=lambda entry: entry.published, reverse=True)
    selected = []
    urls = set()
    titles = set()
    # 每个来源保留当天最新的一条独立内容，为每句摘要对应一个原文。
    for entries in candidates.values():
        for entry in entries:
            title = re.sub(r"\W+", "", entry.title.casefold())
            if entry.url in urls or (len(title) >= 12 and title in titles):
                continue
            urls.add(entry.url)
            titles.add(title)
            selected.append(entry)
            break
    return selected, status
