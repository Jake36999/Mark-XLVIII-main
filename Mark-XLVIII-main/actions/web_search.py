from __future__ import annotations

import html
import json
import re
import sys
import warnings
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests

warnings.filterwarnings(
    "ignore",
    message=r"This package \(`duckduckgo_search`\) has been renamed to `ddgs`!.*",
    category=RuntimeWarning,
)


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_print(message: str) -> None:
    text = str(message)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def _gemini_search(query: str) -> str:
    """The last-resort backend, which no longer exists.

    This called Gemini with google_search grounding when DuckDuckGo and the HTML
    scraper had both returned nothing. Because the credential accessor raised
    unconditionally, the user's error message for "nothing was found" became
    "Search failed: Gemini search is not linked for this session" -- a
    credential problem reported for a situation that had nothing to do with
    credentials, and one the user could not act on.

    Raising with the real reason keeps the same control flow (the caller already
    turns this into `ok: False`) while saying the true thing. Note it must NOT
    be replaced by a local model: inventing search results from model weights is
    the fabrication this system spent the cycle removing, and there would be no
    citation to check it against.
    """
    raise RuntimeError(
        f"No results found for {query!r}. The local search backends returned nothing, "
        "and there is no cloud search backend configured."
    )


def _ddg_client():
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("Install the 'ddgs' package to enable the packaged DuckDuckGo backend.") from exc
    return DDGS()


def _source_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _unwrap_ddg_url(url: str) -> str:
    try:
        from urllib.parse import parse_qs, unquote, urlparse

        parsed = urlparse(url)
        if "duckduckgo.com" in parsed.netloc and parsed.query:
            value = parse_qs(parsed.query).get("uddg", [""])[0]
            if value:
                return unquote(value)
        return url
    except Exception:
        return url


def _result_date(raw: dict[str, Any]) -> str:
    for key in ("published_at", "date", "published", "time", "timestamp"):
        value = raw.get(key)
        if value:
            return str(value)
    return ""


def _normalize_result(raw: dict[str, Any], *, backend: str, retrieved_at: str) -> dict[str, str]:
    title = str(raw.get("title") or raw.get("heading") or "").strip()
    snippet = str(raw.get("snippet") or raw.get("body") or raw.get("description") or "").strip()
    url = str(raw.get("url") or raw.get("href") or "").strip()
    source = str(raw.get("source") or raw.get("publisher") or raw.get("provider") or "").strip()
    return {
        "title": title,
        "snippet": snippet,
        "url": url,
        "source": source,
        "published_at": _result_date(raw),
        "retrieved_at": retrieved_at,
        "backend": backend,
    }


