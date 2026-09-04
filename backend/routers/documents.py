# backend/routers/documents.py
"""Документы начислений и показаний (ЭТАП 3 роадмапа).

Вынесены из `app.py` СЕКТ: эндпоинты документов начислений (`accrual_documents*`),
документов показаний (`meter_reading_documents*`) и массового ввода показаний
(`meter_readings/bulk`). Логика сохранена без изменений.
"""

import calendar
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from database import get_db
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import get_current_user
from permissions import require_write_access
from models import (
    AccrualDocument,
    AccrualsRegister,
    Apartment,
    Meter,
    MeterReading,
    MeterReadingDocument,
    User,
    recalculate_account_balance,
)
from serializers import (
    SERIALIZERS,
    accrual_document_serializer,
    meter_reading_document_serializer,
    meter_reading_serializer,
)
from services import (
    audit_document_create,
    audit_document_update,
    build_accrual_register_items,
    build_meter_reading_document_title,
    create_accounts_register_entries_for_accruals,
    default_accrual_document_title,
    validate_date_not_future,
    validate_reading_not_decreased,
    _service_name,
)
from writeoffs import auto_recalculate_writeoffs


router = APIRouter(prefix="/api")




# --- ЭНДПОИНТЫ ДЛЯ ДОКУМЕНТОВ НАЧИСЛЕНИЙ ---

@router.post("/accrual_documents", status_code=201)
def create_accrual_document(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_write_access),
):
    accrual_date = payload.get("accrual_date")
    if not accrual_date:
        raise HTTPException(status_code=422, detail="Укажите дату начисления")

    parsed_date = datetime.strptime(accrual_date, "%Y-%m-%d").date()
    # Период начисления не может быть в будущем (1.10 роадмапа).
    now = date.today()
    if (parsed_date.year, parsed_date.month) > (now.year, now.month):
        raise HTTPException(status_code=422, detail="Нельзя начислить за будущий период")
    # Название генерируется автоматически (1.9 роадмапа) — ввод пользователя игнорируется.
    title = default_accrual_document_title(parsed_date)

    document = AccrualDocument(
        accrual_date=parsed_date,
        title=title,
    )
    audit_document_create(document, user.id)
    db.add(document)
    db.commit()
    db.refresh(document)

    return accrual_document_serializer(document)


@router.get("/accrual_documents/{document_id}")
def get_accrual_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return accrual_document_serializer(document)


@router.patch("/accrual_documents/{document_id}")
def update_accrual_document(
    document_id: int,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_write_access),
):
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    if "accrual_date" in payload:
        document.accrual_date = datetime.strptime(payload["accrual_date"], "%Y-%m-%d").date()
        # Период начисления не может быть в будущем (1.10 роадмапа).
        now = date.today()
        if (document.accrual_date.year, document.accrual_date.month) > (now.year, now.month):
            raise HTTPException(status_code=422, detail="Нельзя начислить за будущий период")

    # Название документа всегда генерируется автоматически (1.9 роадмапа) —
    # ввод пользователя игнорируется.
    document.title = default_accrual_document_title(document.accrual_date)

    if "comment" in payload:
        document.comment = (payload.get("comment") or "").strip() or None

    audit_document_update(document, user.id)
    db.commit()
    db.refresh(document)
    return accrual_document_serializer(document)


@router.delete("/accrual_documents/{document_id}", status_code=204)
def delete_accrual_document(
    document_id: int,
    db: Session = Depends(get_db),
    _auth: User = Depends(require_write_access),
):
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    # Каскадное удаление начислений удалит и их записи accounts_register; запоминаем
    # затронутые аккаунты, чтобы после удаления пересчитать их балансы.
    accrued_items = db.query(AccrualsRegister).filter(
        AccrualsRegister.accrual_document_id == document_id
    ).all()
    affected_accounts: set[int] = {item.account_id for item in accrued_items}

    db.delete(document)
    db.commit()

    for account_id in affected_accounts:
        recalculate_account_balance(db, account_id)
    db.commit()

    # Удаление начислений влияет на регистр взаиморасчётов -> пересчитываем распределение.
    if affected_accounts:
        auto_recalculate_writeoffs(db, list(affected_accounts))

    return Response(status_code=204)


