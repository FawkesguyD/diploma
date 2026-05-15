from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "badaevsky_complex": ("бадаевск",),
    "mortgage_rates": ("ипотек", "ставк", "цб рф", "ключевую ставк"),
    "developers": ("capital group", "застройщик", "девелопер"),
    "primary_market": ("новостройк", "старт продаж", "ввод жилья"),
    "secondary_market": ("вторичк", "вторичн"),
    "commercial_realty": ("коммерческ", "арендных ставок", "арендной став"),
    "price_trends": ("рост цен", "снижени", "цен на", "квадратного метра", "за м²", "за квартал"),
    "districts_msk": ("пресненск", "гагаринск", "раменски", "беговой"),
    "districts_spb": ("выборгск", "невски", "петроградск"),
}

_AD_KEYWORDS: tuple[str, ...] = (
    "скидк",
    "промокод",
    "регистрация по ссылке",
    "выгодные условия",
    "только сегодня",
    "купите",
    "🔥",
)

_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "снижени",
    "негативн",
    "падени",
    "обвал",
    "дешеве",
)

_POSITIVE_KEYWORDS: tuple[str, ...] = (
    "рост",
    "позитивн",
    "доступн",
    "выгодн",
    "лидером",
)

_DISTRICT_SLUGS: dict[str, str] = {
    "пресненск": "presnenskiy",
    "гагаринск": "gagarinskiy",
    "раменски": "ramenki",
    "беговой": "begovoy",
    "выборгск": "vyborgskiy",
}

_DEVELOPER_NAMES: tuple[str, ...] = ("Capital Group", "ПИК", "Самолёт")


@dataclass
class NlpResult:
    is_ad: bool
    ad_score: float
    topics: list[dict[str, Any]] = field(default_factory=list)
    sentiment_label: str = "neutral"
    sentiment_score: float = 0.5
    entities: list[dict[str, Any]] = field(default_factory=list)
    lang: str = "ru"
    summary: str | None = None


def _ad_score(text_low: str) -> float:
    hits = sum(1 for kw in _AD_KEYWORDS if kw in text_low)
    if hits == 0:
        return 0.05
    return min(0.3 + 0.2 * hits, 0.99)


def _topics(text_low: str) -> list[dict[str, Any]]:
    hits: list[tuple[str, float]] = []
    for slug, keywords in _TOPIC_KEYWORDS.items():
        matched = sum(1 for kw in keywords if kw in text_low)
        if matched == 0:
            continue
        score = min(0.4 + 0.2 * matched, 0.99)
        hits.append((slug, score))
    hits.sort(key=lambda x: x[1], reverse=True)
    return [{"slug": s, "score": round(sc, 2)} for s, sc in hits]


def _sentiment(text_low: str) -> tuple[str, float]:
    pos = sum(1 for kw in _POSITIVE_KEYWORDS if kw in text_low)
    neg = sum(1 for kw in _NEGATIVE_KEYWORDS if kw in text_low)
    if pos == 0 and neg == 0:
        return "neutral", 0.5
    if pos > neg:
        return "positive", round(min(0.55 + 0.1 * pos, 0.95), 2)
    if neg > pos:
        return "negative", round(min(0.55 + 0.1 * neg, 0.95), 2)
    return "neutral", 0.5


def _entities(text: str, text_low: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for marker, slug in _DISTRICT_SLUGS.items():
        if marker in text_low:
            out.append({"type": "location", "text": marker, "district_slug": slug})
    for dev in _DEVELOPER_NAMES:
        if dev.lower() in text_low:
            out.append({"type": "developer", "text": dev})
    return out


def analyze(text: str, *, lang_hint: str | None = None) -> NlpResult:
    text_low = text.lower()
    ad_score = _ad_score(text_low)
    is_ad = ad_score >= 0.5
    topics = _topics(text_low)
    sentiment_label, sentiment_score = _sentiment(text_low)
    entities = _entities(text, text_low)
    return NlpResult(
        is_ad=is_ad,
        ad_score=round(ad_score, 2),
        topics=topics,
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
        entities=entities,
        lang=lang_hint or "ru",
        summary=None,
    )


_MODEL_VERSIONS: dict[str, str] = {
    "classifier": "stub-v0.1",
    "ner": "stub-v0.1",
    "sentiment": "stub-v0.1",
    "ad_filter": "stub-v0.1",
}


def model_versions() -> dict[str, str]:
    return dict(_MODEL_VERSIONS)


__all__ = ["analyze", "NlpResult", "model_versions"]
