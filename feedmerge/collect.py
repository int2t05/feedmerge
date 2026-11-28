"""读取公开订阅，统一发布日期、原文 URL 和摘要素材。"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


FX_FEED_ALIASES = {
    "fixupx.com": "fxtwitter.com",
    "fxtwitter.com": "fixupx.com",
    "www.fxtwitter.com": "fixupx.com",
}
X_FEED_HOSTS = {*FX_FEED_ALIASES, "teapawt.org"}


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
    if host in X_FEED_HOSTS or host == "twitter.com":
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


def fetch(url, *, default_headers=False):
    """用有限的超时读取一个公开地址。"""
    retry = Retry(total=1, status_forcelist=(502, 503, 504), respect_retry_after_header=False)
    with requests.Session() as client:
        client.mount("https://", HTTPAdapter(max_retries=retry))
        headers = None if default_headers else {
            "User-Agent": "FeedMerge/0.1",
            "Accept": "application/rss+xml, application/atom+xml, text/html, */*",
        }
        result = client.get(url, timeout=(5, 15), headers=headers)
        result.raise_for_status()
        return result


def make_entry(source, url, title, excerpt, date):
    date = parse_date(date)
    url = canonical(url)
    excerpt = clean(excerpt)[:2000]
    title = clean(title)[:170] or excerpt[:75]
    return Entry(source, url, title, excerpt, date) if url and title and excerpt and date else None


def read_feed(source, response):
    """从 RSS 或 Atom 读取内容，X 时间线只收账号本人的原帖。"""
    parsed = feedparser.parse(response.content)
    if not parsed.version:
        raise ValueError("响应不是 RSS 或 Atom")
    feed_url = urlsplit(response.url)
    owner = (
        feed_url.path.split("/")[1].casefold()
        if feed_url.hostname in X_FEED_HOSTS else ""
    )
    entries = []
    for item in parsed.entries:
        if not item.get("link"):
            continue
        url = canonical(urljoin(response.url, item["link"]))
        if owner and not re.match(rf"^https?://x\.com/{re.escape(owner)}/status/", url, re.I):
            continue
        entry = make_entry(
            source, url, item.get("title"),
            (item.get("content") or [{}])[0].get("value") or item.get("summary"),
            item.get("published") or item.get("updated"),
        )
        if entry:
            entries.append(entry)
        if len(entries) == 35:
            break
    return entries


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


def read_tencent_column(source, response):
    """读取腾讯云公开专栏随页面返回的文章摘要和发布日期。"""
    fallback = next_data(response)["fallback"]
    pages = next(value for key, value in fallback.items() if "/api/column/getArticlesByColumnId" in key)
    zone = ZoneInfo("Asia/Shanghai")
    entries = []
    for row in pages[0]["list"]:
        if row.get("author", {}).get("nickname") != source or not row.get("createTime"):
            continue
        published = datetime.strptime(row["createTime"], "%Y/%m/%d %H:%M:%S").replace(tzinfo=zone)
        entries.append(make_entry(
            source, urljoin(response.url, f'/developer/article/{row["articleId"]}'),
            row.get("title"), row.get("summary"), published.isoformat(),
        ))
    return entries


def read_pmthinking(source, response):
    """从产品沉思录归档找到近期文章，并读取原站正文。"""
    document = BeautifulSoup(response.content, "html.parser")
    entries = []
    for link in document.select('li > time[datetime] + a[href^="/p/"]', limit=5):
        url = urljoin(response.url, link["href"])
        page = BeautifulSoup(fetch(url).content, "html.parser")
        paragraphs = page.select('article[aria-labelledby="article-title"] > p')
        text = " ".join(paragraph.get_text(" ", strip=True) for paragraph in paragraphs)
        published = link.find_previous_sibling("time")["datetime"]
        entries.append(make_entry(source, url, link.get_text(" ", strip=True), text, published + "T00:00:00+08:00"))
    return entries


def read_tuoluo_column(source, response):
    """从陀螺科技作者专栏读取近期文章的正文和发布日期。"""
    document = BeautifulSoup(response.content, "html.parser")
    entries = []
    zone = ZoneInfo("Asia/Shanghai")
    for card in document.select(".article_list > li.item", limit=5):
        link = card.select_one(".intro a.title[href]")
        stamp = card.select_one(".otherInfo .time")
        if not (link and stamp):
            continue
        url = urljoin(response.url, link["href"])
        page = BeautifulSoup(fetch(url).content, "html.parser")
        paragraphs = page.select("#content_acritle p")
        text = " ".join(paragraph.get_text(" ", strip=True) for paragraph in paragraphs)
        published = datetime.strptime(stamp.get_text(strip=True), "%Y年%m月%d日").replace(tzinfo=zone)
        entries.append(make_entry(source, url, link.get_text(" ", strip=True), text, published.isoformat()))
    return entries


READERS = {
    "rss": read_feed,
    "podcast": read_podcast,
    "jike": read_jike,
    "tencent-column": read_tencent_column,
    "pmthinking": read_pmthinking,
    "tuoluo-column": read_tuoluo_column,
}


def collect_one(source):
    try:
        url = source["url"]
        addresses = [url]
        feed_url = urlsplit(url)
        if alternate_host := FX_FEED_ALIASES.get(feed_url.hostname):
            # 两个 FxEmbed 域名都不可用时，尝试同一账号的独立 RSS。
            owner = feed_url.path.split("/")[1]
            addresses += [
                feed_url._replace(netloc=alternate_host).geturl(),
                f"https://teapawt.org/{owner}/rss",
            ]
        for index, address in enumerate(addresses):
            try:
                # 腾讯云专栏在默认请求头下提供可解析的公开列表。
                response = fetch(address, default_headers=source["adapter"] == "tencent-column")
            except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as error:
                if index == len(addresses) - 1 or (
                    isinstance(error, requests.HTTPError) and error.response.status_code not in {404, 502, 503, 504}
                ):
                    raise
                continue
            entries = [entry for entry in READERS[source["adapter"]](source["name"], response) if entry]
            if entries:
                return entries, f"成功，{len(entries)} 条可选"
        return [], "无包含正文和有效日期的条目"
    except requests.HTTPError as error:
        return [], f"HTTP {error.response.status_code}"
    except requests.RequestException:
        return [], "网络请求失败或超时"
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration):
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
