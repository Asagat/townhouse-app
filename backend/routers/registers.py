# backend/routers/registers.py
"""Регистры начислений, списания и обслуживание регистров (ЭТАП 3 роадмапа).

Вынесены из `app.py`: расчёт и генерация начислений (`accruals_register/calculate`,
`accruals_register/generate`), операция списания (`write_offs/run`) и пересбор
регистров (`maintenance/rebuild_registers`). Логика сохранена без изменений.
"""

import calendar
import logging
from datetime import date
from typing import Any

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import AccrualDocument, AccrualsRegister, User
from routers.documents import default_accrual_document_title
from serializers import SERIALIZERS, accrual_document_serializer
from services import (
    build_accrual_register_items,
    calculate_accruals_preview,
    create_accounts_register_entries_for_accruals,
)
from writeoffs import (
    calculate_write_offs,
    rebuild_accounts_register,
    check_register_integrity,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# --- ЭНДПОИНТЫ ДЛЯ НАЧИСЛЕНИЙ ---

@router.get("/accruals_register/calculate")
async def calculate_accruals(
    year: int,
    month: int,
    db: Session = Depends(get_db),
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Некорректный месяц")

    rows = calculate_accruals_preview(db, year, month)
    return {"rows": rows}


@router.post("/accruals_register/generate", status_code=201)
async def generate_accruals(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    _auth: User = Depends(require_roles("operator", "admin")),
):
    """
    Создаёт документ начислений и строки регистра за одну транзакцию.

    Важно: клиент присылает только идентификаторы выбранных строк (account_id + services_type_id),
    а не рассчитанные значения. Сумма, потребление, тариф и показания
    всегда пересчитываются на сервере на момент сохранения, чтобы исключить подмену
    данных через API и рассинхронизацию с изменившимися между превью и сохранением данными.
    """
    year = payload.get("year")
    month = payload.get("month")
    selections = payload.get("selections") or payload.get("rows") or []

    if year in (None, "") or month in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите месяц и год начисления")
    if not isinstance(selections, list) or not selections:
        raise HTTPException(status_code=422, detail="Нет строк для начисления")

    year = int(year)
    month = int(month)
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Некорректный месяц")

    period_end = date(year, month, calendar.monthrange(year, month)[1])

    # Собираем уникальные пары (account_id, services_type_id) из выбора клиента
    requested_pairs: set[tuple[int, int]] = set()
    for row in selections:
        account_id = row.get("account_id")
        services_type_id = row.get("services_type_id")
        if account_id in (None, "") or services_type_id in (None, ""):
            continue
        requested_pairs.add((int(account_id), int(services_type_id)))

    if not requested_pairs:
        raise HTTPException(status_code=422, detail="Нет корректных строк для начисления")

    accrual_date = date(year, month, calendar.monthrange(year, month)[1])

    # Создаём документ начислений в той же транзакции, чтобы исключить документы-сирот
    title = payload.get("title") or default_accrual_document_title(accrual_date)
    document = AccrualDocument(accrual_date=accrual_date, title=title)
    db.add(document)
    db.flush()  # получаем document.id до commit

    items = build_accrual_register_items(db, document, period_end, accrual_date, requested_pairs)

    if not items:
        db.rollback()
        raise HTTPException(status_code=422, detail="Нет корректных строк для начисления (возможно, данные успели измениться с момента расчёта превью)")

    db.add_all(items)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Нарушение целостности данных при сохранении начислений: {str(exc)}",
        ) from exc

    try:
        create_accounts_register_entries_for_accruals(db, items)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Не удалось создать записи в регистре взаиморасчётов: {str(exc)}",
        ) from exc

    db.refresh(document)

    serializer = SERIALIZERS.get(AccrualsRegister)
    created_rows = [serializer(item) for item in items]

    return {
        "document": accrual_document_serializer(document),
        "created": created_rows,
    }


@router.post("/write_offs/run", status_code=201)
def run_write_offs(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    _auth: User = Depends(require_roles("operator", "admin")),
):
    """
    Операция «Списание задолженностей».

    Распределяет доступные деньги каждого лицевого счёта по видам услуг
    в порядке приоритета (services_type.priority) и пишет результат
    в Регистр взаиморасчётов. Идемпотентна: существующие строки списания
    для затронутых счетов перестраиваются заново.

    Запускается: по кнопке, по регламенту (cron) или при создании
    «Приход/Расход».
    """
    raw_ids = payload.get("account_ids")
    if raw_ids is None:
        account_ids = None
    elif isinstance(raw_ids, list):
        account_ids = [int(x) for x in raw_ids]
    else:
        raise HTTPException(status_code=422, detail="Поле 'account_ids' должно быть списком или отсутствовать")

    try:
        result = calculate_write_offs(db, account_ids)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Ошибка списания задолженностей")
        raise HTTPException(status_code=409, detail=f"Не удалось выполнить списание: {str(exc)}")

    return result


@router.post("/maintenance/rebuild_registers", status_code=201)
def rebuild_registers(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    _auth: User = Depends(require_roles("operator", "admin")),
):
    """
    Полный пересбор производного среза (accounts_register) «с нуля» из первичных
    регистров (accruals_register + cash_register). Служебная операция для
    восстановления согласованности после импорта/правок данных и после
    «не прошедшего» списания.

    Опциональный account_ids — ограничить пересбор конкретными счетами;
    если не передан — все активные. После пересбора возвращает аудит целостности
    по затронутым счетам.
    """
    raw_ids = payload.get("account_ids")
    if raw_ids is None:
        account_ids = None
    elif isinstance(raw_ids, list):
        account_ids = [int(x) for x in raw_ids]
    else:
        raise HTTPException(status_code=422, detail="Поле 'account_ids' должно быть списком или отсутствовать")

    try:
        rebuild = rebuild_accounts_register(db, account_ids)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Ошибка пересбора регистров")
        raise HTTPException(status_code=409, detail=f"Не удалось пересобрать регистры: {str(exc)}")

    # Аудит целостности по затронутым счетам.
    audit = []
    for rec in rebuild["processed"]:
        audit.append(check_register_integrity(db, rec["account_id"]))

    return {
        "rebuilt": rebuild["processed"],
        "integrity": audit,
        "all_consistent": all(a["consistent"] for a in audit),
    }
