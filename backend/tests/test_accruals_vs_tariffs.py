# tests/test_accruals_vs_tariffs.py
"""Согласованность «пересчёт начислений по тарифам» vs данные регистра.

Что проверяет:
  Для РЕГУЛЯРНЫХ начислений (документ doc_kind='monthly') сумма в accruals_register
  должна быть выводимой из применяемого тарифа по типу услуги:

    - «Фиксированный»    : amount == тариф.price
    - «По площади»        : amount == тариф.price × apartment.square
    - «По счетчику»       : amount == тариф.price × consumption (потребление на строке)

  Разовые/персональные начисления (doc_kind='oneoff': «Входящие остатки»,
  «Персональное доначисление …» и т.п.) хранят сумму, введённую вручную с комментарием
  причины, и НЕ обязаны равняться тарифу × N — их из проверки исключаем (эталон — comment).

  Отдельно валидируется март-2024 (известный расходящийся исторический период): ставка
  «Фонда развития» закрыта тарифом-периодом №268 = 9 560 ₸ на [2024-03-01..31]; после
  восстановления регистров строка начисления за март-2024 по «Фонду» должна быть равна 9560.

Тест read-only (без записи в БД), работает на импортированной dev/pre-prod БД.
"""

from sqlalchemy import text
import pytest

from services import calculate_accruals_preview

FIXED = "Фиксированный"
AREA = "По площади"
METER = "По счетчику"


def test_regular_accruals_match_tariff_formulas(db):
    """Сумма регулярных начислений == формуле по применяемому тарифу (тип услуги)."""
    rows = db.execute(text("""
        SELECT tt.name ttype, a.amount, t.price, ap.square, a.consumption,
               to_char(a.accrual_date,'YYYY-MM') ym
        FROM accruals_register a
        JOIN accrual_documents d ON d.id = a.accrual_document_id
        JOIN services_type sv ON sv.id = a.services_type_id
        LEFT JOIN tariff_types tt ON tt.id = sv.tariff_type_id
        LEFT JOIN tariffs t ON t.id = a.tariff_id
        LEFT JOIN accounts acc ON acc.id = a.account_id
        LEFT JOIN apartments ap ON ap.id = acc.apartment_id
        WHERE d.doc_kind = 'monthly'
          AND t.id IS NOT NULL
    """)).fetchall()

    mismatches = []
    for r in rows:
        ttype, amount = r[0], float(r[1])
        price = float(r[2]) if r[2] is not None else 0.0
        square = float(r[3] or 0.0)
        consumption = float(r[4] or 0.0)
        if ttype == FIXED:
            expected = price
        elif ttype == AREA:
            expected = price * square
        else:  # METER (и прочие по умолчанию — по потреблению)
            expected = price * consumption
        if abs(amount - expected) > 0.01:
            mismatches.append((r[5], ttype, amount, expected))

    assert not mismatches, (
        "Регулярные начисления не сходятся с тарифной формулой "
        f"(month/YM, тип, amount, expected):\n"
        + "\n".join(f"  {m}: amount={a:,.2f} vs expected={e:,.2f}" for m, t, a, e in mismatches[:30])
        + (f"\n  … всего {len(mismatches)}" if len(mismatches) > 30 else "")
    )


def test_march2024_fund_uses_closed_tariff_9560(db):
    """март-2024 «Фонд развития»: действует тариф-период 9560 и начисление равно 9560.

    Проверка имеет смысл только на БД с импортированной историей (есть начисления
    за март-2024 по «Фонду»). На пустой/свежей БД (disposable-CI после alembic +
    init_data, без истории) таких данных нет — тест пропускается, как и контрольные
    сверки с файлом-источником.
    """
    # Наличие исторического начисления «Фонда» за март-2024 — признак импортированных данных.
    has_march = db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM accruals_register a
            JOIN services_type sv ON sv.id=a.services_type_id
            WHERE sv.services_type='Фонд развития' AND a.accrual_date='2024-03-01'
        )
    """)).scalar()
    if not has_march:
        pytest.skip("Нет начислений «Фонда» за март-2024 (БД без импортированной истории)")

    tariff = db.execute(text("""
        SELECT id, price, status FROM tariffs
        WHERE valid_from <= '2024-03-31' AND valid_to >= '2024-03-01'
          AND services_type_id = (SELECT id FROM services_type WHERE services_type = 'Фонд развития')
          AND status = 'active'
    """)).fetchone()
    assert tariff is not None, "Нет активного тарифа «Фонда» на март-2024 (ожидалась месячная ставка 9560)"
    assert abs(float(tariff[1]) - 9560.0) < 0.005, f"Ставка март-2024 Фонда = {tariff[1]}, ожидалось 9560"

    mismatch = db.execute(text("""
        SELECT COUNT(*) FROM accruals_register a
        JOIN services_type sv ON sv.id=a.services_type_id
        WHERE sv.services_type='Фонд развития' AND a.accrual_date='2024-03-01'
          AND abs(a.amount - 9560.0) > 0.005
    """)).scalar()
    assert not mismatch, "По Фонду за март-2024 есть начисления, не равные тарифу 9560"


def test_accruals_preview_skips_accounts_later_opened(db):
    """Месячный превью учитывает opened_at (вариант A/вперёд).

    За период до открытия л/с счёт не должен появляться в месячном превью (иначе при
    пересоздании месячного он был бы «раскидан» на ещё не введённый л/с); с месяца
    открытия (opened_at <= конца месяца) — появляется. Данные открытия:
    кв4 (account_id=4) = 2017-12 ; кв8 (id=8) = 2017-11 ; кв1 (id=1) = 2017-10.
    Работает только на импортированной БД (accounts.opened_at заполнен).
    """
    has_open = db.execute(text("SELECT COUNT(*) FROM accounts WHERE opened_at IS NOT NULL")).scalar()
    if not has_open:
        pytest.skip("accounts.opened_at не заполнен (БД без миграции 0020/импортированной истории)")

    from datetime import date

    from models import Account
    from services import _account_open_for_period, calculate_accruals_preview

    def open_by_month(year: int, month: int):
        end = date(year, month, 28)
        return {
            a.account_number
            for a in db.query(Account).filter(Account.is_active == True).all()
            if _account_open_for_period(a, end)
        }

    # До открытия кв4/кв8 в превью месяца их нет.
    oct_2017 = open_by_month(2017, 10)
    assert "LS-0004" not in oct_2017, "кв4 не должна попадать в месячный превью до её открытия (2017-12)"
    assert "LS-0008" not in oct_2017, "кв8 не должна попадать в месячный превью до её открытия (2017-11)"

    # С месяца открытия счёт появляется: кв8 с 2017-11, кв4 с 2017-12.
    assert "LS-0008" in open_by_month(2017, 11)
    dec_2017 = open_by_month(2017, 12)
    assert "LS-0008" in dec_2017
    assert "LS-0004" in dec_2017

    # Сверка с фактическим превью: account_id в строках не содержит позже открытых.
    preview_rows = calculate_accruals_preview(db, 2017, 10)
    acc_ids = {r["account_id"] for r in preview_rows}
    assert 4 not in acc_ids and 8 not in acc_ids, f"превью за 2017-10 не должно включать кв4/кв8 (ids={sorted(acc_ids)})"
