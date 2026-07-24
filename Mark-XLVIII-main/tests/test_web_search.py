import io
import json
import unittest
from unittest import mock

from actions import web_search as ws


class FakeDDG:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def news(self, query, max_results=8):
        return [
            {
                "title": "AI Lab Ships Safer Tool Use Model",
                "body": "The release focuses on tool routing, citations, and agent safety.",
                "url": "https://example.com/ai-tool-use",
                "source": "Example News",
                "date": "2026-07-20",
            },
            {
                "title": "Duplicate",
                "body": "Duplicate should be deduped by URL.",
                "url": "https://example.com/ai-tool-use",
                "source": "Example News",
                "date": "2026-07-20",
            },
        ][:max_results]

    def text(self, query, max_results=6):
        return [
            {
                "title": "Research Result",
                "body": "Grounded result for text search.",
                "href": "https://example.com/research",
            }
        ][:max_results]


class QuietDDG(FakeDDG):
    def news(self, query, max_results=8):
        return [{"title": "Uncited", "body": "No URL was returned."}]


class StrictCp1252Stdout(io.StringIO):
    encoding = "cp1252"

    def write(self, value):
        value.encode(self.encoding)
        return super().write(value)


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.content = text.encode("utf-8")
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} error")


class WebSearchTests(unittest.TestCase):
    def test_primary_research_uses_short_entity_specific_official_queries(self):
        from actions import web_search as ws

        queries = []

        def fake_search(query, max_results=6):
            queries.append(query)
            domain = "lmstudio.ai" if "lmstudio.ai" in query else "github.com"
            return [
                {
                    "title": query,
                    "snippet": "Official documentation result.",
                    "url": f"https://{domain}/official-{len(queries)}",
                    "source": domain,
                    "published_at": "",
                    "retrieved_at": "2026-07-21T10:00:00Z",
                    "backend": "test",
                }
            ]

        long_query = (
            "Assess LM Studio and llama.cpp mixed-vendor dual-GPU orchestration using current primary sources, "
            "including model loading, telemetry, concurrency, and recovery."
        )
        with mock.patch("actions.web_search._ddg_search", side_effect=fake_search):
            results = ws._primary_research_results(long_query, 12)

        self.assertGreaterEqual(len(results), 4)
        self.assertTrue(any("ttl auto evict" in query for query in queries))
        self.assertTrue(any("split-mode tensor-split" in query for query in queries))
        self.assertTrue(all(len(query) < len(long_query) for query in queries))

    def test_structured_news_returns_cited_records_with_dates(self):
        with mock.patch("actions.web_search._ddg_client", return_value=FakeDDG()):
            payload = ws.structured_web_search(
                {
                    "query": "AI news",
                    "mode": "news",
                    "date_from": "2026-07-20",
                    "date_to": "2026-07-20",
                    "max_results": 8,
                    "require_citations": True,
                }
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "news")
        self.assertEqual(payload["date_from"], "2026-07-20")
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["url"], "https://example.com/ai-tool-use")
        self.assertEqual(payload["results"][0]["backend"], "ddg_news")
        self.assertIn("Source: https://example.com/ai-tool-use", payload["text"])

    def test_json_output_preserves_citations(self):
        with mock.patch("actions.web_search._ddg_client", return_value=FakeDDG()):
            raw = ws.web_search(
                {
                    "query": "AI news",
                    "mode": "news",
                    "date_from": "2026-07-20",
                    "require_citations": True,
                    "output_format": "json",
                }
            )

        payload = json.loads(raw)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["results"][0]["source"], "Example News")
        self.assertEqual(payload["results"][0]["url"], "https://example.com/ai-tool-use")

    def test_require_citations_rejects_uncited_news(self):
        with mock.patch("actions.web_search._ddg_client", return_value=QuietDDG()), \
             mock.patch("actions.web_search.requests.get", side_effect=RuntimeError("rss offline")):
            payload = ws.structured_web_search(
                {"query": "AI news", "mode": "news", "require_citations": True}
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["results"], [])
        self.assertIn("No cited articles", payload["message"])

    def test_google_news_rss_fallback_recovers_when_ddg_news_is_uncited(self):
        rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel>
          <item>
            <title>Auditors tell UK government to do the math before banking on AI savings - The Register</title>
            <link>https://news.google.com/rss/articles/example?oc=5</link>
            <pubDate>Mon, 20 Jul 2026 08:30:00 GMT</pubDate>
            <source url="https://www.theregister.com">The Register</source>
            <description>&lt;p&gt;Government AI savings claims face scrutiny.&lt;/p&gt;</description>
          </item>
        </channel></rss>
        """

        with mock.patch("actions.web_search._ddg_client", return_value=QuietDDG()), \
             mock.patch("actions.web_search.requests.get", return_value=FakeResponse(rss)):
            payload = ws.structured_web_search(
                {
                    "query": "AI and UK politics today",
                    "mode": "news",
                    "date_from": "2026-07-21",
                    "date_to": "2026-07-21",
                    "require_citations": True,
                }
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["results"][0]["backend"], "google_news_rss")
        self.assertEqual(payload["results"][0]["source"], "The Register")
        self.assertIn("last 48 hours", payload["date_scope_note"])
        self.assertIn("Source: https://news.google.com/rss/articles/example?oc=5", payload["text"])

    def test_research_fallback_uses_cited_html_and_github_without_cloud_key(self):
        github_result = [
            {
                "title": "wifi-sensing/csi-toolkit",
                "snippet": "Open source CSI analysis toolkit.",
                "url": "https://github.com/wifi-sensing/csi-toolkit",
                "source": "GitHub",
                "published_at": "",
                "retrieved_at": "2026-07-21T10:00:00Z",
                "backend": "github_repositories",
            }
        ]
        html_result = [
            {
                "title": "WiFi CSI Resource Index",
                "snippet": "A cited index of WiFi sensing projects.",
                "url": "https://example.com/wifi-csi",
                "source": "example.com",
                "published_at": "",
                "retrieved_at": "2026-07-21T10:00:00Z",
                "backend": "bing_html",
            }
        ]

        with mock.patch("actions.web_search._ddg_search", return_value=[]), \
             mock.patch("actions.web_search._html_search", return_value=html_result), \
             mock.patch("actions.web_search._github_repo_search", return_value=github_result), \
             mock.patch("actions.web_search._gemini_search", side_effect=AssertionError("cloud fallback should not run")):
            payload = ws.structured_web_search(
                {
                    "query": "wifi sensing CSI analysis open source resources",
                    "mode": "research",
                    "max_results": 5,
                    "require_citations": True,
                }
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["results"][0]["backend"], "github_repositories")
        self.assertIn("https://github.com/wifi-sensing/csi-toolkit", payload["text"])
        self.assertIn("https://example.com/wifi-csi", payload["text"])

    def test_safe_print_survives_cp1252_stdout(self):
        stream = StrictCp1252Stdout()

        with mock.patch("actions.web_search.sys.stdout", stream):
            ws._safe_print("debug rocket \U0001f680")

        self.assertIn("debug rocket", stream.getvalue())
        self.assertIn("?", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
