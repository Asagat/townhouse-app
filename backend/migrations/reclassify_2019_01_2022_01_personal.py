"""Реклассификация 2019‑01 и 2022‑01: месячные vs персональные начисления Фонда.

Правила (владелец, 09.2026): месячный документ начислений — «всем, у кого л/с уже
открыт»; что остаётся «не‑по‑всем» или индивидуальным → персональное. Здесь два
выявленных месяца, где Фонд развития распределён неверно между monthly/перс:

1. **2019‑01** — месячный Фонд 10 000 в doc 21 лежит только у 9 л/с, а у восьми
   (кв 4,7,9,11,12,13,14,17) он попал внутрь oneoff-документов 22–29 по 12 000
   (строка сшила месячный Фонд 10 000 и аудит 2 000).
   → месячному doc 21 добавить Фонд 10 000 восьми без него; у oneoff 22–29
     понизить 12 000 → 2 000 («аудит дымоходов» остаётся перс.).
   Нагрузка каждого л/с за месяц не меняется (12 000 ⇄ 10 000 + 2 000).

2. **2022‑01** — месячный doc 71 несёт Фонд 6 000 у 13 л/с (спец‑сбор
   «парковка/освещение» из «Прочие расходы»; у кв 4,5,10,17 его нет).
   REGULAR месячного Фонда в январе нет. По правилу «не‑по‑всем → перс.» его
   выносим в отдельный перс‑документ oneoff января‑2022 на те же 13 л/с.

Суммарные начисления/долг каждого л/с и дома за месяц не меняются (перенос строк
monthly <-> перс), для 2019 — понижение существующего oneoff компенсирует добавку
в месячный. Изменения документов влияют на регистр взаиморасчётов → точечная
перепроводка затрагиваемых счетов.

Идемпотентен (dry-run/`--apply`, как прочие data-миграции):
    python migrations/reclassify_2019_01_2022_01_personal.py            # dry-run
    python migrations/reclassify_2019_01_2022_01_personal.py --apply    # применить
"""

import os
import sys
from datetime import date

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    AccrualDocument,
    AccrualsRegister,
    recalculate_account_balance,
)
from services import audit_document_update  # noqa: E402

FUND_SVC = None           # заполняется на старте (id услуги «Фонд развития»)
AUDIT_USER = 1            # пользователь 'migration' (admin)
CHANGE_DESC = "Реклассификация monthly/перс: месячный Фонд на всех л/с, перс-компонент вынесен (09.09.2026)"

KV8_2019 = [4, 7, 9, 11, 12, 13, 14, 17]          # кв без месячного Фонда-10000 в 2019-01
KV13_2022 = [1, 2, 3, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16]   # спец-сбор 2022-01 (13 л/с)


def _svc_id(db, name):
    return db.execute(text("SELECT id FROM services_type WHERE services_type=:n"), {"n": name}).first()[0]


def _fund_rows(db, doc_id):
    """Список (accrual_id, kv, amount, doc_id) по услуге «Фонд» в документе."""
    return db.execute(
        text(
            "SELECT ar.id, ap.apartment_number, ar.amount, ar.accrual_document_id "
            "FROM accruals_register ar "
            "JOIN accounts a ON a.id = ar.account_id "
            "JOIN apartments ap ON ap.id = a.apartment_id "
            "WHERE ar.accrual_document_id=:d AND ar.services_type_id=:s "
            "ORDER BY ap.apartment_number"
        ),
        {"d": doc_id, "s": FUND_SVC},
    ).fetchall()


def plan_2019(db):
    """(add_kv, lower) для 2019-01."""
    present = {r[1] for r in _fund_rows(db, 21)}
    add_kv = [kv for kv in KV8_2019 if kv not in present]
    lower = []
    for doc_id in range(22, 30):
        for r in _fund_rows(db, doc_id):
            if r[1] in KV8_2019 and float(r[2]) == 12000.0:
                lower.append({"id": r[0], "doc": doc_id, "kv": r[1]})
    return add_kv, lower


def plan_2022(db):
    return [{"id": r[0], "kv": r[1], "amt": float(r[2])} for r in _fund_rows(db, 71) if r[1] in KV13_2022]


def _existing_personal_2022(db):
    return db.execute(
        text("SELECT id FROM accrual_documents WHERE doc_kind='oneoff' "
             "AND to_char(accrual_date,'YYYY-MM')='2022-01' "
             "AND title LIKE 'Персональный сбор за январь 2022%' LIMIT 1")
    ).first()


