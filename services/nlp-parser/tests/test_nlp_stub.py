from __future__ import annotations

from nlp_parser.nlp import stub as nlp_stub


def test_analyze_detects_ad():
    result = nlp_stub.analyze(
        "🔥 СКИДКА 50% на курс по инвестициям в недвижимость! Промокод DIPLOM."
    )
    assert result.is_ad is True
    assert result.ad_score >= 0.5


def test_analyze_marks_non_ad_neutral_news():
    result = nlp_stub.analyze("В Москве введено 1.2 млн м² жилья в апреле.")
    assert result.is_ad is False
    assert result.ad_score < 0.5


def test_analyze_extracts_district_entities():
    result = nlp_stub.analyze(
        "В Пресненском районе зафиксирован рост спроса на двухкомнатные квартиры."
    )
    districts = [e for e in result.entities if e.get("type") == "location"]
    assert any(e.get("district_slug") == "presnenskiy" for e in districts)


def test_analyze_extracts_developer_entity():
    result = nlp_stub.analyze("Capital Group объявил о запуске нового проекта.")
    devs = [e for e in result.entities if e.get("type") == "developer"]
    assert any(e.get("text") == "Capital Group" for e in devs)


def test_analyze_sentiment_negative():
    result = nlp_stub.analyze(
        "Выборгский район Санкт-Петербурга показал снижение цен. Настроение негативное."
    )
    assert result.sentiment_label == "negative"


def test_analyze_topics_populated():
    result = nlp_stub.analyze(
        "ЦБ РФ оставил ключевую ставку. Ипотечные программы остаются доступны."
    )
    slugs = {t["slug"] for t in result.topics}
    assert "mortgage_rates" in slugs


def test_analyze_default_language():
    result = nlp_stub.analyze("Какой-то текст без ключевых слов.")
    assert result.lang == "ru"
    assert result.sentiment_label == "neutral"


def test_model_versions_returns_dict():
    versions = nlp_stub.model_versions()
    assert "classifier" in versions
    assert all(isinstance(v, str) for v in versions.values())
