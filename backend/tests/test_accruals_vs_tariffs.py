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
    """март-2024 «Фонд развития»: действует тариф-период 9560 и начисление равно 9560."""
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