def _dedupe_results(results: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    deduped = []
    for result in results:
        key = (result.get("url") or result.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _ddg_search(query: str, max_results: int = 6) -> list[dict[str, str]]:
    retrieved_at = _now_iso()
    results = []
    try:
        with _ddg_client() as ddgs:
            for raw in ddgs.text(query, max_results=max_results):
                results.append(_normalize_result(raw, backend="ddg_text", retrieved_at=retrieved_at))
    except Exception:
        return []
    return _dedupe_results(results)


def _ddg_news(query: str, max_results: int = 8) -> list[dict[str, str]]:
    retrieved_at = _now_iso()
    results = []
    try:
        with _ddg_client() as ddgs:
            for raw in ddgs.news(query, max_results=max_results):
                results.append(_normalize_result(raw, backend="ddg_news", retrieved_at=retrieved_at))
    except Exception as exc:
        _safe_print(f"[WebSearch] DDG news failed ({exc}); falling back to text search")
        results = _ddg_search(query, max_results=max_results)
    return _dedupe_results(results)


def _html_soup(url: str):
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return None
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except Exception as exc:
        _safe_print(f"[WebSearch] HTML fallback failed for {url}: {exc}")
        return None


def _bing_html_search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    retrieved_at = _now_iso()
    soup = _html_soup(f"https://www.bing.com/search?q={quote_plus(query)}")
    if not soup:
        return []
    results: list[dict[str, str]] = []
    for item in soup.select("li.b_algo"):
        link = item.select_one("h2 a")
        if not link:
            continue
        url = str(link.get("href") or "").strip()
        title = _strip_html(link.get_text(" ", strip=True))
        snippet_el = item.select_one("p")
        snippet = _strip_html(snippet_el.get_text(" ", strip=True) if snippet_el else "")
        if title and url.startswith(("http://", "https://")):
            results.append(
                {
                    "title": title,
                    "snippet": snippet,
                    "url": url,
                    "source": _source_from_url(url),
                    "published_at": "",
                    "retrieved_at": retrieved_at,
                    "backend": "bing_html",
                }
            )
        if len(results) >= max_results:
            break
    return _dedupe_results(results)


def _ddg_html_search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    retrieved_at = _now_iso()
    soup = _html_soup(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}")
    if not soup:
        return []
    results: list[dict[str, str]] = []
    for item in soup.select(".result"):
        link = item.select_one("a.result__a")
        if not link:
            continue
        url = _unwrap_ddg_url(str(link.get("href") or "").strip())
        title = _strip_html(link.get_text(" ", strip=True))
        snippet_el = item.select_one(".result__snippet")
        snippet = _strip_html(snippet_el.get_text(" ", strip=True) if snippet_el else "")
        if title and url.startswith(("http://", "https://")):
            results.append(
                {
                    "title": title,
                    "snippet": snippet,
                    "url": url,
                    "source": _source_from_url(url),
                    "published_at": "",
                    "retrieved_at": retrieved_at,
                    "backend": "ddg_html",
                }
            )
        if len(results) >= max_results:
            break
    return _dedupe_results(results)


def _github_repo_search(query: str, max_results: int = 6) -> list[dict[str, str]]:
    retrieved_at = _now_iso()
    try:
        response = requests.get(
            "https://api.github.com/search/repositories",
            params={
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": max(1, min(10, max_results)),
            },
            timeout=15,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "JARVIS-MARK-XLVIII",
            },
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        _safe_print(f"[WebSearch] GitHub repository search failed: {exc}")
        return []
    results: list[dict[str, str]] = []
    for item in data.get("items", [])[:max_results]:
        url = str(item.get("html_url") or "").strip()
        full_name = str(item.get("full_name") or item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        language = str(item.get("language") or "").strip()
        stars = item.get("stargazers_count")
        details = []
        if description:
            details.append(description)
        if language:
            details.append(f"Language: {language}")
        if stars is not None:
            details.append(f"Stars: {stars}")
        if full_name and url:
            results.append(
                {
                    "title": full_name,
                    "snippet": " | ".join(details),
                    "url": url,
                    "source": "GitHub",
                    "published_at": "",
                    "retrieved_at": retrieved_at,
                    "backend": "github_repositories",
                }
            )
    return _dedupe_results(results)


def _html_search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    results = _bing_html_search(query, max_results=max_results)
    if len(results) < max_results:
        results.extend(_ddg_html_search(query, max_results=max_results - len(results)))
    return _dedupe_results(results)[:max_results]


def _is_open_source_query(query: str) -> bool:
    lowered = (query or "").lower()
    return any(token in lowered for token in ("open source", "opensource", "github", "repository", "resources", "toolkit", "library"))


def _expanded_open_source_queries(query: str) -> list[str]:
    base = (query or "").strip()
    lowered = base.lower()
    queries: list[str] = []
    if ("wifi" in lowered or "wi-fi" in lowered) and (
        "csi" in lowered or "channel state information" in lowered or "sensing" in lowered
    ):
        queries.extend(
            [
                "wifi CSI channel state information open source",
                "802.11n CSI tool GitHub",
                "Intel 5300 CSI tool GitHub",
                "WiFi sensing channel state information GitHub",
            ]
        )
    if base:
        queries.append(base)
    deduped: list[str] = []
    seen = set()
    for item in queries:
        key = item.lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped or [base]


def _open_source_research_results(query: str, max_results: int = 8) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for expanded in _expanded_open_source_queries(query):
        if len(results) >= max_results:
            break
        github_query = expanded
        github_query = re.sub(r"\b(open source|resources?|toolkits?|libraries?)\b", " ", github_query, flags=re.I)
        github_query = re.sub(r"\s+", " ", github_query).strip()
        results.extend(_github_repo_search(github_query or expanded, max_results=max(1, max_results - len(results))))
        if len(results) >= max_results:
            break
        results.extend(_html_search(expanded, max_results=max(1, max_results - len(results))))
    return _dedupe_results(results)[:max_results]


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_rss_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return value


def _google_news_rss(query: str, max_results: int = 8, *, date_from: str = "", date_to: str = "") -> list[dict[str, str]]:
    retrieved_at = _now_iso()
    rss_query = (query or "").strip()
    if date_from or date_to:
        rss_query = f"{rss_query} when:2d"
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(rss_query)}&hl=en-GB&gl=GB&ceid=GB:en"
    )
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; JARVIS/1.0)"},
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as exc:
        _safe_print(f"[WebSearch] Google News RSS failed: {exc}")
        return []

    results = []
    for item in root.findall("./channel/item")[:max_results]:
        source_el = item.find("source")
        source = ""
        if source_el is not None and source_el.text:
            source = source_el.text.strip()
        link = (item.findtext("link") or "").strip()
        source_url = source_el.get("url", "").strip() if source_el is not None else ""
        results.append(
            {
                "title": _strip_html(item.findtext("title") or "Untitled news result"),
                "snippet": _strip_html(item.findtext("description") or ""),
                "url": link or source_url,
                "source": source,
                "published_at": _parse_rss_date(item.findtext("pubDate") or ""),
                "retrieved_at": retrieved_at,
                "backend": "google_news_rss",
            }
        )
    return _dedupe_results(results)


