# backend/statement_pdf.py
"""PDF «Выписки по лицевому счёту» (роадмап 2.3 + Б15).

Два вида выписок на базе reportlab + кириллических TTF (шрифты/цвета — как
в квитанциях, `receipt_config.py`):
  - build_movements_pdf  — детализация движений по счёту (начисления/оплаты/списания)
                           за период: используется в ЛК жителя и просмотре администратора;
  - build_monthly_pdf    — помесячная выписка (начислено/списано/остаток): отчёт
                           «Выписка по счёту».

Возвращают готовые байты PDF; разметка/данные — вне модуля.
"""

import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import receipt_config as rc


def _ensure_fonts() -> None:
    if rc.FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(rc.FONT_REGULAR, rc.FONT_REGULAR_PATH))
    if rc.FONT_BOLD not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(rc.FONT_BOLD, rc.FONT_BOLD_PATH))


def _money(value, signed: bool = False) -> str:
    """«1 525,00» (signed=True — «+1 525,00»/«-1 525,00»)."""
    try:
        v = Decimal(str(value if value is not None else 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        v = Decimal("0.00")
    neg = v < 0
    v = abs(v)
    int_part, _, frac = f"{v}".partition(".")
    ip = f"{int(int_part):,}".replace(",", " ")
    body = f"{ip},{frac}"
    if signed:
        return f"+{body}" if not neg else f"-{body}"
    return f"-{body}" if neg else body


def _date_label(value) -> str:
    """Дата в формате ДД.ММ.ГГГГ (для строк/даты/времени)."""
    if value is None:
        return ""
    if isinstance(value, str):
        s = value[:10]
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return f"{s[8:10]}.{s[5:7]}.{s[:4]}"
        return s
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _render_pdf(title: str, subtitle_lines: list[str], headers: list[str],
                widths: list[float], rows: list[list[str]], total_row: list[str] | None,
                footer_note: str = "") -> bytes:
    _ensure_fonts()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "StTitle", parent=styles["Normal"], fontSize=rc.TITLE_SIZE,
        leading=rc.TITLE_SIZE + 3, spaceAfter=4, fontName=rc.FONT_BOLD,
        textColor=colors.HexColor(rc.COLOR_TEXT_TITLE),
    )
    text_style = ParagraphStyle(
        "StText", parent=styles["Normal"], fontSize=9, leading=12,
        fontName=rc.FONT_REGULAR, textColor=colors.HexColor(rc.COLOR_TEXT_CELL),
    )
    cell_style = ParagraphStyle(
        "StCell", parent=styles["Normal"], fontSize=rc.TABLE_SIZE, leading=11,
        fontName=rc.FONT_REGULAR, textColor=colors.HexColor(rc.COLOR_TEXT_CELL),
    )
    head_style = ParagraphStyle(
        "StHead", parent=styles["Normal"], fontSize=rc.TABLE_SIZE, leading=11,
        fontName=rc.FONT_BOLD, textColor=colors.HexColor(rc.COLOR_TEXT_HEADER_TABLE),
    )
    # Правосвязанные варианты — для денежных колонок (роадмап 2.16: суммы справа).
    head_right = ParagraphStyle("StHeadR", parent=head_style, alignment=2)
    cell_right = ParagraphStyle("StCellR", parent=cell_style, alignment=2)

    bio = io.BytesIO()
    doc = SimpleDocTemplate(
        bio, pagesize=A4,
        topMargin=rc.PAGE_TOP_MARGIN + 30, bottomMargin=rc.PAGE_BOTTOM_MARGIN,
        leftMargin=rc.PAGE_LEFT_MARGIN, rightMargin=rc.PAGE_RIGHT_MARGIN,
        title=title,
    )
    story = []
    story.append(Paragraph(title, title_style))
    for line in subtitle_lines:
        story.append(Paragraph(line, text_style))
    story.append(Spacer(1, 8))

    def _is_money(text: str) -> bool:
        return bool(text) and bool(re.fullmatch(r"[+-]?\d[\d ]*,\d{2}", str(text).strip()))

    money_cols: set[int] = set()
    for data_row in list(rows or []) + ([total_row] if total_row else []):
        for i, val in enumerate(data_row):
            if _is_money(val):
                money_cols.add(i)

    def _cell(text: str, head: bool = False, right: bool = False):
        esc = str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if head:
            return Paragraph(esc, head_right if right else head_style)
        return Paragraph(esc, cell_right if right else cell_style)

    table_rows = [[_cell(h, head=True, right=(i in money_cols)) for i, h in enumerate(headers)]]
    for r in rows:
        table_rows.append([_cell(c, right=(i in money_cols)) for i, c in enumerate(r)])
    if total_row:
        table_rows.append([_cell(c, right=(i in money_cols)) for i, c in enumerate(total_row)])

    table = Table(table_rows, colWidths=widths, repeatRows=1)
    grid = colors.HexColor(rc.COLOR_TABLE_GRID)
    style_cmds = [
        ("GRID", (0, 0), (-1, -1), 0.5, grid),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(rc.COLOR_HEADER_BG)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), rc.CELL_TOP_PADDING),
        ("BOTTOMPADDING", (0, 0), (-1, -1), rc.CELL_BOTTOM_PADDING),
    ]
    if total_row:
        style_cmds += [
            ("BACKGROUND", (0, len(table_rows) - 1), (-1, len(table_rows) - 1),
             colors.HexColor(rc.COLOR_TOTAL_BG)),
            ("FONTNAME", (0, len(table_rows) - 1), (-1, len(table_rows) - 1), rc.FONT_BOLD),
        ]
    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    if footer_note:
        story.append(Spacer(1, 10))
        story.append(Paragraph(footer_note, text_style))

    doc.build(story)
    return bio.getvalue()


