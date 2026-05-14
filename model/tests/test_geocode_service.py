from model.apps.geocode.service import _build_nominatim_queries


def test_build_nominatim_queries_for_moscow_address_with_admin_parts() -> None:
    queries = _build_nominatim_queries(
        "Москва, СЗАО, р-н Южное Тушино, Строительный проезд, 2С1"
    )

    assert queries == (
        "Москва, СЗАО, р-н Южное Тушино, Строительный проезд, 2С1",
        "Строительный проезд, 2С1, Москва, Россия",
        "Строительный проезд, 2 строение 1, Москва, Россия",
        "Строительный проезд, 2, Москва, Россия",
        "Строительный проезд, 2С1, Южное Тушино, Москва, Россия",
    )


def test_build_nominatim_queries_keeps_prefixed_house_format() -> None:
    queries = _build_nominatim_queries("Москва, Тверская улица, д. 1")

    assert queries == (
        "Москва, Тверская улица, д. 1",
        "Тверская улица, 1, Москва, Россия",
    )
