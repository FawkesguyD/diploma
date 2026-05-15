from __future__ import annotations

from nlp_parser.config import Settings
from nlp_parser.parsing import telegram as tg
from nlp_parser.parsing.registry import get_adapter


def test_tg_is_configured_requires_all_fields():
    assert tg.is_configured(Settings()) is False
    assert tg.is_configured(Settings(TG_API_ID=1)) is False
    assert (
        tg.is_configured(Settings(TG_API_ID=1, TG_API_HASH="h", TG_SESSION="s")) is True
    )


def test_normalize_handle_strips_prefixes():
    assert tg._normalize_handle("https://t.me/badaevsky") == "badaevsky"
    assert tg._normalize_handle("https://t.me/s/realty_news") == "realty_news"
    assert tg._normalize_handle("@spb_realty") == "spb_realty"
    assert tg._normalize_handle("t.me/moscow_homes/") == "moscow_homes"


def test_registry_unknown_kind():
    import pytest

    with pytest.raises(ValueError):
        get_adapter("ftp")


def test_registry_known_kinds():
    for kind in ("tg", "rss", "html", "news"):
        assert callable(get_adapter(kind))
