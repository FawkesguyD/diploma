from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import httpx

from nlp_parser.config import Settings
from nlp_parser.parsing import rss

SOURCE_ID = UUID("00000000-0000-0000-0000-000000000030")

_RSS_BODY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>RBC Realty</title>
  <link>https://rbc.ru/realty</link>
  <language>ru</language>
  <item>
    <title>Ввод жилья в Москве вырос</title>
    <link>https://rbc.ru/realty/2026/05/14/aaa</link>
    <guid>rbc-aaa</guid>
    <pubDate>Wed, 14 May 2026 10:00:00 +0000</pubDate>
    <description><![CDATA[<p>В Москве за апрель введено <b>1.2 млн</b> м&#178; жилья.</p>]]></description>
    <author>РБК</author>
  </item>
  <item>
    <title>Ставка ЦБ</title>
    <link>https://rbc.ru/realty/2026/05/13/bbb</link>
    <guid>rbc-bbb</guid>
    <pubDate>Tue, 13 May 2026 12:00:00 +0000</pubDate>
    <description>ЦБ оставил ставку на уровне 16%.</description>
  </item>
</channel></rss>
""".encode("utf-8")


def _run(coro):
    return asyncio.run(coro)


def _mock_transport(body: bytes) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"Content-Type": "application/rss+xml"})

    return httpx.MockTransport(handler)


def _patch_client(monkeypatch, body: bytes):
    transport = _mock_transport(body)
    original = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(rss.httpx, "AsyncClient", fake_client)


def test_rss_parses_entries(monkeypatch):
    settings = Settings()
    _patch_client(monkeypatch, _RSS_BODY)
    docs = _run(rss.parse_source(SOURCE_ID, url_or_handle="https://rbc.ru/feed", settings=settings))
    assert len(docs) == 2
    assert {d["external_id"] for d in docs} == {"rss:rbc-aaa", "rss:rbc-bbb"}
    for doc in docs:
        assert doc["source_id"] == str(SOURCE_ID)
        assert doc["channel_kind"] == "rss"
        assert doc["channel_site"] == "rbc.ru"
        assert doc["text"]
        assert isinstance(doc["published_at"], datetime)


def test_rss_filters_since(monkeypatch):
    settings = Settings()
    _patch_client(monkeypatch, _RSS_BODY)
    since = datetime(2026, 5, 14, 0, 0, tzinfo=timezone.utc)
    docs = _run(
        rss.parse_source(
            SOURCE_ID, url_or_handle="https://rbc.ru/feed", settings=settings, since=since
        )
    )
    assert len(docs) == 1
    assert docs[0]["external_id"] == "rss:rbc-aaa"


def test_rss_strips_html_in_description(monkeypatch):
    settings = Settings()
    _patch_client(monkeypatch, _RSS_BODY)
    docs = _run(rss.parse_source(SOURCE_ID, url_or_handle="https://rbc.ru/feed", settings=settings))
    text = next(d["text"] for d in docs if d["external_id"] == "rss:rbc-aaa")
    assert "<b>" not in text
    assert "1.2 млн" in text