def build_movements_pdf(account: dict, rows: list[dict], closing: float | None = None,
                        period_label: str = "за всё время") -> bytes:
    """Выписка-детализация движений по лицевому счёту."""
    subtitle = [
        f"Лицевой счёт {account.get('account_number', '')} — {account.get('account_name', '') or ''}"
        .rstrip(" -—"),
    ]
    apartment = account.get("apartment_number")
    owner = account.get("owner_name")
    if apartment is not None:
        subtitle.append(f"Квартира № {apartment}" + (f" — {owner}" if owner else ""))
    elif owner:
        subtitle.append(owner)
    subtitle.append(f"Период: {period_label}")

    headers = ["Дата", "Вид", "Услуга", "Сумма", "Баланс после"]
    widths = [62, 110, 180, 95, 108]
    data_rows = []
    acc_total = Decimal("0")
    for r in rows:
        amt = r.get("amount", 0) or 0
        acc_total += Decimal(str(amt))
        data_rows.append([
            _date_label(r.get("date")),
            str(r.get("kind_label") or ""),
            str(r.get("service") or ""),
            _money(amt, signed=True),
            _money(r.get("balance_after")),
        ])
    total_row = ["", "Итого", "", _money(acc_total, signed=True),
                 _money(closing if closing is not None else (rows[-1].get("balance_after") if rows else 0))]
    return _render_pdf("Выписка по лицевому счёту", subtitle, headers, widths,
                       data_rows, total_row)


def build_monthly_pdf(account: dict, monthly: list[dict], closing: float | None,
                      period_label: str = "за всё время") -> bytes:
    """Помесячная выписка: начислено / списано / остаток на конец месяца."""
    subtitle = [
        f"Лицевой счёт {account.get('account_number', '')} — {account.get('account_name', '') or ''}"
        .rstrip(" -—"),
    ]
    if account.get("apartment_number") is not None:
        subtitle.append(f"Квартира № {account.get('apartment_number')}"
                        + (f" — {account.get('owner_name')}" if account.get("owner_name") else ""))
    subtitle.append(f"Период: {period_label}")

    headers = ["Период", "Начислено", "Списано/оплачено", "Остаток на конец (долг)"]
    widths = [150, 135, 135, 150]
    data_rows = []
    for m in monthly:
        period = str(m.get("period") or "")
        if len(period) == 7:
            period = f"{period[5:]}.{period[:4]}"
        data_rows.append([
            period,
            _money(m.get("accrued")),
            _money(m.get("paid")),
            _money(m.get("closing")),
        ])
    total_row = ["Итого", "", "", _money(closing)]
    return _render_pdf("Выписка по лицевому счёту (помесячно)", subtitle, headers,
                       widths, data_rows, total_row,
                       footer_note="Примечание: «Остаток на конец» > 0 означает задолженность (долг) на конец периода.")