def apply(db):
    affected: set[int] = set()

    # ---------- 2019-01 ----------
    add_kv, lower = plan_2019(db)
    for kv in add_kv:
        exists = db.execute(
            text("SELECT 1 FROM accruals_register WHERE accrual_document_id=21 "
                 "AND account_id=:a AND services_type_id=:s"),
            {"a": kv, "s": FUND_SVC},
        ).first()
        if exists:
            continue
        item = AccrualsRegister(
            accrual_document_id=21,
            accrual_date=date(2019, 1, 1),
            account_id=kv,
            tariff_id=21,               # Фонд 10 000 (действ. с 2017-11)
            services_type_id=FUND_SVC,
            current_reading_id=None, past_reading_value=None,
            current_reading_value=None, consumption=0,
            amount=10000.00,
        )
        db.add(item)
        db.flush()
        # income хронологически: operation_date = дата начисления
        db.execute(
            text("INSERT INTO accounts_register (operation_date, account_id, accrual_id, "
                 "services_type_id, income, expense, balance_after) "
                 "VALUES (:op,:a,:accr,:svc,:inc,0,0)"),
            {"op": date(2019, 1, 1), "a": kv, "accr": item.id,
             "svc": FUND_SVC, "inc": 10000.0},
        )
        affected.add(kv)

    for r in lower:
        db.execute(text("UPDATE accruals_register SET amount=2000 WHERE id=:i"), {"i": r["id"]})
        db.execute(text("UPDATE accounts_register SET income=2000 WHERE accrual_id=:i"), {"i": r["id"]})
        affected.add(r["kv"])

    doc21 = db.query(AccrualDocument).get(21)
    if doc21:
        base = (doc21.comment or "").strip()
        note = "Месячный Фонд 10 000 за январь-2019 восстановлен на все л/с (17); аудит дымоходов 2 000 вынесен в перс. начисления."
        doc21.comment = (base + " | " + note).strip(" |") if base else note
        audit_document_update(doc21, AUDIT_USER, CHANGE_DESC)
    for rid in range(22, 30):
        d = db.query(AccrualDocument).get(rid)
        if d is not None:
            audit_document_update(d, AUDIT_USER, CHANGE_DESC)

    # ---------- 2022-01 ----------
    rows2022 = plan_2022(db)
    pers_id = None
    moved = 0
    if rows2022:
        found = _existing_personal_2022(db)
        if found is not None:
            pers_id = found[0]
        else:
            doc = AccrualDocument(
                accrual_date=date(2022, 1, 1),
                title="Персональный сбор за январь 2022 (парковка/освещение)",
                doc_kind="oneoff",
                comment="Спец-сбор 6 000 на 13 л/с (перенос «Прочие расходы» в Фонд) — отдельный перс. документ.",
            )
            audit_document_update(doc, AUDIT_USER, CHANGE_DESC)
            db.add(doc)
            db.flush()
            pers_id = doc.id
        for r in rows2022:
            cur = db.execute(text("SELECT accrual_document_id FROM accruals_register WHERE id=:i"), {"i": r["id"]}).first()
            if cur is not None and cur[0] != pers_id:
                db.execute(text("UPDATE accruals_register SET accrual_document_id=:p WHERE id=:i"), {"p": pers_id, "i": r["id"]})
                moved += 1
            affected.add(r["kv"])
        doc71 = db.query(AccrualDocument).get(71)
        if doc71 is not None:
            base = (doc71.comment or "").strip()
            note = "Спец-сбор парковка/освещение 6 000 (13 л/с) вынесен в перс. документ; регулярного Фонда в январе-2022 нет."
            doc71.comment = (base + " | " + note).strip(" |") if base else note
            audit_document_update(doc71, AUDIT_USER, CHANGE_DESC)

    db.commit()

    for acct in sorted(affected):
        recalculate_account_balance(db, acct)
    db.commit()

    return {
        "added_monthly_2019": add_kv,
        "lowered_personal_2019": [{"kv": r["kv"], "doc": r["doc"]} for r in lower],
        "created_new_2022_doc": pers_id,
        "moved_2022": moved,
        "affected_accounts": sorted(affected),
    }


def integrity_report(db):
    print("\n== Контроль 2019-01 (doc21 monthly + oneoff 22–29), кв 4..17 ==")
    for r in db.execute(text(
        "SELECT ap.apartment_number, "
        " COALESCE((SELECT SUM(x.amount) FROM accruals_register x "
        "           WHERE x.account_id=a.id AND x.accrual_document_id=21),0), "
        " COALESCE((SELECT SUM(y.amount) FROM accruals_register y "
        "           WHERE y.account_id=a.id AND y.accrual_document_id BETWEEN 22 AND 29),0) "
        "FROM accounts a JOIN apartments ap ON ap.id=a.apartment_id "
        "WHERE ap.apartment_number BETWEEN 4 AND 17 "
        "ORDER BY ap.apartment_number")).fetchall():
        if float(r[1]) or float(r[2]):
            print(f"   кв {r[0]:>2}: monthly={float(r[1]):>10,.2f}  oneoff={float(r[2]):>9,.2f}")


def main():
    global FUND_SVC
    db = SessionLocal()
    try:
        FUND_SVC = _svc_id(db, "Фонд развития")
        add_kv, lower = plan_2019(db)
        rows2022 = plan_2022(db)
        print(f"Услуга «Фонд развития» id={FUND_SVC}")
        print("== 2019-01: добавить месячный Фонд 10 000 в doc21 (кв) ==")
        print("   ", add_kv or "нет")
        print("== 2019-01: oneoff 22–29 понизить 12 000 → 2 000 ==")
        for r in lower:
            print(f"     аккр={r['id']} кв={r['kv']:>2} doc={r['doc']} -> 2000")
        print("== 2022-01: перенести спец-сбор 6 000 из doc71 в перс. ==")
        for r in rows2022:
            print(f"     аккр={r['id']} кв={r['kv']:>2} amount={r['amt']:.0f}")
        if add_kv or lower or rows2022:
            print("\ndry-run: для применения используйте --apply")
        if "--apply" not in sys.argv:
            return
        out = apply(db)
        print("\n== ПРИМЕНЕНО ==")
        print("  месячных Фонда добавлено (2019-01):", out["added_monthly_2019"])
        print("  oneoff понижено (2019-01):", out["lowered_personal_2019"])
        print("  перс-документ 2022-01 id:", out["created_new_2022_doc"], " перенесено строк:", out["moved_2022"])
        print("  пересчитаны счета:", out["affected_accounts"])
        integrity_report(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
