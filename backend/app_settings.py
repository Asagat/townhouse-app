# backend/app_settings.py
"""Глобальные настройки приложения (Б3 и далее).

Хранятся в таблице `app_settings` (key/value, правит админ). Отсутствующая строка
= значение по умолчанию из `DEFAULTS`. Пока настройка одна — «Префикс лицевого
счёта»; модуль рассчитан на расширение.
"""

from sqlalchemy.orm import Session

from models import Account, Apartment, AppSetting

# Известные настройки и их значения по умолчанию.
DEFAULTS: dict[str, str] = {
    "account_number_prefix": "LS-",
}


def get_settings(db: Session) -> dict[str, str]:
    """Эффективные настройки: дефолты, перекрытые строками из БД."""
    result = dict(DEFAULTS)
    for row in db.query(AppSetting).all():
        if row.key in DEFAULTS and row.value is not None:
            result[row.key] = row.value
    return result


def get_setting(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    if row is not None and row.value is not None:
        return row.value
    return DEFAULTS.get(key, "")


def set_settings(db: Session, values: dict, user_id: int | None) -> dict[str, str]:
    """Сохраняет известные настройки (неизвестные ключи игнорируются)."""
    for key, value in values.items():
        if key not in DEFAULTS:
            continue
        row = db.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key)
            db.add(row)
        row.value = "" if value is None else str(value)
        row.updated_by = user_id
    db.commit()
    return get_settings(db)


def generate_account_number(db: Session, prefix: str, apartment_id) -> str:
    """Генерирует уникальный номер лицевого счёта: `<префикс><номер квартиры:04d>`.

    Если такой номер занят — добавляет суффикс `-2`, `-3`, … Гарантирует уникальность.
    """
    prefix = prefix or ""
    base = prefix
    apartment = None
    if apartment_id not in (None, ""):
        apartment = db.get(Apartment, int(apartment_id))
    if apartment is not None and apartment.apartment_number is not None:
        base = f"{prefix}{int(apartment.apartment_number):04d}"
    candidate = base or "LS-0001"
    n = 1
    while db.query(Account.id).filter(Account.account_number == candidate).first():
        n += 1
        candidate = f"{base}-{n}"
    return candidate
