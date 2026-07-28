SIGN_EN_TO_RU: dict[str, str] = {
    "Ari": "Овен",
    "Tau": "Телец",
    "Gem": "Близнецы",
    "Can": "Рак",
    "Leo": "Лев",
    "Vir": "Дева",
    "Lib": "Весы",
    "Sco": "Скорпион",
    "Sag": "Стрелец",
    "Cap": "Козерог",
    "Aqu": "Водолей",
    "Pis": "Рыбы",
}

SIGN_RU_PREPOSITIONAL: dict[str, str] = {
    "Овен": "Овне",
    "Телец": "Тельце",
    "Близнецы": "Близнецах",
    "Рак": "Раке",
    "Лев": "Льве",
    "Дева": "Деве",
    "Весы": "Весах",
    "Скорпион": "Скорпионе",
    "Стрелец": "Стрельце",
    "Козерог": "Козероге",
    "Водолей": "Водолее",
    "Рыбы": "Рыбах",
}

PLANET_EN_TO_RU: dict[str, str] = {
    "Sun": "Солнце",
    "Moon": "Луна",
    "Mercury": "Меркурий",
    "Venus": "Венера",
    "Mars": "Марс",
    "Jupiter": "Юпитер",
    "Saturn": "Сатурн",
    "Uranus": "Уран",
    "Neptune": "Нептун",
    "Pluto": "Плутон",
}

ASPECT_EN_TO_RU: dict[str, str] = {
    "conjunction": "соединение",
    "sextile": "секстиль",
    "square": "квадрат",
    "trine": "трин",
    "opposition": "оппозиция",
}

TRANSIT_PLANETS = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn")
NATAL_POINTS = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn")

POINT_EN_TO_RU: dict[str, str] = {
    **PLANET_EN_TO_RU,
    "Chiron": "Хирон",
    "Mean_Lilith": "Лилит",
    "True_North_Lunar_Node": "Северный узел",
    "True_South_Lunar_Node": "Южный узел",
    "Ascendant": "Асцендент",
    "Medium_Coeli": "MC",
}

SIGN_RU_TO_MODALITY: dict[str, str] = {
    "Овен": "кардинальный",
    "Телец": "фиксированный",
    "Близнецы": "мутабельный",
    "Рак": "кардинальный",
    "Лев": "фиксированный",
    "Дева": "мутабельный",
    "Весы": "кардинальный",
    "Скорпион": "фиксированный",
    "Стрелец": "мутабельный",
    "Козерог": "кардинальный",
    "Водолей": "фиксированный",
    "Рыбы": "мутабельный",
}

# Управители домов берём традиционные: для счёта партнёрств важна планета,
# которая реально ходит по карте, а не Плутон с циклом в 248 лет.
SIGN_RU_TO_CLASSIC_RULER: dict[str, str] = {
    "Овен": "Mars",
    "Телец": "Venus",
    "Близнецы": "Mercury",
    "Рак": "Moon",
    "Лев": "Sun",
    "Дева": "Mercury",
    "Весы": "Venus",
    "Скорпион": "Mars",
    "Стрелец": "Jupiter",
    "Козерог": "Saturn",
    "Водолей": "Saturn",
    "Рыбы": "Jupiter",
}

# «Двойные» знаки: классический признак нескольких союзов на десценденте.
DOUBLE_BODIED_SIGNS: frozenset[str] = frozenset({"Близнецы", "Стрелец", "Рыбы"})

ELEMENT_EN_TO_RU: dict[str, str] = {
    "Fire": "огонь",
    "Earth": "земля",
    "Air": "воздух",
    "Water": "вода",
}

QUALITY_EN_TO_RU: dict[str, str] = {
    "Cardinal": "кардинальный",
    "Fixed": "фиксированный",
    "Mutable": "мутабельный",
}

HOUSE_NAME_TO_NUM: dict[str, int] = {
    "First_House": 1,
    "Second_House": 2,
    "Third_House": 3,
    "Fourth_House": 4,
    "Fifth_House": 5,
    "Sixth_House": 6,
    "Seventh_House": 7,
    "Eighth_House": 8,
    "Ninth_House": 9,
    "Tenth_House": 10,
    "Eleventh_House": 11,
    "Twelfth_House": 12,
}

MOON_PHASE_EN_TO_RU: dict[str, str] = {
    "New Moon": "новолуние",
    "Waxing Crescent": "растущий серп",
    "First Quarter": "первая четверть",
    "Waxing Gibbous": "растущая Луна",
    "Full Moon": "полнолуние",
    "Waning Gibbous": "убывающая Луна",
    "Last Quarter": "последняя четверть",
    "Waning Crescent": "убывающий серп",
}
