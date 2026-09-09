"""Реклассификация 2020-02 и 2024-10: месячный Фонд на всех + отдельный перс-досбор.

Продолжение Шага 3 плана (правило «не-по-всем/индивидуально = перс»), тот же паттерн,
что для 2019-01 и 2022-01. По исходнику (templates/Миграция данных FTH.xlsx):

1) **2020-02** — месячный doc 43 (monthly) несёт «Фонд 10 000» у 15 кв, кроме кв2 и кв12;
   их строки свернуты в отдельные перс-документы oneoff: doc 44 (кв2, 76 500) и doc 45
   (кв12, 32 000). В файле строки кв2/кв12 имеют тариф 10 000 и комментарии-причину:
   «66 500 долг за парковку» (кв2) и «22 000 долг за парковку» (кв12), т.е. внутри перс-
   документа «зашиты» месячный Фонд 10 000 + отдельный долг-досбор.
   → к месячному doc 43 добавить Фонд 10 000 для кв2 и кв12; перс doc 44 понизить
     76 500 → **66 500**, doc 45 32 000 → **22 000** (парковка остаётся перс.).
   Нагрузка этих л/с не меняется (76 500 ⇄ 10 000 + 66 500; 32 000 ⇄ 10 000 + 22 000).

2) **2024-10** — месячный doc 106 (monthly) несёт «Фонд 2 000» у 16 кв, кроме кв5; строка
   кв5 свернута в перс-документ oneoff doc 107 (14 000). В файле кв5 имеет тариф 2 000,
   amount 14 000, комментарий «12 000 за ремонт воды».
   → к месячному doc 106 добавить Фонд 2 000 для кв5; перс doc 107 понизить
     14 000 → **12 000** (ремонт воды остаётся перс.).
   Нагрузка кв5 не меняется (14 000 ⇄ 2 000 + 12 000).

Суммарные начисления/долг дома и каждого л/с за месяц не меняются; accounts_register
затронутых счетов пересчитывается точечно.

Идемпотентен (dry-run/`--apply`):
    python migrations/reclassify_2020_02_2024_10_fond_personal.py            # dry-run
    python migrations/reclassify_2020_02_2024_10_fond_personal.py --apply
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

AUDIT_USER = 1  # 'migration' (admin)
CHANGE_DESC = "Реклассификация monthly/перс: месячный Фонд на всех л/с, перс-досбор вынесен (09.09.2026)"

# (doc месячного, месяц, тариф Фонда, месячная сумма, [добавляемые кв])
CASES_MONTHLY = [
    {"doc": 43, "date": date(2020, 2, 1), "tariff": 21, "amount": 10000.0,
     "add_kv": [2, 12]},
    {"doc": 106, "date": date(2024, 10, 1), "tariff": 24, "amount": 2000.0,
     "add_kv": [5]},
]

# (перс-документ, кв, было, станет)
CASES_PERSONAL = [
    {"doc": 44, "kv": 2, "was": 76500.0, "now": 66500.0},
    {"doc": 45, "kv": 12, "was": 32000.0, "now": 22000.0},
    {"doc": 107, "kv": 5, "was": 14000.0, "now": 12000.0},
]


def _svc(db, name):
    return db.execute(text("SELECT id FROM services_type WHERE services_type=:n"), {"n": name}).first()[0]



def kva(db):
    return {r[1]: r[0] for r in db.execute(text(
        "SELECT a.id, ap.apartment_number FROM accounts a JOIN apartments ap ON ap.id=a.apartment_id")).fetchall()}


def _row_for(db, doc_id, svc, kv_map, kv):
    """id accrual-строки в doc для kv (если есть)."""
    r = db.execute(
        text("SELECT ar.id FROM accruals_register ar WHERE ar.accrual_document_id=:d "
             "AND ar.account_id=:a AND ar.services_type_id=:s"),
        {"d": doc_id, "a": kv_map[kv], "s": svc},
    ).first()
    return r[0] if r else None

def plan(db):
    svc = _svc(db, "Фонд развития")
    kvmap = kva(db)
    add_monthly = []
    for c in CASES_MONTHLY:
        for kv in c["add_kv"]:
            if _row_for(db, c["doc"], svc, kvmap, kv) is None:
                add_monthly.append({"doc": c["doc"], "kv": kv, "amount": c["amount"], "tariff": c["tariff"]})
    lower_personal = []
    for c in CASES_PERSONAL:
        rows = db.execute(text(
            "SELECT ar.id, ar.amount FROM accruals_register ar "
            "WHERE ar.account_id=:a AND ar.services_type_id=:s AND ar.accrual_document_id=:d"),
            {"a": kvmap[c["kv"]], "s": svc, "d": c["doc"]}).fetchall()
        for r in rows:
            if float(r[1]) == c["was"]:
                lower_personal.append({"accr": r[0], "kv": c["kv"], "doc": c["doc"],
                                      "was": c["was"], "now": c["now"]})
    return {"add_monthly": add_monthly, "lower_personal": lower_personal, "svc": svc, "kvmap": kvmap}

def _month_label(doc_id):
    if doc_id == 106:
        return "октябрь-2024"
    return "февраль-2020"

def apply(db):
    pl = plan(db)
    svc, kvmap = pl["svc"], pl["kvmap"]
    affected = set()
    added_rows = []
    for c in CASES_MONTHLY:
        for kv in c["add_kv"]:
            if _row_for(db, c["doc"], svc, kvmap, kv) is not None:
                continue
            item = AccrualsRegister(
                accrual_document_id=c["doc"],
                accrual_date=c["date"],
                account_id=kvmap[kv],
                tariff_id=c["tariff"],
                services_type_id=svc,
                current_reading_id=None, past_reading_value=None,
                current_reading_value=None, consumption=0,
                amount=c["amount"],
            )
            db.add(item)
            db.flush()
            db.execute(
                text("INSERT INTO accounts_register (operation_date, account_id, accrual_id, "
                     "services_type_id, income, expense, balance_after) "
                     "VALUES (:op,:a,:accr,:svc,:inc,0,0)"),
                {"op": c["date"], "a": kvmap[kv], "accr": item.id, "svc": svc, "inc": c["amount"]},
            )
            added_rows.append({"doc": c["doc"], "kv": kv, "accr": item.id})
            affected.add(kvmap[kv])
            d = db.query(AccrualDocument).get(c["doc"])
            if d is not None:
                base = (d.comment or "").strip()
                note = f"Месячный Фонд {c['amount']:,.0f} добавлен для кв {kv} («{_month_label(c['doc'])}» — был свернут в перс)."
                d.comment = (base + " | " + note).strip(" |") if base else note
                audit_document_update(d, AUDIT_USER, CHANGE_DESC)

    lowered = []
    for c in CASES_PERSONAL:
        rows = db.execute(text(
            "SELECT ar.id, ar.amount FROM accruals_register ar "
            "WHERE ar.account_id=:a AND ar.services_type_id=:s AND ar.accrual_document_id=:d"),
            {"a": kvmap[c["kv"]], "s": svc, "d": c["doc"]}).fetchall()
        for r in rows:
            if float(r[1]) == c["was"]:
                db.execute(text("UPDATE accruals_register SET amount=:n WHERE id=:i"), {"n": c["now"], "i": r[0]})
                db.execute(text("UPDATE accounts_register SET income=:n WHERE accrual_id=:i"), {"n": c["now"], "i": r[0]})
                lowered.append({"accr": r[0], "kv": c["kv"], "doc": c["doc"]})
                affected.add(kvmap[c["kv"]])
                d = db.query(AccrualDocument).get(c["doc"])
                if d is not None:
                    base = (d.comment or "").strip()
                    note = f"Перс-досбор понижен до {c['now']:,.0f} (месячный Фонд вынесен в месячный документ)."
                    d.comment = (base + " | " + note).strip(" |") if base else note
                    audit_document_update(d, AUDIT_USER, CHANGE_DESC)

    db.commit()
    for acct in sorted(affected):
        recalculate_account_balance(db, acct)
    db.commit()
    return {"added_rows": added_rows, "lowered": lowered, "affected": sorted(a for a in affected)}


def main():
    db = SessionLocal()
    try:
        pl = plan(db)
        print(f"Услуга «Фонд развития» id={pl['svc']}")
        print("== добавить в месячные ==")
        for r in pl["add_monthly"]:
            print(f"   doc={r['doc']} кв={r['kv']} amount={r['amount']:,.0f} tariff=#{r['tariff']}")
        print("== понизить перс ==")
        for r in pl["lower_personal"]:
            print(f"   doc={r['doc']} кв={r['kv']} accr={r['accr']} {r['was']:,.0f} -> {r['now']:,.0f}")
        if pl["add_monthly"] or pl["lower_personal"]:
            print("\ndry-run: для применения используйте --apply")
        if "--apply" in sys.argv:
            out = apply(db)
            print("\n== ПРИМЕНЕНО ==")
            print("   месячных добавлено:", out["added_rows"])
            print("   перс понижено:", out["lowered"])
            print("   пересчитаны счета:", out["affected"])
    finally:
        db.close()


if __name__ == "__main__":
    main()
