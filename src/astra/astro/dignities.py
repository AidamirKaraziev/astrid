"""Эссенциальные достоинства планет: обитель, экзальтация, изгнание, падение.

Современные управители (Уран/Нептун/Плутон) учитываются наравне с традиционными.
Ключи — английские имена планет и трёхбуквенные коды знаков kerykeion.
"""

from __future__ import annotations

DIGNITY_RU: dict[str, str] = {
    "domicile": "обитель",
    "exaltation": "экзальтация",
    "detriment": "изгнание",
    "fall": "падение",
}

_DOMICILE: dict[str, tuple[str, ...]] = {
    "Sun": ("Leo",),
    "Moon": ("Can",),
    "Mercury": ("Gem", "Vir"),
    "Venus": ("Tau", "Lib"),
    "Mars": ("Ari", "Sco"),
    "Jupiter": ("Sag", "Pis"),
    "Saturn": ("Cap", "Aqu"),
    "Uranus": ("Aqu",),
    "Neptune": ("Pis",),
    "Pluto": ("Sco",),
}

_EXALTATION: dict[str, str] = {
    "Sun": "Ari",
    "Moon": "Tau",
    "Mercury": "Vir",
    "Venus": "Pis",
    "Mars": "Cap",
    "Jupiter": "Can",
    "Saturn": "Lib",
    "Uranus": "Sco",
    "Neptune": "Leo",
    "Pluto": "Ari",
}

_OPPOSITE_SIGN: dict[str, str] = {
    "Ari": "Lib",
    "Tau": "Sco",
    "Gem": "Sag",
    "Can": "Cap",
    "Leo": "Aqu",
    "Vir": "Pis",
    "Lib": "Ari",
    "Sco": "Tau",
    "Sag": "Gem",
    "Cap": "Can",
    "Aqu": "Leo",
    "Pis": "Vir",
}


def dignity_for(planet: str, sign: str) -> str | None:
    """Достоинство планеты в знаке (en-ключ из DIGNITY_RU) или None."""
    domiciles = _DOMICILE.get(planet, ())
    if sign in domiciles:
        return "domicile"
    if any(_OPPOSITE_SIGN[d] == sign for d in domiciles):
        return "detriment"
    exaltation = _EXALTATION.get(planet)
    if exaltation == sign:
        return "exaltation"
    if exaltation is not None and _OPPOSITE_SIGN[exaltation] == sign:
        return "fall"
    return None


def dignity_ru(planet: str, sign: str) -> str | None:
    key = dignity_for(planet, sign)
    return DIGNITY_RU[key] if key else None
