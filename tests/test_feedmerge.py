"""回归验证日期、来源引用和 Markdown 安全边界。"""

import json
import unittest
from datetime import date
from unittest.mock import Mock, patch

import requests

from feedmerge.__main__ import ZONE, read_sources
from feedmerge.collect import collect, collect_one, make_entry, read_feed
from feedmerge.digest import summarize
from feedmerge.site import format_daily


class FeedMergeTest(unittest.TestCase):
    def test_source_inventory(self):
        sources = read_sources()
        self.assertGreaterEqual(len(sources), 49)
        self.assertTrue(any(source["mode"] == "active" for source in sources))

    def test_x_rss_skips_reposts_with_another_author_url(self):
        response = Mock(url="https://fixupx.com/Jimmy/feed.xml")
        response.content = b"""<rss version="2.0"><channel><title>Jimmy</title>
          <item><title>Repost</title><link>https://x.com/other/status/1</link>
          <description>Other author</description>
          <pubDate>Thu, 26 Nov 2026 18:00:00 GMT</pubDate></item>
          <item><title>Original</title><link>https://fxtwitter.com/jimmy/status/2</link>
          <description>Author text</description>
          <pubDate>Thu, 26 Nov 2026 17:00:00 GMT</pubDate></item>
          </channel></rss>"""
        self.assertEqual([item.url for item in read_feed("Jimmy", response)], [
            "https://x.com/jimmy/status/2",
        ])
        response.url = "https://teapawt.org/jimmy/rss"
        response.content = response.content.replace(b"fxtwitter.com", b"teapawt.org")
        unavailable = requests.HTTPError(response=Mock(status_code=404))
        # 用 fxtwitter 作为首选域名的账号也必须走备用 RSS。
        source = {"name": "Jimmy", "adapter": "rss", "url": "https://fxtwitter.com/jimmy/feed.xml"}
        with patch("feedmerge.collect.fetch", side_effect=[unavailable, unavailable, response]) as fetcher:
            entries, _ = collect_one(source)
        self.assertEqual([call.args[0] for call in fetcher.call_args_list], [
            source["url"], "https://fixupx.com/jimmy/feed.xml", response.url,
        ])
        self.assertEqual([item.url for item in entries], ["https://x.com/jimmy/status/2"])

    def test_local_date_and_canonical_url(self):
        sources = [
            {"name": "甲", "adapter": "rss"},
            {"name": "乙", "adapter": "rss"},
        ]
        first = make_entry("甲", "https://fixupx.com/a/status/12?utm_source=test",
                           "日报", "摘要", "2026-11-26T16:10:00Z")
        duplicate = make_entry("乙", "https://x.com/a/status/12", "日报", "摘要",
                               "2026-11-26T17:10:00Z")
        old = make_entry("甲", "https://example.com/old", "昨日", "摘要", "2026-11-26T15:59:00Z")
        with patch("feedmerge.collect.collect_one", side_effect=[
            ([first, old], "成功"), ([duplicate], "成功")
        ]):
            entries, _ = collect(sources, date(2026, 11, 27), ZONE)
        self.assertEqual([entry.url for entry in entries], ["https://x.com/a/status/12"])

    def test_model_cannot_introduce_missing_reference(self):
        entry = make_entry("甲", "https://example.com/article", "标题", "概要", "2026-11-27T12:00:00+08:00")
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"items": [{"summary": "摘要", "id": 2}]})
        }}]}
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake-test-key"}):
            with patch("feedmerge.digest.requests.post", return_value=response):
                with self.assertRaisesRegex(ValueError, "引用超出"):
                    summarize([entry])

    def test_markdown_escapes_model_output(self):
        text = format_daily({
            "date": "2026-11-27", "collected": 1, "successful_sources": 1, "total_sources": 1,
            "items": [{"summary": "<script>x</script> [title] {{x}}",
                       "source": {"name": "甲", "url": "https://example.com/article"}}],
        })
        self.assertNotIn("<script>", text)
        self.assertNotIn("{{", text)
        self.assertIn("[甲](<https://example.com/article>)", text)

    def test_digest_regenerates_only_missing_summary(self):
        entries = [
            make_entry(f"来源 {i}", f"https://example.com/{i}", "标题", "概要",
                       "2026-11-27T12:00:00+08:00")
            for i in range(12)
        ]
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake-test-key"}):
            def generate(batch, key):
                return {
                    index: entry.source for index, entry in enumerate(batch, 1)
                    if entry != entries[2] or len(batch) == 1
                }

            with patch("feedmerge.digest.summarize_batch", side_effect=generate) as mock:
                self.assertEqual([point["summary"] for point in summarize(entries)], [
                    entry.source for entry in entries
                ])
                self.assertEqual(sorted(len(call.args[0]) for call in mock.call_args_list), [1, 2, 10])


if __name__ == "__main__":
    unittest.main()
