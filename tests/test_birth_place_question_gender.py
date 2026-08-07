"""Род в вопросе про место рождения берётся из профиля, а не угадывается.

До этого «📍 Где ты родилась?» приходило всем, включая мужчин, а про третьих
лиц бот спрашивал формой «родился(ась)» — это бланк, а не речь.
"""

from astra.telegram.handlers.places import birth_place_question
from astra.users.gender import GENDER_FEMALE, GENDER_MALE


class TestAboutTheUser:
    def test_female_and_male_get_their_own_form(self) -> None:
        assert birth_place_question(GENDER_FEMALE) == "📍 Где ты родилась?"
        assert birth_place_question(GENDER_MALE) == "📍 Где ты родился?"

    def test_unknown_gender_avoids_the_word_entirely(self) -> None:
        text = birth_place_question(None)
        assert "родил" not in text  # ни мужской формы по умолчанию, ни скобок
        assert text == "📍 Где твоё место рождения?"


class TestAboutSomeoneElse:
    def test_name_is_kept_in_the_gendered_form(self) -> None:
        assert birth_place_question(GENDER_FEMALE, who="Анжела") == "📍 Где родилась Анжела?"
        assert birth_place_question(GENDER_MALE, who="партнёр") == "📍 Где родился партнёр?"

    def test_unknown_gender_drops_the_name_instead_of_guessing(self) -> None:
        text = birth_place_question(None, who="Анжела")
        assert "родил" not in text
        assert text == "📍 Где место рождения этого человека?"


def test_no_slash_forms_anywhere() -> None:
    """«родился(ась)» и «готов/готова» — формы из бланка, их быть не должно."""
    variants = [
        birth_place_question(gender, who=who)
        for gender in (GENDER_FEMALE, GENDER_MALE, None)
        for who in (None, "Анжела")
    ]
    for text in variants:
        assert "(ась)" not in text
        assert "/" not in text
