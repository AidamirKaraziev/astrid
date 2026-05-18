from astra.places.ru_admin1 import RU_ADMIN1_RU, admin1_name_ru


def test_krasnodar_krai_code_38() -> None:
    assert RU_ADMIN1_RU["38"] == "Краснодарский край"
    assert RU_ADMIN1_RU["21"] == "Ивановская область"
    assert admin1_name_ru("38") == "Краснодарский край"


def test_ivanovo_not_krasnodar() -> None:
    assert admin1_name_ru("21") == "Ивановская область"
    assert admin1_name_ru("38") != "Ивановская область"
