# backend/routers/receipts.py
"""Квитанции (ЭТАП 3 роадмапа).

Вынесены из `app.py`: генерация квитанций (`receipt_documents/generate`), получение
строк (`items`), PDF на лету (`pdf`), массовый ZIP (`bulk_pdf`) и массовое удаление
(`bulk_delete`). Логика и PDF-вёрстка сохранены без изменений.
"""

import calendar
import io
import os
import zipfile
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from database import get_db
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

import receipt_config as rc
from auth import get_current_user
from models import Account, AccrualsRegister, ReceiptDocument, ReceiptItem, ServiceType, User
from serializers import SERIALIZERS, receipt_document_serializer
from services import FUND_SERVICE_FALLBACK, _service_name, audit_document_create


router = APIRouter(prefix="/api")


# --- ЭНДПОИНТЫ ДЛЯ КВИТАНЦИЙ ---


def _fund_service_id(db) -> int | None:
    """ID услуги «Фонд развития» (сюда «садится» общий долг/переплата счёта в квитанции).

    Определяется динамически по имени из справочника, а не по жёсткому ID
    (раньше был захардкожен 7, что ломало генерацию, если «Фонд развития» имеет другой id).
    """
    svc = db.query(ServiceType).filter(ServiceType.services_type == FUND_SERVICE_FALLBACK).first()
    return svc.id if svc else None

def _account_debt_overpayment(db: Session, account_id: int) -> tuple[float, float]:
    """Возвращает (долг, переплата) по счёту на основе регистров.

    - долг = начислено - списано (>=0);
    - переплата = внесено на счёт - списано (>=0) — аванс сверх распределённых услуг.
    Согласовано с метриками отчёта build_account_statement (баланс/квитанции сходятся).
    """
    accrued_total = db.execute(
        text("SELECT COALESCE(SUM(income),0) FROM accounts_register WHERE account_id=:a AND services_type_id IS NOT NULL"),
        {"a": account_id},
    ).scalar()
    paid_total = db.execute(
        text("SELECT COALESCE(SUM(expense),0) FROM accounts_register WHERE account_id=:a AND services_type_id IS NOT NULL"),
        {"a": account_id},
    ).scalar()
    available = db.execute(
        text("SELECT COALESCE(SUM(income - expense),0) FROM cash_register WHERE account_id=:a"),
        {"a": account_id},
    ).scalar()
    accrued_total = float(accrued_total or 0.0)
    paid_total = float(paid_total or 0.0)
    available = float(available or 0.0)
    debt = max(0.0, accrued_total - paid_total)
    overpayment = max(0.0, available - paid_total)
    return debt, overpayment


def generate_receipt_document(
    db: Session, account: Account, year: int, month: int, user_id: int | None = None
) -> ReceiptDocument | None:
    """
    Формирует квитанцию для одного лицевого счёта за период.
    Возвращает None, если за период нет начислений.
    """
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])

    accruals = (
        db.query(AccrualsRegister)
        .filter(
            AccrualsRegister.account_id == account.id,
            AccrualsRegister.accrual_date >= start,
            AccrualsRegister.accrual_date <= end,
        )
        .all()
    )
    if not accruals:
        return None

    apartment = account.apartment
    owner_name = apartment.owner.full_name if apartment and apartment.owner else ""

    receipt = ReceiptDocument(
        account_id=account.id,
        period_year=year,
        period_month=month,
        apartment_number=apartment.apartment_number if apartment else None,
        address=apartment.address if apartment else None,
        owner_name=owner_name,
        account_number=account.account_number,
    )
    audit_document_create(receipt, user_id)
    db.add(receipt)
    db.flush()

    # Долг и переплата счёта на основе регистров (см. «КОНВЕНЦИЯ ЗНАКОВ»):
    # долг = начислено - списано, переплата = внесено - списано (аванс).
    debt, overpayment = _account_debt_overpayment(db, account.id)

    total_amount = 0.0
    created_items: list[ReceiptItem] = []
    for acc in accruals:
        tariff = acc.tariff.price if acc.tariff else 0
        amount = float(acc.amount)
        total_amount += amount
        item = ReceiptItem(
            receipt_id=receipt.id,
            services_type_id=acc.services_type_id,
            service_name=_service_name(db, acc.services_type_id),
            reading_prev=acc.past_reading_value,
            reading_curr=acc.current_reading_value,
            quantity=acc.consumption,
            tariff=tariff,
            amount=amount,
            debt=0.0,
            overpayment=0.0,
            payable=amount,
        )
        db.add(item)
        created_items.append(item)

    # Долг/переплату садим на строку «Фонд развития» (id услуги из справочника).
    # Ищем среди уже созданных строк фонда из начислений; если таковой нет — создаём отдельную.
    fund_service_id = _fund_service_id(db)
    fund_row = next(
        (x for x in created_items if x.services_type_id == fund_service_id),
        None,
    )
    if fund_row is None:
        fund_row = ReceiptItem(
            receipt_id=receipt.id,
            services_type_id=fund_service_id,
            service_name=FUND_SERVICE_FALLBACK,
            reading_prev=None,
            reading_curr=None,
            quantity=1,
            tariff=0.0,
            amount=0.0,
            debt=0.0,
            overpayment=0.0,
            payable=0.0,
        )
        db.add(fund_row)
    # «Садим» общий баланс (долг ИЛИ переплата) на строку фонда: payable = amount + долг - переплата
    fund_row.debt = debt
    fund_row.overpayment = overpayment
    fund_row.payable = float(fund_row.amount or 0.0) + debt - overpayment

    receipt.total_amount = total_amount
    receipt.debt = debt
    receipt.overpayment = overpayment
    receipt.payable_amount = total_amount + debt - overpayment

    return receipt


