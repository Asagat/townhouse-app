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

# Пароль НЕ должен попадать в git/историю. При интерактивном создании лучше задавать
# его через env:  ADMIN_PASSWORD='...' python create_user.py
#
# Скрипт ИДЕМПОТЕНТЕН: если пользователь с таким username уже есть — его пароль по
# умолчанию (без --password) ОБНОВЛЯЕТСЯ на актуальный (из --password / ADMIN_PASSWORD /
# сгенерированный), чтобы можно было безопасно повторно запускать при развёртывании.
"""

import argparse
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Гарантируем UTF-8 для stdout/stderr (кириллица в логах на любом окружении,
# включая серверы с локалью ASCII). PYTHONUTF8 обычно уже решает это при старте,
# но страхуемся и здесь — обёрнуто в try/except, чтобы сбой кодировки никогда
# не обрывал реальную работу скрипта.
try:
    for _stream in (sys.stdout, sys.stderr):
        if _stream and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

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
    parser.add_argument(
        "--account",
        default="",
        help="ID лицевого счёта для привязки пользователя (особенно для роли resident/ЛК)",
    )
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
        existing = db.query(User).filter(User.username == args.username).first()
        if existing:
            # Пользователь уже есть — обновляем пароль (идемпотентность), а также
            # роль и имя, если переданы. Повторный запуск не считается ошибкой.
            existing.password_hash = hash_password(password)
            existing.role = role
            if args.full_name:
                existing.full_name = args.full_name
            if args.account:
                existing.account_id = int(args.account)
            db.commit()
            print(f"Пользователь '{args.username}' существует — пароль обновлён (роль '{role.name}').")
            if generated:
                print(f"Сгенерирован пароль: {password}")
                print("Сохраните его — повторно показать невозможно.")
            return

        user = User(
            username=args.username,
            password_hash=hash_password(password),
            full_name=args.full_name,
            role=role,
            is_active=True,
            account_id=int(args.account) if args.account else None,
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
