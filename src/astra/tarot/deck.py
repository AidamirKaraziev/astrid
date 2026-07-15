"""Колода таро: 78 карт — 22 старших аркана + 56 младших (deck_minor/).

astro_affinity — традиционные планетарно-знаковые соответствия арканов
(у младших — деканы Golden Dawn), связка с транзитами в интерпретации.
keywords_reversed заполнены у всех карт; механика перевёрнутых включается этапом 2.
"""

from __future__ import annotations

from astra.tarot.card import ARCANA_LABELS_RU, Arcana, TarotCard

__all__ = ["ARCANA_LABELS_RU", "Arcana", "TarotCard", "MAJOR_ARCANA", "DECK", "card_by_id"]

MAJOR_ARCANA: tuple[TarotCard, ...] = (
    TarotCard(
        id="major_00", name_ru="Шут", arcana="major", number=0, emoji="🃏",
        keywords=("начало", "спонтанность", "доверие пути"),
        astro_affinity="Уран",
        voice="Шагни — дорога появится под ногой. Не считай ступени, которых ещё нет.",
        keywords_reversed=("безрассудство", "бег от обязательств"),
    ),
    TarotCard(
        id="major_01", name_ru="Маг", arcana="major", number=1, emoji="🎩",
        keywords=("воля", "инструменты под рукой", "слово создаёт"),
        astro_affinity="Меркурий",
        voice="Всё нужное уже на твоём столе. Назови намерение вслух — и начни.",
        keywords_reversed=("манипуляция", "распылённая воля"),
    ),
    TarotCard(
        id="major_02", name_ru="Верховная Жрица", arcana="major", number=2, emoji="🌒",
        keywords=("интуиция", "тишина", "скрытое знание"),
        astro_affinity="Луна",
        voice="Ответ уже внутри, он просто тише чужих голосов. Не спрашивай — прислушайся.",
        keywords_reversed=("заглушённая интуиция", "секреты во вред"),
    ),
    TarotCard(
        id="major_03", name_ru="Императрица", arcana="major", number=3, emoji="🌾",
        keywords=("плодородие", "забота", "рост без спешки"),
        astro_affinity="Венера",
        voice="Не подгоняй растущее. Полей — и отойди от грядки.",
        keywords_reversed=("гиперопека", "творческий застой"),
    ),
    TarotCard(
        id="major_04", name_ru="Император", arcana="major", number=4, emoji="🏛",
        keywords=("порядок", "границы", "ответственность"),
        astro_affinity="Овен",
        voice="Правила, которые ты установишь сегодня, будут защищать тебя завтра.",
        keywords_reversed=("жёсткость", "контроль ради контроля"),
    ),
    TarotCard(
        id="major_05", name_ru="Иерофант", arcana="major", number=5, emoji="🗝",
        keywords=("традиция", "наставник", "проверенный путь"),
        astro_affinity="Телец",
        voice="Кто-то уже проходил эту дверь. Спроси — и не изобретай замок заново.",
        keywords_reversed=("догма", "бунт ради бунта"),
    ),
    TarotCard(
        id="major_06", name_ru="Влюблённые", arcana="major", number=6, emoji="💞",
        keywords=("выбор сердцем", "союз", "честность с собой"),
        astro_affinity="Близнецы",
        voice="Это не выбор между людьми — это выбор, кем будешь ты. Выбирай не губами, а жизнью.",
        keywords_reversed=("разлад", "выбор из страха"),
    ),
    TarotCard(
        id="major_07", name_ru="Колесница", arcana="major", number=7, emoji="🏇",
        keywords=("движение", "воля к победе", "управление противоречиями"),
        astro_affinity="Рак",
        voice="Две лошади тянут в разные стороны — и обе твои. Побеждает тот, кто держит поводья, а не хлыст.",
        keywords_reversed=("потеря управления", "напор без руля"),
    ),
    TarotCard(
        id="major_08", name_ru="Сила", arcana="major", number=8, emoji="🦁",
        keywords=("мягкая сила", "терпение", "приручить, не сломать"),
        astro_affinity="Лев",
        voice="Льва не побеждают — с ним договариваются. Твоя мягкость сегодня сильнее чужого рыка.",
        keywords_reversed=("сомнение в себе", "сила через давление"),
    ),
    TarotCard(
        id="major_09", name_ru="Отшельник", arcana="major", number=9, emoji="🏮",
        keywords=("уединение", "свой темп", "внутренний свет"),
        astro_affinity="Дева",
        voice="Отойди от шума на один вечер — и увидишь то, что толпа заслоняла.",
        keywords_reversed=("изоляция", "отказ от помощи"),
    ),
    TarotCard(
        id="major_10", name_ru="Колесо Фортуны", arcana="major", number=10, emoji="🎡",
        keywords=("поворот", "шанс", "цикл сменился"),
        astro_affinity="Юпитер",
        voice="Колесо уже повернулось — не держись за спицу. Лови новую точку опоры.",
        keywords_reversed=("сопротивление переменам", "полоса невезения"),
    ),
    TarotCard(
        id="major_11", name_ru="Справедливость", arcana="major", number=11, emoji="⚖️",
        keywords=("равновесие", "последствия", "честный расчёт"),
        astro_affinity="Весы",
        voice="Сегодня всё взвешивается точно. Проверь, что кладёшь на свою чашу.",
        keywords_reversed=("перекос весов", "самообман в расчётах"),
    ),
    TarotCard(
        id="major_12", name_ru="Повешенный", arcana="major", number=12, emoji="🙃",
        keywords=("пауза", "смена угла", "отпустить контроль"),
        astro_affinity="Нептун",
        voice="Не всё решается усилием. Повиси в неопределённости — картинка перевернётся сама.",
        keywords_reversed=("бесплодная жертва", "затянувшаяся пауза"),
    ),
    TarotCard(
        id="major_13", name_ru="Смерть", arcana="major", number=13, emoji="🦋",
        keywords=("завершение", "освобождение места", "необратимая смена"),
        astro_affinity="Скорпион",
        voice="Это не конец — это освобождение полки. Не реанимируй то, что уже дало тебе всё.",
        keywords_reversed=("цепляние за старое", "страх завершить"),
    ),
    TarotCard(
        id="major_14", name_ru="Умеренность", arcana="major", number=14, emoji="🕊",
        keywords=("дозировка", "смешение крайностей", "точная мера"),
        astro_affinity="Стрелец",
        voice="Не «или-или», а «сколько именно». Смешай две крайности — получится твой ответ.",
        keywords_reversed=("крайности", "потеря меры"),
    ),
    TarotCard(
        id="major_15", name_ru="Дьявол", arcana="major", number=15, emoji="⛓",
        keywords=("зависимость", "выгодная несвобода", "честность о желаниях"),
        astro_affinity="Козерог",
        voice="Цепь держится, пока она удобна. Назови свою выгоду в этой клетке — и дверь окажется открыта.",
        keywords_reversed=("освобождение от зависимости", "отрицание своей тени"),
    ),
    TarotCard(
        id="major_16", name_ru="Башня", arcana="major", number=16, emoji="🌩",
        keywords=("внезапная правда", "разрушение фасада", "освобождение"),
        astro_affinity="Марс",
        voice="Рушится не твоё — рушится фальшивое. Не отстраивай фасад, посмотри, что за ним стояло.",
        keywords_reversed=("отложенный крах", "страх перемен"),
    ),
    TarotCard(
        id="major_17", name_ru="Звезда", arcana="major", number=17, emoji="⭐",
        keywords=("надежда", "восстановление", "тихая уверенность"),
        astro_affinity="Водолей",
        voice="После грозы небо чище. Делай маленький искренний шаг — этого достаточно.",
        keywords_reversed=("неверие", "погасший ориентир"),
    ),
    TarotCard(
        id="major_18", name_ru="Луна", arcana="major", number=18, emoji="🌕",
        keywords=("туман", "страхи-миражи", "не время решать"),
        astro_affinity="Рыбы",
        voice="В тумане все кусты похожи на волков. Не принимай решений о том, чего не видно, — дождись рассвета.",
        keywords_reversed=("туман рассеивается", "страхи преувеличены"),
    ),
    TarotCard(
        id="major_19", name_ru="Солнце", arcana="major", number=19, emoji="☀️",
        keywords=("ясность", "радость без причины", "открытость"),
        astro_affinity="Солнце",
        voice="Сегодня можно не прятаться. Покажи то, чем гордишься, — свет на твоей стороне.",
        keywords_reversed=("временная тень", "радость напоказ"),
    ),
    TarotCard(
        id="major_20", name_ru="Суд", arcana="major", number=20, emoji="📯",
        keywords=("призыв", "итог прошлого", "второй шанс"),
        astro_affinity="Плутон",
        voice="Старое дело зовёт тебя не назад, а на новый уровень. Ответь на звонок, который откладывала.",
        keywords_reversed=("игнор призыва", "самокритика без итога"),
    ),
    TarotCard(
        id="major_21", name_ru="Мир", arcana="major", number=21, emoji="🌍",
        keywords=("завершённый цикл", "целостность", "заслуженный итог"),
        astro_affinity="Сатурн",
        voice="Круг замкнулся — и это победа. Поставь точку красиво, прежде чем открывать новую главу.",
        keywords_reversed=("незакрытый круг", "точка не поставлена"),
    ),
)

# импорт после MAJOR_ARCANA: масти зависят от card.py, а не от deck.py — цикла нет
from astra.tarot.deck_minor import CUPS, PENTACLES, SWORDS, WANDS  # noqa: E402

DECK: tuple[TarotCard, ...] = MAJOR_ARCANA + WANDS + CUPS + SWORDS + PENTACLES

_CARDS_BY_ID: dict[str, TarotCard] = {card.id: card for card in DECK}


def card_by_id(card_id: str) -> TarotCard | None:
    return _CARDS_BY_ID.get(card_id)