# --- ЭНДПОИНТЫ ДЛЯ ДОКУМЕНТОВ ПОКАЗАНИЙ (массовый ввод) ---

@router.post("/meter_readings/bulk", status_code=201)
def bulk_create_readings(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_write_access),
):
    """Массовое создание показаний с документом-шапкой"""
    reading_date = payload.get("reading_date")
    services_type_id = payload.get("services_type_id")
    readings_data = payload.get("readings") or payload.get("entries") or []

    if not reading_date or not services_type_id:
        raise HTTPException(status_code=422, detail="Заполните дату и вид услуги")
    if not readings_data:
        raise HTTPException(status_code=422, detail="Добавьте хотя бы одно показание")

    parsed_date = (
        datetime.strptime(reading_date, "%Y-%m-%d").date()
        if isinstance(reading_date, str)
        else reading_date
    )
    # Дата показаний не может быть в будущем (1.10 роадмапа).
    validate_date_not_future(parsed_date, "Дата показаний")

    # Название генерируется автоматически (1.9 роадмапа) — ввод пользователя игнорируется.
    document = MeterReadingDocument(
        title=build_meter_reading_document_title(
            parsed_date, _service_name(db, int(services_type_id))
        ),
        reading_date=parsed_date,
        services_type_id=int(services_type_id),
    )
    audit_document_create(document, user.id)
    db.add(document)
    db.flush()

    created_readings = []
    row_errors = []
    for row in readings_data:
        apartment_id = row.get("apartment_id")
        reading_value = row.get("reading")
        meter_id = row.get("meter_id")

        if apartment_id in (None, "") or reading_value in (None, ""):
            continue

        apartment = db.query(Apartment).filter(Apartment.id == int(apartment_id)).first()
        if not apartment:
            row_errors.append({"apartment_id": apartment_id, "detail": "Квартира не найдена"})
            continue

        if not meter_id:
            meter = (
                db.query(Meter)
                .filter(
                    Meter.apartment_id == int(apartment_id),
                    Meter.services_type_id == int(services_type_id),
                )
                .order_by(Meter.installed_at.desc().nullslast(), Meter.id.desc())
                .first()
            )
            meter_id = meter.id if meter else None

        # Показания нарастающие: строку с уменьшением не сохраняем, а помечаем ошибкой.
        try:
            validate_reading_not_decreased(db, meter_id, reading_value, parsed_date)
        except HTTPException as exc:
            row_errors.append({"apartment_id": apartment_id, "detail": exc.detail})
            continue

        meter_reading = MeterReading(
            document_id=document.id,
            apartment_id=int(apartment_id),
            services_type_id=int(services_type_id),
            reading=Decimal(str(reading_value)),
            reading_date=parsed_date,
            meter_id=meter_id,
        )
        db.add(meter_reading)
        created_readings.append(meter_reading)

    if not created_readings:
        db.rollback()
        if not row_errors:
            raise HTTPException(status_code=422, detail="Нет корректных строк для сохранения")
        # Все строки отклонены с конкретными ошибками (например, показание меньше
        # предыдущего) — возвращаем их, чтобы фронтенд показал ошибки по строкам,
        # а не общий текст «Нет корректных строк для сохранения».
        return {
            "document": None,
            "created": [],
            "errors": row_errors,
        }

    db.commit()
    db.refresh(document)

    return {
        "document": meter_reading_document_serializer(document),
        "created": [{"id": r.id, "apartment_id": r.apartment_id} for r in created_readings],
        "errors": row_errors,
    }