@router.post("/receipt_documents/generate", status_code=201)
def generate_receipts(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Массово формирует квитанции по всем активным лицевым счетам за период."""
    year = payload.get("year")
    month = payload.get("month")
    if year in (None, "") or month in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите месяц и год")
    year = int(year)
    month = int(month)
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Некорректный месяц")

    accounts = db.query(Account).filter(Account.is_active == True).all()
    created = []
    for account in accounts:
        rec = generate_receipt_document(db, account, year, month, user_id=user.id)
        if rec:
            created.append(rec)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Не удалось сохранить квитанции: {str(exc)}")

    serializer = SERIALIZERS.get(ReceiptDocument)
    rows = []
    for rec in created:
        db.refresh(rec)
        rows.append(serializer(rec) if serializer else {"id": rec.id})
    return {"year": year, "month": month, "created": rows}


def _raise_for_resident_other(user: User | None, own_account_id: int, receipt: ReceiptDocument) -> None:
    """resident может видеть только свои квитанции (по привязке users.account_id)."""
    if (
        user is not None
        and getattr(user, "role", None) is not None
        and user.role.name == "resident"
    ):
        own = getattr(user, "account_id", None)
        if not own or int(own) != int(receipt.account_id):
            raise HTTPException(status_code=403, detail="Нет доступа к этой квитанции")


@router.get("/me/receipts")
def get_my_receipts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список квитанций текущего пользователя (ЛК жителя), по его счёту."""
    account_id = getattr(user, "account_id", None)
    if not account_id:
        raise HTTPException(status_code=404, detail="Лицевой счёт не привязан к пользователю")
    receipts = (
        db.query(ReceiptDocument)
        .filter(ReceiptDocument.account_id == int(account_id))
        .order_by(ReceiptDocument.period_year.desc(), ReceiptDocument.period_month.desc(), ReceiptDocument.id.desc())
        .all()
    )
    serializer = SERIALIZERS.get(ReceiptDocument)
    return [serializer(r) for r in receipts] if serializer else []


@router.get("/receipt_documents/{document_id}/items")
def get_receipt_items(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    receipt = db.get(ReceiptDocument, document_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Квитанция не найдена")
    _raise_for_resident_other(user, None, receipt)
    items = db.query(ReceiptItem).filter(ReceiptItem.receipt_id == document_id).all()
    serializer = SERIALIZERS.get(ReceiptItem)
    return {
        "document": receipt_document_serializer(receipt),
        "items": [serializer(i) for i in items] if serializer else [],
    }


@router.get("/receipt_documents/{document_id}/pdf")
def get_receipt_pdf(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    inline: bool = Query(False, description="inline=true — показать в браузере, иначе скачивание"),
):
    """Генерирует PDF квитанции на лету. inline=true открывает в просмотрщике, иначе скачивает."""
    receipt = (
        db.query(ReceiptDocument)
        .options(joinedload(ReceiptDocument.items))
        .get(document_id)
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Квитанция не найдена")
    _raise_for_resident_other(user, None, receipt)

    pdf_bytes = build_receipt_pdf(receipt)
    filename = f"receipt_{receipt.id}_{receipt.period_month:02d}_{receipt.period_year}.pdf"
    if inline:
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=\"{filename}\""},
        )
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


@router.post("/receipt_documents/bulk_pdf")
def bulk_receipt_pdf(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    """Массово скачивает квитанции за период одним ZIP-архивом."""
    year = payload.get("year")
    month = payload.get("month")
    if year in (None, "") or month in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите месяц и год")
    year = int(year)
    month = int(month)

    receipts = (
        db.query(ReceiptDocument)
        .options(joinedload(ReceiptDocument.items))
        .filter(ReceiptDocument.period_year == year, ReceiptDocument.period_month == month)
        .all()
    )
    if not receipts:
        raise HTTPException(status_code=404, detail="Квитанции за выбранный период не найдены")

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rec in receipts:
            pdf = build_receipt_pdf(rec)
            fname = f"Квитанция_{rec.apartment_number}_{rec.period_month:02d}.{rec.period_year}.pdf"
            # безопасное имя в архиве
            zf.writestr(fname, pdf)
    bio.seek(0)

    return StreamingResponse(
        bio,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"receipts_{month:02d}_{year}.zip\""
        },
    )


@router.delete("/receipt_documents/bulk_delete")
def bulk_delete_receipts(
    year: int,
    month: int,
    db: Session = Depends(get_db),
):
    """Массово удаляет квитанции за период (строки удаляются каскадно)."""
    deleted = db.query(ReceiptDocument).filter(
        ReceiptDocument.period_year == year,
        ReceiptDocument.period_month == month,
    ).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


def _fmt_amount2(value) -> str:
    """Формат: пробелы как разделители тысяч, запятая как десятичный. Напр. «1 525,00»."""
    try:
        v = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        v = Decimal("0.00")
    neg = ""
    if v < 0:
        neg = "-"
        v = -v
    int_part, _, frac = f"{v}".partition(".")
    ip = f"{int(int_part):,}".replace(",", " ")
    return f"{neg}{ip},{frac}"


def _fmt_reading(value) -> str:
    if value is None:
        return "-"
    v = Decimal(str(value))
    if v == v.to_integral_value():
        return f"{int(v)}"
    return f"{v}"


def build_receipt_pdf(receipt: ReceiptDocument) -> bytes:
    """Вёрстка PDF квитанции в стиле шаблона «Квитанция.pdf» (+ столбец «Переплата»)."""
    # Поддержка кириллицы: регистрируем TTF-шрифты.
    FONT = rc.FONT_REGULAR
    FONT_B = rc.FONT_BOLD
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, rc.FONT_REGULAR_PATH))
    if FONT_B not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_B, rc.FONT_BOLD_PATH))

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title2", parent=styles["Normal"], fontSize=rc.TITLE_SIZE,
        leading=rc.TITLE_SIZE + 3, spaceAfter=2, leftIndent=0, fontName=FONT_B,
        textColor=colors.HexColor(rc.COLOR_TEXT_TITLE),
    )
    brand_style = ParagraphStyle(
        "Brand", parent=styles["Normal"], fontSize=rc.BRAND_SIZE,
        leading=rc.BRAND_SIZE + 2, fontName=FONT_B,
        textColor=colors.HexColor(rc.COLOR_BRAND_TEXT),
    )
    period_style = ParagraphStyle(
        "Period", parent=styles["Normal"], fontSize=rc.PERIOD_SIZE,
        spaceAfter=6, leftIndent=0, fontName=FONT_B,
        textColor=colors.HexColor(rc.COLOR_TEXT_PERIOD),
    )
    head_style = ParagraphStyle(
        "Head", parent=styles["Normal"], fontSize=rc.HEAD_SIZE,
        spaceAfter=14, leftIndent=0, fontName=FONT_B,
        textColor=colors.HexColor(rc.COLOR_TEXT_HEAD),
    )

    month_names = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
    ]
    period = f"{month_names[receipt.period_month - 1].capitalize()} {receipt.period_year}"
    # Логотип (если файл доступен)
    logo_path = rc.LOGO_PATH
    if not os.path.isabs(logo_path):
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), logo_path)
    has_logo = os.path.exists(logo_path)
    logo_w = rc.LOGO_WIDTH
    # Пропорции: если включена высота не задана — берём из реального файла
    if rc.LOGO_HEIGHT:
        logo_h = rc.LOGO_HEIGHT
    elif has_logo:
        from PIL import Image as _PILImage
        _w, _h = _PILImage.open(logo_path).size
        logo_h = logo_w * (_h / _w) if _w else logo_w
    else:
        logo_h = logo_w * (90 / 73)

    # Строка шапки: слева «Квитанция», справа логотип + «Family Townhouse» (прижато вправо)
    left = Paragraph(rc.TEXT_TITLE, title_style)
    brand_text = Paragraph(rc.TEXT_BRAND, brand_style)
    if has_logo:
        brand = Table(
            [[
                Image(logo_path, width=logo_w, height=logo_h),
                brand_text,
            ]],
            colWidths=[logo_w + 6, 150],
            hAlign="LEFT",
        )
        brand.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        # head_row: левый блок, растягивающийся пустырь, brand — прижат вправо
        head_row = Table(
            [[left, "", brand]],
            colWidths=[120, None, 196],
            hAlign="LEFT",
        )
    else:
        head_row = Table(
            [[left, "", brand_text]],
            colWidths=[120, None, 196],
            hAlign="LEFT",
        )
    head_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    head_row.spaceBefore = 0
    header = [Spacer(1, rc.HEADER_SPACER), head_row]
    header.append(Paragraph(period, period_style))
    header.append(
        Paragraph(
            f"Квартира № {receipt.apartment_number} {receipt.owner_name}",
            head_style,
        )
    )

    # Двухуровневая шапка: «Показания» — объединённая ячейка над Пред./Послед.
    data = [
        [
            rc.COL_Услуга, rc.COL_Показания, rc.COL_Показания, rc.COL_Колво,
            rc.COL_Тариф, rc.COL_Сумма, rc.COL_Долг, rc.COL_Переплата, rc.COL_Коплате,
        ],
        [
            "", rc.COL_Пред, rc.COL_Послед, "", "", "", "", "", "",
        ],
    ]
    for it in sorted(receipt.items, key=lambda x: (x.services_type_id is None, x.id)):
        data.append([
            it.service_name,
            _fmt_reading(it.reading_prev),   # Пред.
            _fmt_reading(it.reading_curr),   # Послед.
            _fmt_amount2(it.quantity) if it.quantity is not None else "-",
            _fmt_amount2(it.tariff) if it.tariff is not None else "-",
            _fmt_amount2(it.amount),
            _fmt_amount2(it.debt) if it.debt else "0,00",
            _fmt_amount2(it.overpayment) if it.overpayment else "0,00",
            _fmt_amount2(it.payable),
        ])
    data.append([
        rc.COL_Итого, "", "", "", "", _fmt_amount2(receipt.total_amount),
        _fmt_amount2(receipt.debt) if receipt.debt else "0,00",
        _fmt_amount2(receipt.overpayment) if receipt.overpayment else "0,00",
        _fmt_amount2(receipt.payable_amount),
    ])

    col_widths = rc.COL_WIDTHS
    table = Table(data, colWidths=col_widths, repeatRows=2)
    gray = colors.HexColor(rc.COLOR_TABLE_GRID)          # серые границы
    even = colors.HexColor(rc.COLOR_ROW_EVEN)            # чётная строка
    odd = colors.HexColor(rc.COLOR_ROW_ODD)              # нечётная строка
    header_bg = colors.HexColor(rc.COLOR_HEADER_BG)
    total_bg = colors.HexColor(rc.COLOR_TOTAL_BG)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, gray),
        ("BOX", (0, 0), (-1, -1), 0.8, gray),
        # Чередование фона строк данных (перекрывается нижними командами для шапки/итога)
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [even, odd]),
        ("BACKGROUND", (0, 0), (-1, 1), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.HexColor(rc.COLOR_TEXT_HEADER_TABLE)),
        ("TEXTCOLOR", (0, 2), (-1, -2), colors.HexColor(rc.COLOR_TEXT_CELL)),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor(rc.COLOR_TEXT_TOTAL)),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), rc.TABLE_SIZE),
        ("FONTNAME", (0, 0), (-1, 1), FONT_B),
        ("ALIGN", (1, 2), (-1, -1), "RIGHT"),
        ("ALIGN", (1, 0), (-1, 1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), rc.CELL_TOP_PADDING),
        ("BOTTOMPADDING", (0, 0), (-1, -1), rc.CELL_BOTTOM_PADDING),
        # Объединение ячеек шапки (строка 0 и 1)
        ("SPAN", (1, 0), (2, 0)),
        ("SPAN", (0, 0), (0, 1)),
        ("SPAN", (3, 0), (3, 1)),
        ("SPAN", (4, 0), (4, 1)),
        ("SPAN", (5, 0), (5, 1)),
        ("SPAN", (6, 0), (6, 1)),
        ("SPAN", (7, 0), (7, 1)),
        ("SPAN", (8, 0), (8, 1)),
        ("SPAN", (0, -1), (4, -1)),
        ("FONTNAME", (0, -1), (-1, -1), FONT_B),
        ("BACKGROUND", (0, -1), (-1, -1), total_bg),
    ]))

    issued = receipt.issued_at
    stamp = issued.strftime("%d.%m.%Y %H:%M:%S") if issued else ""
    date_style = ParagraphStyle(
        "DateS", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor(rc.COLOR_STAMP),
        spaceBefore=18, alignment=2, fontName=FONT,
    )
    footer = [Paragraph(stamp, date_style)]

    story = header + [Spacer(1, 2), table] + footer
    buf = io.BytesIO()
    SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=rc.PAGE_TOP_MARGIN, bottomMargin=rc.PAGE_BOTTOM_MARGIN,
        leftMargin=rc.PAGE_LEFT_MARGIN, rightMargin=rc.PAGE_RIGHT_MARGIN,
    ).build(story)
    return buf.getvalue()
