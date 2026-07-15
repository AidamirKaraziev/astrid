"""Пентакли — стихия Земли: деньги, работа, тело, ресурсы."""

from __future__ import annotations

from astra.tarot.card import TarotCard

PENTACLES: tuple[TarotCard, ...] = (
    TarotCard(
        id="pentacles_01", name_ru="Туз Пентаклей", arcana="pentacles", number=1, emoji="🪙",
        keywords=("шанс в материи", "семя дохода", "твёрдое начало"),
        astro_affinity="стихия Земли",
        voice="Монета уже в ладони — вопрос, посадишь или потратишь. Из посаженного вырастает сад.",
        keywords_reversed=("упущенная возможность", "жадный старт"),
    ),
    TarotCard(
        id="pentacles_02", name_ru="Двойка Пентаклей", arcana="pentacles", number=2, emoji="🤹",
        keywords=("жонглирование", "гибкий баланс", "два дела разом"),
        astro_affinity="Юпитер в Козероге",
        voice="Две монеты в воздухе — это танец, а не паника. Держи ритм и не бери третью.",
        keywords_reversed=("перегрузка", "всё валится из рук"),
    ),
    TarotCard(
        id="pentacles_03", name_ru="Тройка Пентаклей", arcana="pentacles", number=3, emoji="🧑‍🎨",
        keywords=("мастерство в команде", "признание навыка", "общая стройка"),
        astro_affinity="Марс в Козероге",
        voice="Твоё ремесло заметили — покажи эскизы. Собор строят втроём: мастер, план и заказчик.",
        keywords_reversed=("работа без обратной связи", "халтура"),
    ),
    TarotCard(
        id="pentacles_04", name_ru="Четвёрка Пентаклей", arcana="pentacles", number=4, emoji="🧰",
        keywords=("сбережение", "контроль", "крепко держать своё"),
        astro_affinity="Солнце в Козероге",
        voice="Держать — не то же, что иметь. Разожми пальцы на одну монету и проверь: мир не рухнул.",
        keywords_reversed=("скупость", "зажатость"),
    ),
    TarotCard(
        id="pentacles_05", name_ru="Пятёрка Пентаклей", arcana="pentacles", number=5, emoji="🕯",
        keywords=("полоса нужды", "холод снаружи", "помощь рядом"),
        astro_affinity="Меркурий в Тельце",
        voice="Свет в окне горит и для тебя. Бедность этой недели — погода, а не приговор: зайди погреться.",
        keywords_reversed=("конец трудной полосы", "принятая помощь"),
    ),
    TarotCard(
        id="pentacles_06", name_ru="Шестёрка Пентаклей", arcana="pentacles", number=6, emoji="🎁",
        keywords=("обмен", "щедрость с весами", "дать и взять"),
        astro_affinity="Луна в Тельце",
        voice="Сегодня ты на дающей стороне — завтра на принимающей, и обе достойны. Дари без верёвочек.",
        keywords_reversed=("долг с процентами", "подачка вместо помощи"),
    ),
    TarotCard(
        id="pentacles_07", name_ru="Семёрка Пентаклей", arcana="pentacles", number=7, emoji="🌿",
        keywords=("пауза оценки", "урожай зреет", "терпение"),
        astro_affinity="Сатурн в Тельце",
        voice="Куст растёт, даже когда ты не смотришь. Оцени урожай честно — и не выкапывай корни для проверки.",
        keywords_reversed=("нетерпение", "усилия не туда"),
    ),
    TarotCard(
        id="pentacles_08", name_ru="Восьмёрка Пентаклей", arcana="pentacles", number=8, emoji="🔨",
        keywords=("оттачивание", "ремесло", "монета за монетой"),
        astro_affinity="Солнце в Деве",
        voice="Восьмая монета получается лучше первой — в этом весь секрет. Сегодня просто сделай следующую.",
        keywords_reversed=("рутина без смысла", "перфекционизм"),
    ),
    TarotCard(
        id="pentacles_09", name_ru="Девятка Пентаклей", arcana="pentacles", number=9, emoji="🍇",
        keywords=("самодостаточность", "сад своими руками", "достоинство"),
        astro_affinity="Венера в Деве",
        voice="Этот сад ты вырастила сама — гуляй по нему не спеша. Роскошь дня: никому ничего не доказывать.",
        keywords_reversed=("одиночество в роскоши", "зависимость от комфорта"),
    ),
    TarotCard(
        id="pentacles_10", name_ru="Десятка Пентаклей", arcana="pentacles", number=10, emoji="🏡",
        keywords=("наследие", "клан", "устойчивое богатство"),
        astro_affinity="Меркурий в Деве",
        voice="Ты строишь то, что переживёт сезон, — дом, имя, привычку. Вложись сегодня в долгое.",
        keywords_reversed=("споры о наследстве", "дом без тепла"),
    ),
    TarotCard(
        id="pentacles_page", name_ru="Паж Пентаклей", arcana="pentacles", number=11, emoji="📚",
        keywords=("ученичество", "первая монета", "интерес к ремеслу"),
        astro_affinity="стихия Земли (Телец, Дева, Козерог)",
        voice="Разгляди монету как студентка: что это за шанс и чему он учит? Маленький навык сегодня — капитал через год.",
        keywords_reversed=("прокрастинация", "учёба без практики"),
    ),
    TarotCard(
        id="pentacles_knight", name_ru="Рыцарь Пентаклей", arcana="pentacles", number=12, emoji="🚜",
        keywords=("методичность", "медленно и верно", "поле вспахано"),
        astro_affinity="Лев–Дева",
        voice="Твой конь не скачет — он пашет, и потому доходит. Скучный шаг сегодня дороже яркого рывка.",
        keywords_reversed=("застой", "упрямая рутина"),
    ),
    TarotCard(
        id="pentacles_queen", name_ru="Королева Пентаклей", arcana="pentacles", number=13, emoji="🪴",
        keywords=("забота с ресурсом", "уют", "практичная мудрость"),
        astro_affinity="Стрелец–Козерог",
        voice="Ты умеешь превращать голое место в тёплое. Позаботься о своих — но начни список с себя.",
        keywords_reversed=("быт съел мечту", "гиперопека"),
    ),
    TarotCard(
        id="pentacles_king", name_ru="Король Пентаклей", arcana="pentacles", number=14, emoji="🏦",
        keywords=("достаток", "надёжность", "хозяйка результата"),
        astro_affinity="Овен–Телец",
        voice="Империя строится из повторённых обещаний. Дай слово по средствам — и сдержи, как обычно.",
        keywords_reversed=("контроль через деньги", "застывший успех"),
    ),
)