def _report_pdf(
    title: str,
    subtitle: list[str],
    page_landscape: bool,
    sections: list[tuple[str | None, list[str], list[float], list[list[str]], list[str] | None]],
) -> bytes:
    """PDF отчёта (2.16): одна-две таблицы подряд, общей платReportLab-каркас квитанций."""
    from reportlab.lib.units import cm as _cm_u
    from reportlab.lib.pagesizes import A4, landscape
    _cm = lambda v: v * _cm_u
    _ensure_fonts()
    page = landscape(A4) if page_landscape else A4
    styles = getSampleStyleSheet()
    t_style = ParagraphStyle("Rt", parent=styles["Normal"], fontSize=rc.TITLE_SIZE,
                              leading=rc.TITLE_SIZE + 3, spaceAfter=4, fontName=rc.FONT_BOLD,
                              textColor=colors.HexColor(rc.COLOR_TEXT_TITLE))
    txt_style = ParagraphStyle("Rs", parent=styles["Normal"], fontSize=9, leading=12,
                                fontName=rc.FONT_REGULAR, textColor=colors.HexColor(rc.COLOR_TEXT_CELL))
    cell_style = ParagraphStyle("Rc", parent=styles["Normal"], fontSize=rc.TABLE_SIZE, leading=11,
                                 fontName=rc.FONT_REGULAR, textColor=colors.HexColor(rc.COLOR_TEXT_CELL))
    head_style = ParagraphStyle("Rh", parent=styles["Normal"], fontSize=rc.TABLE_SIZE, leading=11,
                                 fontName=rc.FONT_BOLD, textColor=colors.HexColor(rc.COLOR_TEXT_HEADER_TABLE))
    cell_right = ParagraphStyle("RcR", parent=cell_style, alignment=2)
    head_right = ParagraphStyle("RhR", parent=head_style, alignment=2)
    sec_style = ParagraphStyle("Rk", parent=styles["Normal"], fontSize=10, leading=13, spaceBefore=10,
                                spaceAfter=4, fontName=rc.FONT_BOLD, textColor=colors.HexColor(rc.COLOR_TEXT_TITLE))
    grid = colors.HexColor(rc.COLOR_TABLE_GRID)
    head_bg = colors.HexColor(rc.COLOR_HEADER_BG)
    total_bg = colors.HexColor(rc.COLOR_TOTAL_BG)

    bio = io.BytesIO()
    doc = SimpleDocTemplate(
        bio, pagesize=page,
        topMargin=rc.PAGE_TOP_MARGIN + 30, bottomMargin=rc.PAGE_BOTTOM_MARGIN,
        leftMargin=rc.PAGE_LEFT_MARGIN, rightMargin=rc.PAGE_RIGHT_MARGIN, title=title,
    )
    story = [Paragraph(title, t_style)]
    for line in subtitle:
        story.append(Paragraph(line, txt_style))
    story.append(Spacer(1, 6))

    def _is_money(text: str) -> bool:
        return bool(text) and bool(re.fullmatch(r"[+-]?\d[\d ]*,\d{2}", str(text).strip()))

    def _cell(text: str, head: bool = False, right: bool = False):
        esc = str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if head:
            return Paragraph(esc, head_right if right else head_style)
        return Paragraph(esc, cell_right if right else cell_style)

    for caption, headers, widths, rows, total_row in sections:
        if not rows and not total_row:
            continue
        if caption:
            story.append(Paragraph(caption, sec_style))
        money_cols: set[int] = set()
        for data_row in list(rows or []) + ([total_row] if total_row else []):
            for i, val in enumerate(data_row):
                if _is_money(val):
                    money_cols.add(i)
        tbl = [[_cell(h, True, i in money_cols) for i, h in enumerate(headers)]]
        for r in rows:
            tbl.append([_cell(c, False, i in money_cols) for i, c in enumerate(r)])
        if total_row:
            tbl.append([_cell(c, True, i in money_cols) for i, c in enumerate(total_row)])
        table = Table(tbl, colWidths=widths, repeatRows=1)
        cmd = [
            ("GRID", (0, 0), (-1, -1), 0.5, grid),
            ("BACKGROUND", (0, 0), (-1, 0), head_bg),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), rc.CELL_TOP_PADDING),
            ("BOTTOMPADDING", (0, 0), (-1, -1), rc.CELL_BOTTOM_PADDING),
        ]
        if total_row:
            cmd += [
                ("BACKGROUND", (0, len(tbl) - 1), (-1, len(tbl) - 1), total_bg),
                ("FONTNAME", (0, len(tbl) - 1), (-1, len(tbl) - 1), rc.FONT_BOLD),
            ]
        table.setStyle(TableStyle(cmd))
        story.append(table)
    doc.build(story)
    return bio.getvalue()


