"""
Аутентификация и ролевой доступ.

- Хеширование паролей: PBKDF2-SHA256 (stdlib), формат "<it>$<salt_hex>$<hash_hex>".
- Токены: JWT (PyJWT), HS256.
- Роли: см. models.UserRole. Иерархия уровней + точечное исключение
  («настройки — только admin»). Подробнее — см. ролевую матрицу в ROADMAP.

Безопасность: в продакшене обязательно задайте AUTH_SECRET_KEY (см. .env). Значение
по умолчанию используется ТОЛЬКО для разработки.
"""

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import User, UserRole

JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800"))  # 8 ч по умолчанию
# Секрет для подписи JWT. В продакшене задаётся через AUTH_SECRET_KEY.
_SECRET = os.getenv("AUTH_SECRET_KEY") or "dev-only-insecure-secret-change-me"

_PBKDF2_ITERATIONS = 260000


# --- ХЕШИРОВАНИЕ ПАРОЛЕЙ ---


def hash_password(password: str) -> str:
    """Возвращает хеш пароля в формате '<it>$<salt_hex>$<hash_hex>'."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Проверяет пароль против сохранённого хеша. Устойчив к различию форматов."""
    try:
        iterations_s, salt_hex, hash_hex = stored.split("$")
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)


# --- JWT ---


def create_access_token(user: User) -> str:
    """Создаёт JWT для пользователя."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.name,
        "iat": now,
        "exp": now + timedelta(seconds=TOKEN_TTL_SECONDS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Декодирует JWT; бросает HTTPException при невалидном/просроченном токене."""
    try:
        return jwt.decode(token, _SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Токен истёк")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Недействительный токен")


# --- ЗАВИСИМОСТИ FASTAPI ---

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Возвращает текущего пользователя по Bearer-токену, либо 401."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Некорректный токен")
    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Пользователь недоступен или отключён")
    return user


# Иерархия ролей для «уровневого» доступа. resident самая низкая, admin — самая высокая.
ROLE_LEVEL: dict[UserRole, int] = {
    UserRole.resident: 0,
    UserRole.controller: 1,
    UserRole.cashier: 2,
    UserRole.operator: 3,
    UserRole.admin: 4,
}


def has_level(user: User, minimum: UserRole) -> bool:
    """True, если роль пользователя >= заданного уровня (по иерархии)."""
    return ROLE_LEVEL.get(user.role, -1) >= ROLE_LEVEL.get(minimum, 0)


def require_roles(*roles: str) -> Any:
    """Фабрика зависимости: допускает только указанные роли (по имени, напр. 'admin')."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        allowed = {r for r in roles}
        if user.role.name not in allowed and user.role.name != "admin":
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return user

    return dependency
