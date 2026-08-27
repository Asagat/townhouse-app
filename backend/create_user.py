"""
Создание пользователя (CLI). Нужен для первоначального заведения администратора
и последующего управления пользователями из командной строки.

Запуск из каталога backend:
    python create_user.py                          # админ; пароль из ADMIN_PASSWORD или случайный
    python create_user.py --username admin --password 'секрет' [--role admin]

Правила выбора пароля (в порядке приоритета):
    1. Аргумент --password
    2. Переменная окружения ADMIN_PASSWORD
    3. Если и того, и другого нет — генерируется случайный пароль и выводится в консоль
       (безопасно для неинтерактивного развёртывания).

Пароль НЕ должен попадать в git/историю. При интерактивном создании лучше задавать
его через env:  ADMIN_PASSWORD='...' python create_user.py
"""

import argparse
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal  # noqa: E402
from models import User, UserRole  # noqa: E402
from auth import hash_password  # noqa: E402


def _default_password() -> str:
    """Берёт пароль из ADMIN_PASSWORD или генерирует случайный."""
    env_pass = os.getenv("ADMIN_PASSWORD")
    if env_pass:
        return env_pass
    return secrets.token_urlsafe(24)


def main() -> None:
    parser = argparse.ArgumentParser(description="Создание пользователя")
    parser.add_argument(
        "--username",
        default=os.getenv("ADMIN_USERNAME", "admin"),
        help="Логин (по умолчанию admin или ADMIN_USERNAME)",
    )
    parser.add_argument(
        "--password",
        default="",
        help="Пароль (мин. 6 символов). Если не задан — возьмётся из ADMIN_PASSWORD "
             "или будет сгенерирован случайный.",
    )
    parser.add_argument(
        "--role",
        default="admin",
        help="Роль: admin/operator/cashier/controller/resident (по умолчанию admin)",
    )
    parser.add_argument("--full-name", default="", help="Отображаемое имя")
    args = parser.parse_args()

    try:
        role = UserRole[args.role]
    except KeyError:
        sys.exit(f"Недопустимая роль: {args.role}. Допустимые: {[r.name for r in UserRole]}")

    password = args.password or _default_password()
    generated = not (args.password or os.getenv("ADMIN_PASSWORD"))

    if len(password) < 6:
        msg = f"Пароль слишком короткий (мин. 6 символов), длина: {len(password)}"
        if generated:
            sys.exit(msg + " (повторите запуск с явным паролем или задайте ADMIN_PASSWORD)")
        sys.exit(msg)

    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == args.username).first():
            sys.exit(f"Пользователь '{args.username}' уже существует")
        user = User(
            username=args.username,
            password_hash=hash_password(password),
            full_name=args.full_name,
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Пользователь '{args.username}' создан с ролью '{role.name}' ({role.value}).")
        if generated:
            # Печатаем сгенерированный пароль ТОЛЬКО здесь, в лог/консоль одноразового запуска.
            print(f"Сгенерирован пароль: {password}")
            print("Сохраните его — повторно показать невозможно.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