def _is_news_like_result(item: dict[str, str]) -> bool:
    backend = str(item.get("backend") or "")
    return backend in {"ddg_news", "google_news_rss"} or bool(item.get("source") or item.get("published_at"))


def _date_scoped_query(query: str, date_from: str = "", date_to: str = "", mode: str = "search") -> str:
    query = (query or "").strip()
    if not date_from and not date_to:
        return query
    if date_from and date_to and date_from != date_to:
        date_phrase = f"published between {date_from} and {date_to}"
    else:
        date_phrase = f"published {date_from or date_to}"
    if mode == "news":
        return f"{query} {date_phrase}".strip()
    return f"{query} {date_phrase}".strip()


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _coerce_max_results(value: Any, default: int) -> int:
    try:
        return max(1, min(25, int(value)))
    except Exception:
        return default


def _primary_domain_hints(query: str) -> list[str]:
    lowered = (query or "").lower()
    hints: list[str] = []
    if "lm studio" in lowered or "lmstudio" in lowered:
        hints.append("lmstudio.ai")
    if "llama.cpp" in lowered or "llama cpp" in lowered:
        hints.append("github.com/ggml-org/llama.cpp")
    if any(token in lowered for token in ("multi-gpu", "dual-gpu", "dual gpu", "nvidia", "gtx")):
        hints.append("developer.nvidia.com")
    if any(token in lowered for token in ("vulkan", "mixed-vendor", "mixed vendor", "llama.cpp", "llama cpp")):
        hints.append("docs.vulkan.org")
    if "dagster" in lowered:
        hints.append("docs.dagster.io")
    if "openai" in lowered:
        hints.append("platform.openai.com")
    return hints


def _primary_search_queries(query: str, domain: str) -> list[str]:
    lowered = (query or "").lower()
    if domain == "lmstudio.ai":
        return [
            "site:lmstudio.ai/docs/developer/rest models load unload",
            "site:lmstudio.ai/docs/developer/core ttl auto evict",
            "site:lmstudio.ai multi-GPU controls",
        ]
    if domain == "github.com/ggml-org/llama.cpp":
        return [
            "site:github.com/ggml-org/llama.cpp server split-mode tensor-split",
            "site:github.com/ggml-org/llama.cpp feature matrix Vulkan multi GPU",
        ]
    if domain == "developer.nvidia.com":
        return ["site:developer.nvidia.com Vulkan multi GPU memory telemetry"]
    if domain == "docs.vulkan.org":
        return ["site:docs.vulkan.org device groups memory multi GPU"]
    if domain == "docs.dagster.io":
        return ["site:docs.dagster.io assets jobs resources sensors schedules partitions"]
    if domain == "platform.openai.com":
        return ["site:platform.openai.com/docs API models responses"]
    entity_terms = " ".join(re.findall(r"[A-Za-z0-9_.+-]+", lowered)[:12])
    return [f"site:{domain} {entity_terms}".strip()]