@router.get("/meter_reading_documents/{document_id}/readings")
def get_document_readings(
    document_id: int,
    db: Session = Depends(get_db)
):
    document = db.query(MeterReadingDocument).filter(MeterReadingDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    readings = db.query(MeterReading).filter(MeterReading.document_id == document_id).all()

    return {
        "document": meter_reading_document_serializer(document),
        "readings": [meter_reading_serializer(r) for r in readings],
    }


@router.put("/meter_reading_documents/{document_id}/full")
def update_meter_reading_document_full(
    document_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_write_access),
):
    """
    Полностью обновляет документ показаний и пересоздаёт его строки: старые показания удаляются,
    новые создаются из присланного списка — аналогично bulk-созданию, но в режиме редактирования.
    """
    document = db.query(MeterReadingDocument).filter(MeterReadingDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    reading_date = payload.get("reading_date")
    services_type_id = payload.get("services_type_id")
    readings_data = payload.get("readings") or []

    if not reading_date or not services_type_id:
        raise HTTPException(status_code=422, detail="Заполните дату и вид услуги")
    if not readings_data:
        raise HTTPException(status_code=422, detail="Добавьте хотя бы одно показание")

    parsed_date = (
        datetime.strptime(reading_date, "%Y-%m-%d").date()
        if isinstance(reading_date, str)
        else reading_date
    )

    # Дата показаний не может быть в будущем (1.10 роадмапа).
    validate_date_not_future(parsed_date, "Дата показаний")

    document.title = build_meter_reading_document_title(
        parsed_date, _service_name(db, int(services_type_id))
    )
    document.reading_date = parsed_date
    document.services_type_id = services_type_id
    audit_document_update(document, user.id, "Изменение документа показаний")

    # Удаляем старые показания этого документа и создаём новые из присланного списка
    db.query(MeterReading).filter(MeterReading.document_id == document_id).delete(synchronize_session=False)
    db.flush()

    created_readings = []
    row_errors = []
    for row in readings_data:
        apartment_id = row.get("apartment_id")
        reading_value = row.get("reading")
        meter_id = row.get("meter_id")

        if apartment_id in (None, "") or reading_value in (None, ""):
            continue

        apartment = db.query(Apartment).filter(Apartment.id == int(apartment_id)).first()
        if not apartment:
            row_errors.append({"apartment_id": apartment_id, "detail": "Квартира не найдена"})
            continue

        if not meter_id:
            meter = (
                db.query(Meter)
                .filter(
                    Meter.apartment_id == int(apartment_id),
                    Meter.services_type_id == services_type_id,
                )
                .order_by(Meter.installed_at.desc().nullslast(), Meter.id.desc())
                .first()
            )
            meter_id = meter.id if meter else None

        # Показания нарастающие: строку с уменьшением не сохраняем, а помечаем ошибкой.
        try:
            validate_reading_not_decreased(db, meter_id, reading_value, parsed_date)
        except HTTPException as exc:
            row_errors.append({"apartment_id": apartment_id, "detail": exc.detail})
            continue

        meter_reading = MeterReading(
            document_id=document.id,
            apartment_id=int(apartment_id),
            services_type_id=services_type_id,
            reading=Decimal(str(reading_value)),
            reading_date=parsed_date,
            meter_id=meter_id,
        )
        db.add(meter_reading)
        created_readings.append(meter_reading)

    if not created_readings:
        db.rollback()
        if not row_errors:
            raise HTTPException(status_code=422, detail="Нет корректных строк для сохранения")
        # Все строки отклонены с конкретными ошибками — возвращаем их, чтобы
        # фронтенд показал ошибки по строкам (откат вернул прежние показания).
        return {
            "document": meter_reading_document_serializer(document),
            "updated": [],
            "errors": row_errors,
        }

    db.commit()
    db.refresh(document)

    return {
        "document": meter_reading_document_serializer(document),
        "updated": [{"id": r.id, "apartment_id": r.apartment_id} for r in created_readings],
        "errors": row_errors,
    }


@router.get("/accrual_documents/{document_id}/details")
def get_accrual_document_details(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Возвращает документ начислений вместе с его строками регистра, чтобы их можно было отредактировать."""
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    accruals = db.query(AccrualsRegister).filter(AccrualsRegister.accrual_document_id == document_id).all()
    serializer = SERIALIZERS.get(AccrualsRegister)

    year = document.accrual_date.year
    month = document.accrual_date.month

    return {
        "document": accrual_document_serializer(document),
        "accruals": [serializer(item) for item in accruals],
        "year": year,
        "month": month,
        "selections": [
            {"account_id": item.account_id, "services_type_id": item.services_type_id}
            for item in accruals
        ],
    }


@router.put("/accrual_documents/{document_id}/full")
async def update_accrual_document_full(
    document_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_write_access),
):
    """
    Полностью пересоздаёт строки регистра начислений для документа: старые строки удаляются,
    новые рассчитываются на сервере по присланным идентификаторам (account_id + services_type_id).
    Связанные записи регистра взаиморасчётов (accounts_register) также пересоздаются.
    """
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")
    # Разовые/персональные документы редактируются как история — не через месячный расчёт.
    if document.doc_kind == "oneoff":
        raise HTTPException(
            status_code=422,
            detail="Это разовый/персональный документ — он недоступен для месячного пересчёта; "
            "для правки используйте раздел разовых сборов.",
        )

    accrual_date_raw = payload.get("accrual_date")
    selections = payload.get("selections") or []

    if not isinstance(selections, list) or not selections:
        raise HTTPException(status_code=422, detail="Нет строк для начисления")

    requested_pairs: set[tuple[int, int]] = set()
    for row in selections:
        account_id = row.get("account_id")
        services_type_id = row.get("services_type_id")
        if account_id in (None, "") or services_type_id in (None, ""):
            continue
        requested_pairs.add((int(account_id), int(services_type_id)))

    if not requested_pairs:
        raise HTTPException(status_code=422, detail="Нет корректных строк для начисления")

    accrual_date = (
        datetime.strptime(accrual_date_raw, "%Y-%m-%d").date()
        if accrual_date_raw
        else document.accrual_date
    )
    if "comment" in payload:
        document.comment = (payload.get("comment") or "").strip() or None
    # Период начисления не может быть в будущем (1.10 роадмапа).
    now = date.today()
    if (accrual_date.year, accrual_date.month) > (now.year, now.month):
        raise HTTPException(status_code=422, detail="Нельзя начислить за будущий период")
    period_end = date(accrual_date.year, accrual_date.month, calendar.monthrange(accrual_date.year, accrual_date.month)[1])

    # Удаляем старые строки регистра вместе со связанными записями взаиморасчётов
    old_items = db.query(AccrualsRegister).filter(AccrualsRegister.accrual_document_id == document_id).all()
    old_ids = [item.id for item in old_items]
    # Аккаунты, затронутые удаляемыми строками, — их балансы тоже нужно пересчитать
    affected_accounts: set[int] = {item.account_id for item in old_items}
    if old_ids:
        db.execute(text("DELETE FROM accounts_register WHERE accrual_id = ANY(:ids)"), {"ids": old_ids})
        db.query(AccrualsRegister).filter(AccrualsRegister.id.in_(old_ids)).delete(synchronize_session=False)
        db.flush()

    document.accrual_date = accrual_date

    # Название документа всегда генерируется автоматически (1.9 роадмапа) —
    # ввод пользователя игнорируется.
    document.title = default_accrual_document_title(accrual_date)

    new_items = build_accrual_register_items(db, document, period_end, accrual_date, requested_pairs)
    if not new_items:
        db.rollback()
        raise HTTPException(status_code=422, detail="Нет корректных строк для начисления")

    db.add_all(new_items)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Нарушение целостности данных при сохранении начислений: {str(exc)}",
        ) from exc

    try:
        create_accounts_register_entries_for_accruals(db, new_items)
        # Пересчитываем балансы аккаунтов, которым начисление полностью убрали (старые строки),
        # а также новых. create_accounts_register_entries_for_accruals уже пересчитал новые, но
        # унифицированно пересчитываем все затронутые (дублирование безопасно).
        affected_accounts.update(item.account_id for item in new_items)
        for account_id in affected_accounts:
            recalculate_account_balance(db, account_id)
        audit_document_update(document, user.id, "Изменение документа начислений")
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Не удалось обновить записи в регистре взаиморасчётов: {str(exc)}",
        ) from exc

    # Пересоздание начислений влияет на регистр взаиморасчётов -> пересчитываем распределение.
    if affected_accounts:
        auto_recalculate_writeoffs(db, list(affected_accounts))

    db.refresh(document)

    serializer = SERIALIZERS.get(AccrualsRegister)
    updated_rows = [serializer(item) for item in new_items]

    return {
        "document": accrual_document_serializer(document),
        "updated": updated_rows,
    }


@router.put("/accrual_documents/{document_id}/amounts")
async def update_accrual_document_amounts(
    document_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_write_access),
):
    """Правит существующие строки ДОКУМЕНТА-ОДНОРАЗОВОГО («Разовые/персональные»).

    В отличие от «Начисление за месяц» (PUT .../full), здесь НЕ идёт пересчёт по
    регулярным тарифам: разовые/персональные сборы начисляются фиксированными
    суммами по тарифу из истории, поэтому правке доступна только СУММА строки
    (показания/потребление не используются). Изменяемое значение переносится и в
    реестр взаиморасчётов (accounts_register.income) с пересчётом балансов счёта.
    """
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")
    if document.doc_kind != "oneoff":
        raise HTTPException(
            status_code=422,
            detail="Этот документ — не разовый (oneoff); для месячного начисления используйте "
            "месячный пересчёт (PUT .../full).",
        )

    rows = payload.get("rows") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=422, detail="Нет строк для изменения")

    amounts: list[tuple[int, Decimal]] = []
    for row in rows:
        rid = row.get("id")
        amt = row.get("amount")
        if rid in (None, ""):
            continue
        try:
            dec = Decimal(str(amt))
        except Exception:
            continue
        if dec < 0:
            raise HTTPException(status_code=422, detail="Сумма не может быть отрицательной")
        amounts.append((int(rid), dec))

    ids = [rid for rid, _ in amounts]
    if not ids:
        raise HTTPException(status_code=422, detail="Нет корректных строк для изменения")

    items = db.query(AccrualsRegister).filter(
        AccrualsRegister.accrual_document_id == document_id,
        AccrualsRegister.id.in_(ids),
    ).all()
    if not items:
        raise HTTPException(status_code=404, detail="Строки начислений не найдены")

    amt_by_id = dict(amounts)
    affected_accounts: set[int] = set()
    for item in items:
        new_amount = amt_by_id.get(item.id)
        if new_amount is None:
            continue
        if item.amount == new_amount:
            continue
        item.amount = new_amount
        affected_accounts.add(item.account_id)
        # Синхронизируем реестр взаиморасчётов: у каждой строки начисления есть
        # соответствующая income-запись (accrual_id = строке) того же amount.
        db.execute(
            text("UPDATE accounts_register SET income = :amt WHERE accrual_id = :rid"),
            {"amt": new_amount, "rid": item.id},
        )

    if "comment" in payload:
        document.comment = (payload.get("comment") or "").strip() or None

    if not affected_accounts and "comment" not in payload:
        db.rollback()
        raise HTTPException(status_code=422, detail="Изменений нет")

    audit_document_update(document, user.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Нарушение целостности данных: {str(exc)}")

    if affected_accounts:
        for account_id in affected_accounts:
            recalculate_account_balance(db, account_id)
        try:
            auto_recalculate_writeoffs(db, list(affected_accounts))
        except Exception:
            db.rollback()
            raise HTTPException(status_code=409, detail="Не удалось пересчитать списания")
        db.commit()

    db.refresh(document)
    updated = [
        {"id": i.id, "account_id": i.account_id, "amount": float(i.amount)} for i in items
    ]
    return {"document": accrual_document_serializer(document), "updated": updated}
