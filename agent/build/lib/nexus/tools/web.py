"""Fast web search and scraping tools for research workflows."""

from __future__ import annotations

from datetime import datetime, timezone
import html
from html.parser import HTMLParser
import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from nexus.tools.workspace import get_active_workspace_path, write_workspace_file

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _tool_error(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": message}
    payload.update(extra)
    return payload


def _slugify(value: str, *, fallback: str = "page") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or fallback


def _clean_text(value: str) -> str:
    unescaped = html.unescape(_TAG_RE.sub(" ", value or ""))
    return _WHITESPACE_RE.sub(" ", unescaped).strip()


def _normalize_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" not in parsed.netloc:
        return url
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return url


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current_link: dict[str, str] | None = None
        self._active_result: dict[str, str] | None = None
        self._in_snippet = False
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        class_name = attrs_map.get("class", "")
        if tag == "a" and "result__a" in class_name and attrs_map.get("href"):
            self._current_link = {"title": "", "url": attrs_map["href"], "snippet": ""}
            self.results.append(self._current_link)
            self._active_result = self._current_link
            self._snippet_parts = []
            self._in_snippet = False
            return
        if "result__snippet" in class_name and self._active_result is not None:
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_link is not None:
            self._current_link["title"] = _clean_text(self._current_link["title"])
            self._current_link["url"] = _normalize_duckduckgo_url(self._current_link["url"])
            self._current_link = None
        elif tag in {"div", "span", "a"} and self._in_snippet and self._active_result is not None:
            if self._snippet_parts:
                self._active_result["snippet"] = _clean_text(" ".join(self._snippet_parts))
            self._in_snippet = False
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_link is not None:
            self._current_link["title"] += data
        elif self._in_snippet and self._active_result is not None:
            self._snippet_parts.append(data)


def parse_duckduckgo_results(html_text: str, *, max_results: int = 5) -> list[dict[str, str]]:
    parser = _DuckDuckGoResultParser()
    parser.feed(html_text)
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in parser.results:
        title = _clean_text(result.get("title", ""))
        url = result.get("url", "").strip()
        if not title or not url or url in seen:
            continue
        seen.add(url)
        normalized.append(
            {
                "title": title,
                "url": url,
                "snippet": _clean_text(result.get("snippet", "")),
            }
        )
        if len(normalized) >= max_results:
            break
    return normalized


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.parts.append(data)


def extract_html_title(html_text: str) -> str:
    parser = _TitleParser()
    parser.feed(html_text)
    return _clean_text(" ".join(parser.parts))


def _fallback_extract_markdown(html_text: str, *, url: str) -> str:
    title = extract_html_title(html_text) or url
    cleaned = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        " ",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body = _clean_text(cleaned)
    return f"# {title}\n\nSource: {url}\n\n{body}\n"


def extract_readable_markdown(html_text: str, *, url: str) -> str:
    try:
        import trafilatura  # type: ignore
    except Exception:
        trafilatura = None

    if trafilatura is not None:
        extracted = trafilatura.extract(
            html_text,
            url=url,
            output_format="markdown",
            include_links=True,
            include_images=False,
            favor_precision=True,
        )
        if extracted:
            return extracted.strip() + "\n"
    return _fallback_extract_markdown(html_text, url=url)


async def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search the web quickly and save normalized results into the workspace."""
    try:
        cleaned_query = " ".join((query or "").split()).strip()
        if not cleaned_query:
            return _tool_error("query is required")
        if max_results < 1:
            return _tool_error("max_results must be at least 1")

        async with httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": "CoComputer/1.0 (+https://cocomputer.local)"},
            timeout=20.0,
        ) as client:
            response = await client.get("https://duckduckgo.com/html/", params={"q": cleaned_query})
            response.raise_for_status()
            html_text = response.text

        results = parse_duckduckgo_results(html_text, max_results=max_results)
        payload = {
            "query": cleaned_query,
            "provider": "duckduckgo_html",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "result_count": len(results),
            "results": results,
            "raw_html_excerpt": html_text[:4000],
            "workspace_path": get_active_workspace_path(),
        }
        filename = f"sources/search-{_slugify(cleaned_query, fallback='search')}.json"
        write_result = await write_workspace_file(
            filename,
            json.dumps(payload, indent=2, ensure_ascii=True),
        )
        if write_result.get("error"):
            return write_result
        return {
            "query": cleaned_query,
            "results": results,
            "saved_path": f"{get_active_workspace_path()}/{filename}",
        }
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        return _tool_error(
            f"Web search failed with HTTP {status_code or 'error'}. Please retry or try a narrower query.",
            status_code=status_code,
            query=" ".join((query or "").split()).strip(),
        )
    except httpx.RequestError as exc:
        return _tool_error(
            f"Web search failed: {exc}",
            query=" ".join((query or "").split()).strip(),
        )
    except Exception as exc:
        return _tool_error(str(exc) or "Web search failed unexpectedly.")


async def scrape_web_page(url: str, output_basename: str | None = None) -> dict[str, Any]:
    """Fetch a page, extract readable text, and save it into the workspace."""
    try:
        cleaned_url = (url or "").strip()
        if not cleaned_url:
            return _tool_error("url is required")

        async with httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": "CoComputer/1.0 (+https://cocomputer.local)"},
            timeout=20.0,
        ) as client:
            response = await client.get(cleaned_url)
            response.raise_for_status()
            html_text = response.text

        title = extract_html_title(html_text) or cleaned_url
        markdown = extract_readable_markdown(html_text, url=cleaned_url)
        base = output_basename.strip() if isinstance(output_basename, str) else ""
        slug = _slugify(base or title, fallback="page")
        relative_path = f"sources/{slug}.md"
        write_result = await write_workspace_file(relative_path, markdown)
        if write_result.get("error"):
            return write_result
        return {
            "url": cleaned_url,
            "title": title,
            "content": markdown,
            "saved_path": f"{get_active_workspace_path()}/{relative_path}",
        }
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        message = (
            f"Could not scrape {cleaned_url}: site returned HTTP {status_code or 'error'}."
        )
        if status_code in {401, 403, 429}:
            message += (
                " This source blocked automated access. Try another source or use open_browser only if the page is essential."
            )
        return _tool_error(
            message,
            url=cleaned_url,
            status_code=status_code,
        )
    except httpx.RequestError as exc:
        return _tool_error(
            f"Could not scrape {cleaned_url}: {exc}",
            url=cleaned_url,
        )
    except Exception as exc:
        return _tool_error(str(exc) or "Could not scrape the page unexpectedly.", url=(url or "").strip())
