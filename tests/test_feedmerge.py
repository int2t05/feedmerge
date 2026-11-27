"""回归验证日期、来源引用和 Markdown 安全边界。"""

import json
import unittest
from datetime import date
from unittest.mock import Mock, patch

from feedmerge.__main__ import ZONE, read_sources
from feedmerge.collect import collect, make_entry
from feedmerge.digest import summarize
from feedmerge.site import format_daily


class FeedMergeTest(unittest.TestCase):
    def test_source_inventory(self):
        sources = read_sources()
        self.assertEqual(len(sources), 49)
        self.assertTrue(any(source["mode"] == "active" for source in sources))

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


if __name__ == "__main__":
    unittest.main()