def _primary_research_results(query: str, max_results: int, preferred_domains: Any = None) -> list[dict[str, Any]]:
    domains = []
    if isinstance(preferred_domains, str):
        domains.extend(part.strip() for part in preferred_domains.split(",") if part.strip())
    elif isinstance(preferred_domains, list):
        domains.extend(str(part).strip() for part in preferred_domains if str(part).strip())
    if re.search(r"\bprimary sources?\b|\bofficial (?:docs|documentation|sources?)\b", query, flags=re.I):
        domains.extend(_primary_domain_hints(query))
    domains = list(dict.fromkeys(domains))[:4]
    if not domains:
        return []
    per_query = max(1, min(3, max_results // max(1, len(domains)) + 1))
    results: list[dict[str, Any]] = []
    for domain in domains:
        for scoped_query in _primary_search_queries(query, domain):
            results.extend(_ddg_search(scoped_query, max_results=per_query))
    return _dedupe_results(results)[:max_results]


def _format_structured(payload: dict[str, Any]) -> str:
    query = payload.get("query") or ""
    mode = payload.get("mode") or "search"
    results = payload.get("results") or []
    if not results:
        return str(payload.get("message") or f"No results found for: {query}")

    heading = "Latest news" if mode == "news" else "Search results"
    if payload.get("date_from") or payload.get("date_to"):
        date_label = payload.get("date_from") or payload.get("date_to")
        if payload.get("date_to") and payload.get("date_to") != date_label:
            date_label = f"{date_label} to {payload.get('date_to')}"
        heading = f"{heading} ({date_label})"

    lines = [f"{heading}: {query}", ""]
    for index, item in enumerate(results, 1):
        title = item.get("title") or "Untitled result"
        source = f" [{item.get('source')}]" if item.get("source") else ""
        published = f" ({item.get('published_at')})" if item.get("published_at") else ""
        lines.append(f"{index}. {title}{source}{published}")
        if item.get("snippet"):
            lines.append(f"   {item['snippet'][:240]}")
        if item.get("url"):
            lines.append(f"   Source: {item['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def structured_web_search(parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(parameters or {})
    query = str(params.get("query") or "").strip()
    mode = str(params.get("mode") or "search").lower().strip()
    items = params.get("items") or []
    aspect = str(params.get("aspect") or "general").strip() or "general"
    max_results = _coerce_max_results(params.get("max_results"), 8 if mode == "news" else 6)
    date_from = str(params.get("date_from") or "").strip()
    date_to = str(params.get("date_to") or "").strip()
    require_citations = _coerce_bool(params.get("require_citations"), False)
    preferred_domains = params.get("preferred_domains") or []
    retrieved_at = _now_iso()

    if items and mode not in {"compare"}:
        mode = "compare"
    if not query and not items:
        return {
            "ok": False,
            "mode": mode,
            "query": query,
            "results": [],
            "retrieved_at": retrieved_at,
            "message": "Please provide a search query.",
        }

    scoped_query = _date_scoped_query(query, date_from, date_to, mode=mode)
    payload: dict[str, Any] = {
        "ok": True,
        "mode": mode,
        "query": query or ", ".join(items),
        "effective_query": scoped_query or query,
        "date_from": date_from,
        "date_to": date_to,
        "retrieved_at": retrieved_at,
        "require_citations": require_citations,
        "results": [],
        "text": "",
        "message": "",
    }

    try:
        if mode == "compare" and items:
            compare_query = f"Compare {', '.join(map(str, items))} in terms of {aspect}"
            results = _ddg_search(compare_query, max_results=max_results)
            if not results:
                results = _html_search(compare_query, max_results=max_results)
            payload["results"] = results
            payload["text"] = _format_structured(payload)
            return payload

        if mode == "news":
            results = _ddg_news(scoped_query or query, max_results=max_results)
            cited = [item for item in results if item.get("url") and _is_news_like_result(item)]
            if require_citations and not cited:
                rss_results = _google_news_rss(query, max_results=max_results, date_from=date_from, date_to=date_to)
                if rss_results:
                    payload["date_scope_note"] = (
                        "DuckDuckGo news returned no cited news articles; used Google News RSS "
                        "fallback over the last 48 hours."
                    )
                    cited = [item for item in rss_results if item.get("url")]
            if require_citations and not cited:
                payload.update(
                    {
                        "ok": False,
                        "results": [],
                        "message": f"No cited articles found for: {query}",
                    }
                )
                return payload
            payload["results"] = cited if require_citations else results
            payload["text"] = _format_structured(payload)
            return payload

        if mode == "research":
            primary_results = _primary_research_results(query, max_results, preferred_domains)
            results = _ddg_search(scoped_query or query, max_results=max_results)
            if primary_results:
                results = _dedupe_results(primary_results + results)[:max_results]
            if _is_open_source_query(query):
                open_source_results = _open_source_research_results(query, max_results=max_results)
                results = _dedupe_results(open_source_results + results)[:max_results]
            if not results:
                results = _html_search(scoped_query or query, max_results=max_results)
            if results:
                payload["results"] = results
                payload["text"] = _format_structured(payload)
                return payload
            if require_citations:
                payload.update({"ok": False, "message": f"No cited research results found for: {query}"})
                return payload
            research_query = (
                f"Comprehensive, detailed explanation of: {query}. "
                "Include background context, key facts, current state, and important nuances."
            )
            payload["text"] = _gemini_search(research_query)
            return payload

        if mode == "price":
            results = _ddg_search(f"{query} price buy", max_results=max_results)
            if not results:
                results = _html_search(f"{query} price buy", max_results=max_results)
            payload["results"] = results
            payload["text"] = _format_structured(payload)
            return payload

        results = _ddg_search(scoped_query or query, max_results=max_results)
        if not results:
            results = _html_search(scoped_query or query, max_results=max_results)
        if _is_open_source_query(query):
            open_source_results = _open_source_research_results(query, max_results=max_results)
            results = _dedupe_results(open_source_results + results)[:max_results]
        if results:
            payload["results"] = results
            payload["text"] = _format_structured(payload)
            return payload
        if require_citations:
            payload.update({"ok": False, "message": f"No cited results found for: {query}"})
            return payload
        payload["text"] = _gemini_search(query)
        return payload
    except Exception as exc:
        _safe_print(f"[WebSearch] search backend failed: {exc}")
        payload.update({"ok": False, "message": f"Search failed: {exc}", "results": []})
        return payload


def _search(query: str) -> str:
    return structured_web_search({"query": query, "mode": "search"}).get("text") or f"No results found for: {query}"


def _news(query: str) -> str:
    payload = structured_web_search({"query": query, "mode": "news", "max_results": 8})
    return payload.get("text") or payload.get("message") or f"No news found for: {query}"


def _research(query: str) -> str:
    payload = structured_web_search({"query": query, "mode": "research", "max_results": 10})
    return payload.get("text") or payload.get("message") or f"No research results found for: {query}"


def _price(query: str) -> str:
    payload = structured_web_search({"query": query, "mode": "price", "max_results": 6})
    return payload.get("text") or payload.get("message") or f"No prices found for: {query}"


def _compare(items: list[str], aspect: str) -> str:
    payload = structured_web_search({"items": items, "mode": "compare", "aspect": aspect, "max_results": 6})
    return payload.get("text") or payload.get("message") or "No comparison results found."


def _gemini_headlines(n: int = 5) -> tuple[list[str], str]:
    """
    Fetches current headlines via Gemini grounded search.
    Returns (headline_list, raw_text_for_display).
    """
    try:
        raw = _gemini_search(f"Current world news: {n} headlines. Numbered list, titles only.")
    except Exception as exc:
        _safe_print(f"[WebSearch] Gemini headlines failed: {exc}")
        raw = _news("top world news today")

    headlines = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or not re.match(r"^[\d]+[.\)\-]", line):
            continue
        clean = re.sub(r"^[\d]+[.\)\-]\s*", "", line)
        clean = re.sub(r"^\*+\s*", "", clean).strip()
        if clean and len(clean) > 10:
            headlines.append(clean)
    return headlines[:n], raw.strip()


def web_search(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = dict(parameters or {})
    query = str(params.get("query") or "").strip()
    mode = str(params.get("mode") or "search").lower().strip()
    items = params.get("items", [])
    output_format = str(params.get("output_format") or params.get("format") or "text").lower().strip()

    if not query and not items:
        return "Please provide a search query."

    if player:
        player.write_log(f"[Search:{mode}] {query or ', '.join(map(str, items))}")

    _safe_print(f"[WebSearch] mode={mode!r} query={query!r}")
    payload = structured_web_search(params)
    if output_format in {"json", "structured"}:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if payload.get("text"):
        return str(payload["text"])
    if payload.get("message"):
        return str(payload["message"])
    return f"No results found for: {query or ', '.join(map(str, items))}"
