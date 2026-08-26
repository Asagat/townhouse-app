"""
Создание пользователя (CLI). Нужен для первоначального заведения администратора
и последующего управления пользователями из командной строки.

Запуск из каталога backend:
    python create_user.py --username admin --password 'секрет' [--role admin]
Роли: admin | operator | cashier | controller | resident (по умолчанию cashier).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal  # noqa: E402
from models import User, UserRole  # noqa: E402
from auth import hash_password  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Создание пользователя")
    parser.add_argument("--username", required=True, help="Логин")
    parser.add_argument("--password", required=True, help="Пароль (мин. 6 символов)")
    parser.add_argument("--role", default="cashier", help="Роль: admin/operator/cashier/controller/resident")
    parser.add_argument("--full-name", default="", help="Отображаемое имя")
    args = parser.parse_args()

    try:
        role = UserRole[args.role]
    except KeyError:
        sys.exit(f"Недопустимая роль: {args.role}. Допустимые: {[r.name for r in UserRole]}")

    if len(args.password) < 6:
        sys.exit("Пароль слишком короткий (мин. 6 символов)")

    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == args.username).first():
            sys.exit(f"Пользователь '{args.username}' уже существует")
        user = User(
            username=args.username,
            password_hash=hash_password(args.password),
            full_name=args.full_name,
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Пользователь '{args.username}' создан с ролью '{role.name}' ({role.value}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
