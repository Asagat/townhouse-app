# backend/migrations/migrate_import.py
"""Синтез данных на ЧИСТОЙ базе из подготовленных CSV (`templates/clean`, см.
`migrate_prepare_sources.py`) — роадмап раздел 4.3–4.4.

Выполняется НАПРАВЛЕННО на чистую схему (alembic upgrade head), ДО заполнения
демо/seed. Работа построена атомами в одном скрипте:

  ЭТАП 1 (ref): справочники — миграционный пользователь, CashPoint,
                AnalyticArticle(«Поступления от жителей»), ServiceType (7),
                TariffType, Counterparty/Apartment/Account (из apartments.csv),
                Meter (из meters.csv);
  ЭТАП 2: показания -> документы MeterReadingDocument + строки;
  ЭТАП 3: начисления -> AccrualDocument+строки (reg/vary/razov/manual/enter),
          уважая флаг do_not_recalc;
  ЭТАП 4: касса -> Transaction (+ cash_register через событие); сторно-абс;
  ЭТАП 5: пересбор регистра взаиморасчётов (rebuild_accounts_register) и КС.

Запуск (внутри backend-контейнера, где есть БД и зависимости):
   python migrations/migrate_import.py --csv /app/_migration_src --stage ref,meters

перед прогоном скопируйте подготовленные templates/clean/*.csv в доступное контейнеру
место (docker cp templates/clean <c-backend>:/app/_migration_src). Чтобы исполнить на
чистой (отдельной) БД — прогон в контейнере с переопределённым DATABASE_URL.

Скрипт идемпотентен по этапам (не создаёт дублей справочников); последующие этапы
(об.показаний/начислений/кассы, rebuild) добяются далее в этом же модуле.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import decimal
import os
import secrets
import sys
from pathlib import Path

# Русские месяцы (для авто-названия документов)
MONTHS_RU = ["январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]

# Даём доступ к модулям приложения (database, models, services...), как в других
# миграционных скриптах.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database  # noqa: E402
from models import (  # noqa: E402
    Account,
    AnalyticArticle,
    AnalyticKind,
    Apartment,
    CashPoint,
    Meter,
    MeterReading,
    MeterReadingDocument,
    Counterparty,
    ServiceType,
    TariffType,
    User,
    UserRole,
)

MIGRATION_USERNAME = "migration"
# Потенциальный пароль — ТОЛЬКО из env; служебный пользователь не логинится
# (is_active=False), поэтому при отсутствии env генерируется случайный токен
# (в коде/истории секрет не хранится).
MIGRATION_PASSWORD = os.environ.get("MIGRATION_IMPORT_PASSWORD")


def _csv(path: Path, name: str):
    full = Path(path) / f"{name}.csv"
    with full.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _d(v):
    if not v:
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def get_or_make_user(db) -> User:
    user = db.query(User).filter(User.username == MIGRATION_USERNAME).first()
    if user is None:
        # Роль admin — автор исторических документов. Пароль не требуется для
        # логина (is_active=False); если env не задан — случайный токен.
        from auth import hash_password  # noqa: WPS433
        pw = MIGRATION_PASSWORD or secrets.token_urlsafe(48)
        user = User(
            username=MIGRATION_USERNAME,
            password_hash=hash_password(pw),
            full_name="Миграция (системный)",
            role=UserRole.admin,
            is_active=False,  # служебная, не для логина
        )
        db.add(user)
        db.flush()
    return user


def ensure_system_refs(db, name_cash) -> tuple:
    """ServiceType (7), TariffType, AnalyticArticle нач., CashPoint. Возвращает
    словари «по имени» для синтеза."""
    cash = db.query(CashPoint).filter(CashPoint.name == name_cash).first()
    if cash is None:
        cash = CashPoint(name=name_cash, is_active=True)
        db.add(cash)
        db.flush()

    income_art = (
        db.query(AnalyticArticle)
        .filter(AnalyticArticle.name == "Поступления от жителей")
        .filter(AnalyticArticle.kind == AnalyticKind.income)
        .first()
    )
    if income_art is None:
        income_art = AnalyticArticle(name="Поступления от жителей", kind=AnalyticKind.income)
        db.add(income_art)
        db.flush()
    return cash, income_art


def ensure_tariff_types(db):
    for name in ("Фиксированный", "По счетчику", "По площади"):
        if not db.query(TariffType).filter(TariffType.name == name).first():
            db.add(TariffType(name=name))
    db.flush()


def ensure_services(db, path) -> dict:
    """Создаёт ServiceType из services.csv (code->имя) и возвращает mapping
    code-str -> ServiceType."""
    mapping = {}
    for row in _csv(path, "services"):
        code = row["code"].strip()
        name = row["name"].strip()
        svc = db.query(ServiceType).filter(ServiceType.services_type == name).first()
        if svc is None:
            svc = ServiceType(services_type=name, priority=0)
            db.add(svc)
            db.flush()
        mapping[code] = svc
    db.flush()
    return mapping


def stage_ref(db, path) -> dict:
    """ЭТАП 1: справочники. Возвращает словарь (cash, income_article,
    services, accounts_by_apartment_key, meters_by_apartment) для уполномоченных
    этапов строк."""
    user = get_or_make_user(db)
    ensure_tariff_types(db)
    cash, income_art = ensure_system_refs(db, name_cash="Касса")
    services = ensure_services(db, path)

    owners_by_name: dict[str, Counterparty] = {}
    apt_rows = _csv(path, "apartments")
    accounts_by_apartment_key: dict[str, Account] = {}
    for row in apt_rows:
        ap_key = row["apartment_key"]
        num = row["apartment_number"].split(".")[0] if row["apartment_number"] else ap_key
        full = (row["owner_full_name"] or "").strip()
        owner = owners_by_name.get(full)
        if owner is None and full:
            parts = full.split()
            first = parts[1] if len(parts) > 1 else (parts[0] if parts else full)
            owner = Counterparty(full_name=full, first_name=first,
                          last_name=parts[0] if parts else None,
                          middle_name=parts[2] if len(parts) > 2 else None)
            db.add(owner)
            db.flush()
            owners_by_name[full] = owner
        apartment = db.query(Apartment).filter(Apartment.apartment_number == int(num)).first()
        if apartment is None:
            sq = row["square"]
            try:
                area = decimal.Decimal(sq)
            except Exception:
                area = 0
            apartment = Apartment(
                apartment_number=int(num),
                address=f"Кв. {num}",
                square=area,
                owner_id=owner.id if owner else None,
            )
            db.add(apartment)
            db.flush()
        account_number = row["account_number"] if row.get("account_number") else f"LS-{int(num):04d}"
        account = db.query(Account).filter(Account.account_number == account_number).first()
        if account is None:
            account = Account(
                apartment_id=apartment.id,
                account_number=account_number,
                account_name=f"Лицевой счёт кв. {num}",
                is_active=True,
            )
            db.add(account)
            db.flush()
        accounts_by_apartment_key[ap_key] = account
    db.flush()
    return {
        "user": user,
        "cash": cash,
        "income_article": income_art,
        "services": services,
        "accounts": accounts_by_apartment_key,
        "db": db,
        "path": path,
    }


def stage_ref_meters(ctx, path) -> None:
    """/app -- метры из meters.csv: только услуги-переменные счётчики (електро)."""
    db = ctx["db"]
    services = ctx["services"]
    # электроэнергия = code 1 — единственная «по счётчику» переменная в данных
    el_svc = services.get("1")
    accounts = ctx["accounts"]
    by_apt: dict[str, list] = {}
    for row in _csv(path, "meters"):
        by_apt.setdefault(row["apartment_key"], []).append(row)
    for ap_key, rows in by_apt.items():
        account = accounts.get(ap_key)
        apartment = account.apartment if account else None
        if apartment is None or el_svc is None:
            continue
        for row in rows:
            serial = f"M-{int(ap_key):02d}-{row['meter_idx']}"
            if db.query(Meter).filter(Meter.serial_number == serial).first():
                continue
            db.add(Meter(
                serial_number=serial,
                apartment_id=apartment.id,
                services_type_id=el_svc.id,
                installed_at=_d(row["first_reading_date"]),
            ))
    db.flush()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default="_migration_src", help="каталог подгот. CSV")
    ap.add_argument("--stage", default="ref",
                    help="этап(ы) запятой: ref,meters,doc_accrual,doc_cash,rebuild (построение)")
    args = ap.parse_args()

    if not Path(args.csv).is_dir():
        print(f"Каталог CSV не найден: {args.csv}")
        return 2

    db = database.SessionLocal()
    try:
        stage = [s.strip() for s in args.stage.split(",") if s.strip()]
        ctx = None
        if "ref" in stage:
            ctx = stage_ref(db, Path(args.csv))
        if ctx and "meters" in stage:
            stage_ref_meters(ctx, Path(args.csv))
        db.commit()
        print("СИНТЕЗ: ЭТАП справочников+метров выполнен.")
    except Exception as exc:
        db.rollback()
        print("ОШИБКА СИНТЕЗА:", exc)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
