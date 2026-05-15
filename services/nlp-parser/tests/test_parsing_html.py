from __future__ import annotations

import asyncio
from uuid import UUID

import httpx

from nlp_parser.config import Settings
from nlp_parser.parsing import html as html_adapter

SOURCE_ID = UUID("00000000-0000-0000-0000-000000000040")

_ARTICLE_HTML = """<!doctype html><html lang="ru"><head>
<title>Заголовок статьи</title>
<meta property="article:published_time" content="2026-05-14T10:00:00+00:00" />
<meta name="author" content="Автор Тест" />
</head><body>
<article>
<h1>Заголовок статьи</h1>
<p>Это первый абзац статьи о недвижимости в Москве. Capital Group объявил о новом проекте на Беговой.</p>
<p>Второй абзац: цена квадратного метра выросла на 4.5%.</p>
</article>
</body></html>"""

_INDEX_HTML = """<!doctype html><html><body>
<a href="/article/1">A1</a>
<a href="/article/2">A2</a>
<a href="https://other.example.com/foo">Foreign</a>
</body></html>"""


def _run(coro):
    return asyncio.run(coro)


def _transport_for_routes(routes: dict[str, bytes]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(str(request.url)) or routes.get(request.url.path)
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, content=body, headers={"Content-Type": "text/html; charset=utf-8"})

    return httpx.MockTransport(handler)


def _patch_client(monkeypatch, transport: httpx.MockTransport) -> None:
    original = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(html_adapter.httpx, "AsyncClient", fake_client)


def test_html_single_article(monkeypatch):
    settings = Settings()
    transport = _transport_for_routes(
        {"https://news.example.com/a": _ARTICLE_HTML.encode("utf-8")}
    )
    _patch_client(monkeypatch, transport)
    docs = _run(
        html_adapter.parse_source(
            SOURCE_ID,
            url_or_handle="https://news.example.com/a",
            settings=settings,
            config={"mode": "single"},
        )
    )
    assert len(docs) == 1
    doc = docs[0]
    assert doc["channel_kind"] == "html"
    assert doc["channel_site"] == "news.example.com"
    assert "Заголовок статьи" in doc["text"]
    assert "Capital Group" in doc["text"]
    assert doc["external_id"].startswith("html:")


def test_html_index_discovers_articles(monkeypatch):
    settings = Settings()
    routes = {
        "https://news.example.com/": _INDEX_HTML.encode("utf-8"),
        "/article/1": _ARTICLE_HTML.encode("utf-8"),
        "/article/2": _ARTICLE_HTML.replace(
            "Заголовок статьи", "Вторая статья"
        ).encode("utf-8"),
    }
    transport = _transport_for_routes(routes)
    _patch_client(monkeypatch, transport)
    docs = _run(
        html_adapter.parse_source(
            SOURCE_ID,
            url_or_handle="https://news.example.com/",
            settings=settings,
            config={"mode": "index", "max_articles": 5},
        )
    )
    assert len(docs) == 2
    urls = {d["url"] for d in docs}
    assert urls == {
        "https://news.example.com/article/1",
        "https://news.example.com/article/2",
    }
    assert not any("other.example.com" in d["url"] for d in docs)


def test_html_skips_pages_without_text(monkeypatch):
    settings = Settings()
    transport = _transport_for_routes(
        {"https://news.example.com/empty": b"<html><body></body></html>"}
    )
    _patch_client(monkeypatch, transport)
    docs = _run(
        html_adapter.parse_source(
            SOURCE_ID,
            url_or_handle="https://news.example.com/empty",
            settings=settings,
            config={"mode": "single"},
        )
    )
    assert docs == []
