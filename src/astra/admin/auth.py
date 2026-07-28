"""Вход в админ-панель: пароль из .env и подписанная кука сессии.

Панель включается только когда задан ADMIN_PASSWORD — иначе все её роуты
отвечают 404. Так забытый конфиг на проде не открывает каталог наружу.

Сессия без хранилища: кука = payload + HMAC-подпись. Сервер ничего не помнит,
но и подделать её нельзя. Смена пароля меняет ключ подписи — все сессии гаснут.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Request

from astra.core.config import Settings, get_settings

COOKIE_NAME = "astra_admin"

# Перебор пароля: после стольких неудач с адреса — пауза.
_MAX_ATTEMPTS = 10
_LOCKOUT_SECONDS = 300

# ip -> (число неудач, время последней)
_failures: dict[str, tuple[int, float]] = {}


def is_enabled(settings: Settings | None = None) -> bool:
    """Включена ли панель. Без пароля в .env — выключена."""
    cfg = settings or get_settings()
    return bool(cfg.admin_password.strip())


def _secret(settings: Settings) -> bytes:
    raw = settings.admin_session_secret.strip() or f"astra-admin::{settings.admin_password}"
    return hashlib.sha256(raw.encode()).digest()


def _b64(raw: bytes) -> str:
    """base64url без `=`: иначе куку приходится брать в кавычки."""
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes, settings: Settings) -> str:
    return _b64(hmac.new(_secret(settings), payload, hashlib.sha256).digest())


def issue_session(settings: Settings | None = None) -> str:
    """Кука для успешно вошедшего: срок жизни — admin_session_hours."""
    cfg = settings or get_settings()
    expires = int(time.time()) + cfg.admin_session_hours * 3600
    payload = json.dumps({"u": cfg.admin_username, "exp": expires}).encode()
    return f"{_b64(payload)}.{_sign(payload, cfg)}"


def verify_session(token: str | None, settings: Settings | None = None) -> bool:
    """Валидна ли кука: подпись наша и срок не вышел."""
    cfg = settings or get_settings()
    if not token or not is_enabled(cfg):
        return False
    body, _, signature = token.partition(".")
    if not body or not signature:
        return False
    try:
        payload = _unb64(body)
    except (ValueError, TypeError):
        return False
    if not hmac.compare_digest(_sign(payload, cfg), signature):
        return False
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return False
    return int(data.get("exp", 0)) > time.time()


def is_authenticated(request: Request, settings: Settings | None = None) -> bool:
    return verify_session(request.cookies.get(COOKIE_NAME), settings)


def check_credentials(username: str, password: str, settings: Settings | None = None) -> bool:
    """Сверка логина и пароля — обе за постоянное время."""
    cfg = settings or get_settings()
    if not is_enabled(cfg):
        return False
    # Сравниваем байты: compare_digest не берёт строки с не-ASCII, а пароль
    # вполне может быть кириллическим.
    user_ok = hmac.compare_digest(username.strip().encode(), cfg.admin_username.strip().encode())
    pass_ok = hmac.compare_digest(password.encode(), cfg.admin_password.encode())
    return user_ok and pass_ok


def client_ip(request: Request) -> str:
    """Адрес клиента; за прокси — первый в X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def lockout_seconds_left(ip: str) -> int:
    """Сколько ещё ждать этому адресу; 0 — можно пробовать."""
    attempts, last = _failures.get(ip, (0, 0.0))
    if attempts < _MAX_ATTEMPTS:
        return 0
    left = int(_LOCKOUT_SECONDS - (time.time() - last))
    if left <= 0:
        _failures.pop(ip, None)
        return 0
    return left


def register_failure(ip: str) -> None:
    attempts, last = _failures.get(ip, (0, 0.0))
    if attempts >= _MAX_ATTEMPTS and time.time() - last > _LOCKOUT_SECONDS:
        attempts = 0
    _failures[ip] = (attempts + 1, time.time())


def reset_failures(ip: str) -> None:
    _failures.pop(ip, None)
