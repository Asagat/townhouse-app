"""tariff period conversion (двухфазная миграция, Фаза данных: 2.18)

Конверсия «массовых разовых повышений месяца» в единую месячную ленту тарифов:

- массовые oneoff-документы (>=2 л/с одного вида услуги с одинаковой ставкой,
  «Разовые сборы за <месяц>») переносятся в месячный документ соответствующего
  месяца как обычные строки начисления по новому «тарифу-периоду» (valid_from =
  начало месяца, valid_to = конец месяца);
- если в том же месячном документе уже была базовая строка того же вида услуги
  (единственный случай — март 2024 «Фонда» с досбором 7560 «Прочие расходы»),
  базовая строка переуказывается на суммарную ставку (база + досбор = 9560), а
  отдельный oneoff-документ удаляется (общая сумма по жильцу сохраняется);
- персональные/стартовые/выборочные/отрицательные oneoff-документы НЕ трогаются.

Выполнять только на изолированной песочнице (townhouse_phase0_test), прод не
затрагивает. Внутри Alembic идёт в транзакции; при необходимости отката — заново
развернуть песочницу из дампа (0016) и прогнать 0017 + 0018.

Revision ID: 0018_tariff_period_conversion
Revises: 0017_tariff_period
Create Date: 2026-09-08
"""
import calendar
from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_tariff_period_conversion"
down_revision: Union[str, Sequence[str], None] = "0017_tariff_period"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _month_bounds(ym: tuple[int, int]) -> tuple[date, date]:
    y, m = ym
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def upgrade() -> None:
    bind = op.get_bind()
    from sqlalchemy.orm import Session
    from models import (
        AccrualDocument,
        AccrualsRegister,
        ServiceType,
        Tariff,
        recalculate_account_balance,
    )

    session = Session(bind=bind)
    try:
        docs = {d.id: d for d in session.query(AccrualDocument).all()}
        # строки регистра по документу
        rows_by_doc = {}
        for r in session.query(AccrualsRegister).all():
            rows_by_doc.setdefault(r.accrual_document_id, []).append(r)

        # месячные документы по месяцам
        monthly_doc_by_ym = {
            (d.accrual_date.year, d.accrual_date.month): d
            for d in docs.values() if d.doc_kind == "monthly"
        }

        # --- выделяем массовые oneoff-документы ---
        affected_accounts: set[int] = set()

        def oneoff_massive():
            res = []
            for d in docs.values():
                if d.doc_kind != "oneoff":
                    continue
                rows = rows_by_doc.get(d.id, [])
                if len(rows) < 2:
                    continue
                svcs = {r.services_type_id for r in rows}
                amts = {float(r.amount) for r in rows}
                if len(svcs) == 1 and len(amts) == 1:
                    res.append((d, list(rows), next(iter(svcs)), next(iter(amts))))
            return res

        for doc, orows, svc_id, o_rate in oneoff_massive():
            sy, sm = doc.accrual_date.year, doc.accrual_date.month
            mdoc = monthly_doc_by_ym.get((sy, sm))
            if mdoc is None:
                raise RuntimeError(f"нет месячного документа {sy}-{sm:02d} — песочница повреждена?")
            accounts_of_one = [r.account_id for r in orows]

            # существующая база по этому виду услуги в месячном документе
            base_rows = [
                r for r in rows_by_doc.get(mdoc.id, [])
                if r.services_type_id == svc_id
            ]
            if base_rows:
                # Тип B: база есть → суммарная ставка месяца
                if len(amts := {float(r.amount) for r in base_rows}) != 1:
                    raise RuntimeError("неожиданная база (несколько ставок) по услуге "+str(svc_id))
                base_rate = next(iter(amts))
                period_rate = base_rate + o_rate   # напр. март-2024: 2000 + 7560 = 9560
            else:
                period_rate = o_rate               # Тип A: замена

            # тариф периода месяца
            vf, vt = _month_bounds((sy, sm))
            tariff = Tariff(
                services_type_id=svc_id,
                price=period_rate,
                valid_from=vf,
                comment=f"Конверсия 2.18: месячная ставка {period_rate:g} ({sy}-{sm:02d})",
            )
            tariff.valid_to = vt
            session.add(tariff)
            session.flush()

            if base_rows:
                # переводим базовые строки на суммарную ставку одной (меняем tariff/amount)
                for r in base_rows:
                    r.tariff_id = tariff.id
                    r.amount = period_rate
                affected_accounts |= {r.account_id for r in base_rows}
            else:
                # добавляем строки услуги по аккаунтам oneoff в месячный документ
                for acc in accounts_of_one:
                    nr = AccrualsRegister(
                        accrual_document_id=mdoc.id,
                        accrual_date=doc.accrual_date,
                        account_id=acc,
                        tariff_id=tariff.id,
                        services_type_id=svc_id,
                        current_reading_id=None,
                        past_reading_value=None,
                        current_reading_value=None,
                        consumption=0,
                        amount=period_rate,
                    )
                    session.add(nr)
                    affected_accounts.add(acc)

            # удаляем массовый oneoff документ (его строки уходят каскадом через рег.)
            o_ids = [r.id for r in orows]
            if o_ids:
                session.execute(sa.text(
                    "DELETE FROM accounts_register WHERE accrual_id = ANY(:ids)"
                ), {"ids": o_ids})
            for r in orows:
                session.delete(r)
            session.flush()
            session.delete(doc)
            session.flush()

        session.commit()

        # --- пересчёт балансов всех затронутых л/с ---
        for acc in affected_accounts:
            recalculate_account_balance(session, acc)
        session.commit()
    except Exception:
        session.rollback()
        raise


def downgrade() -> None:
    # Деструктивная конверсия (данные уже изменены). Обратный откат средствами
    # Alembic небезопасен; песочницу следует восстановить заново из дампа 0016.
    raise NotImplementedError(
        "0018 деструктивен: для отката разверните песочницу из дампа (0016) заново."
    )