def build_cash_register_report_pdf(data: dict) -> bytes:
    """PDF отчёта «По кассе» (2.16)."""
    from reportlab.lib.units import cm
    p = data.get("period") or {}
    subtitle = [f"Период: {_period_text(p.get('from'), p.get('to'))}"]
    sections = []
    headers = ["Касса/Счёт", "Нач. остаток", "Приход", "Расход", "Конечный остаток"]
    widths = [cm * w for w in (4.0, 2.4, 2.4, 2.4, 2.6)]
    rows = []
    for cp in data.get("cash_points", []):
        rows.append([cp.get("cash_point_name") or "", _money(cp.get("opening")),
                      _money(cp.get("income")), _money(cp.get("expense")),
                      _money(cp.get("closing"))])
    t = data.get("totals") or {}
    total = (["Итого", _money(t.get("opening")), _money(t.get("income")),
              _money(t.get("expense")), _money(t.get("closing"))]
             if data.get("cash_points") else None)
    sections.append(("Сводка по кассам/счетам", headers, widths, rows, total))

    headers2 = ["Дата", "Касса/Счёт", "Документ", "Счёт", "Статья", "Контрагент", "Приход", "Расход"]
    widths2 = [cm * w for w in (1.9, 2.3, 3.3, 1.7, 2.3, 2.5, 1.8, 1.8)]
    rows2 = []
    for m in data.get("movements", []):
        rows2.append([_date_label(m.get("operation_date") or ""), m.get("cash_point_name") or "",
                      m.get("document_title") or "", m.get("account_number") or "",
                      m.get("article_name") or "", m.get("contractor_name") or "",
                      _money(m.get("income")) if m.get("income") else "",
                      _money(m.get("expense")) if m.get("expense") else ""])
    sections.append(("Движения за период", headers2, widths2, rows2, None))
    return _report_pdf("Отчёт по кассе", subtitle, False, sections)


def build_expense_report_pdf(data: dict) -> bytes:
    """PDF отчёта «По расходам» (2.16)."""
    from reportlab.lib.units import cm
    p = data.get("period") or {}
    subtitle = [f"Период: {_period_text(p.get('from'), p.get('to'))}"]
    headers = ["Статья расхода", "Сумма"]
    widths = [cm * 8.0, cm * 3.2]
    rows = [[a.get("name") or "(без статьи)", _money(a.get("expense"))]
            for a in data.get("articles", [])]
    total = ["Итого", _money(data.get("total_expense"))] if data.get("articles") else None
    headers2 = ["Дата", "Документ", "Статья", "Контрагент", "Счёт", "Сумма"]
    widths2 = [cm * w for w in (2.2, 3.6, 2.8, 2.8, 2.0, 2.2)]
    rows2 = []
    for m in data.get("movements", []):
        rows2.append([_date_label(m.get("operation_date") or ""), m.get("document_title") or "",
                      m.get("article_name") or "", m.get("contractor_name") or "",
                      m.get("account_number") or "", _money(m.get("amount"))])
    total2 = (["Итого", "", "", "", "", _money(data.get("total_expense"))]
              if data.get("movements") else None)
    return _report_pdf("Отчёт по расходам", subtitle, False,
                       [("Разбивка по статьям", headers, widths, rows, total),
                        ("Документы расходов", headers2, widths2, rows2, total2)])


def build_debtors_report_pdf(data: dict) -> bytes:
    """PDF отчёта «По должникам» (2.16)."""
    from reportlab.lib.units import cm
    headers = ["Кв.", "Л/с", "Собственник", "Начислено", "Оплачено", "Долг"]
    widths = [cm * w for w in (1.3, 1.7, 5.0, 2.4, 2.4, 2.6)]
    rows = []
    for r in data.get("rows", []):
        rows.append([str(r.get("apartment_number") or ""), r.get("account_number") or "",
                     r.get("owner_name") or (r.get("account_name") or ""),
                     _money(r.get("accrued")), _money(r.get("paid")),
                     _money(r.get("debt"))])
    total = (["Итого", "", "", "", "", _money(data.get("total_debt"))]
             if data.get("rows") else None)
    sections = [("Должники", headers, widths, rows, total)] if rows else []
    return _report_pdf("Отчёт по должникам", [f"Должников: {data.get('count', 0)}"],
                       False, sections)


def _period_text(f: str | None, t: str | None) -> str:
    if f and t:
        return f"{_short_date(f)} — {_short_date(t)}"
    if f:
        return f"с {_short_date(f)}"
    if t:
        return f"по {_short_date(t)}"
    return "за всё время"


def _short_date(value: str) -> str:
    s = (value or "")[:10]
    if len(s) == 10:
        return f"{s[8:10]}.{s[5:7]}.{s[:4]}"
    return s


if __name__ == "__main__":  # pragma: no cover
    print("Модуль-хелпер: build_movements_pdf / build_monthly_pdf")
