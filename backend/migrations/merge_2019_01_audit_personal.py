"""Объединение перс-«аудит дымоходов» за январь-2019 в единый перс-документ.

Конвенция (вариант (а), владелец 09.09.2026): перс-корректировка одного вида на
несколько квартир ведётся ОДНИМ документом (как перс-сбор 2022-01: doc 134).

В истории 2019-01 «аудит дымоходов» лежит 8 отдельными oneoff-документами
(docs 22–29, по одной строке «Фонд» 2 000 у кв 4,7,9,11,12,13,14,17). Персональный
месячный «Начисление за январь» уже не содержал таких строк удально (см. реклас
2019-01). Приводим к единому виду:
  - создаём один oneoff-документ «Персональная корректировка за январь 2019
    (аудит дымоходов)» с комментарием-причиной;
  - переносим в него 8 accrual-строк (2 000 × 8 == 16 000) из docs 22–29;
  - удаляем опустевшие headers 22–29.

Суммарные начисления/долг не меняются (форма, не суммы): порядок docs у акку ,
записей accounts_register не трогаем (accrual_id строки сохраняется),
пересечёт балансов не требуется. Идемпотентен.

Запуск из backend:
    python migrations/merge_2019_01_audit_personal.py            # dry-run
    python migrations/merge_2019_01_audit_personal.py --apply
"""
import os
import sys
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal  # noqa: E402
from models import AccrualDocument  # noqa: E402
from services import audit_document_create, audit_document_update  # noqa: E402

SRC_DOCS = list(range(22, 30))          # 22..29
AUDIT = 1                                # 'migration' (admin)
MERGE_TITLE = "Персональная корректировка за январь 2019 (аудит дымоходов)"


def _existing(db: Session):
    return db.execute(
        text("SELECT id FROM accrual_documents WHERE doc_kind='oneoff' AND title=:t LIMIT 1"),
        {"t": MERGE_TITLE},
    ).first()


def plan_rows(db: Session):
    """Список (accrual_id, kv) ещё оставшихся строк в docs 22..29."""
    out = []
    r = db.execute(
        text("SELECT ar.id, ap.apartment_number FROM accruals_register ar "
             "JOIN accounts a ON a.id=ar.account_id "
             "JOIN apartments ap ON ap.id=a.apartment_id "
             "WHERE ar.accrual_document_id = ANY(:ids) ORDER BY ap.apartment_number"),
        {"ids": SRC_DOCS},
    ).fetchall()
    for row in r:
        out.append((row[0], row[1]))
    return out


def plan(db: Session):
    rows = plan_rows(db)
    src_headers = db.execute(
        text("SELECT count(*) FROM accrual_documents WHERE id=ANY(:ids)"), {"ids": SRC_DOCS}).scalar()
    return rows, src_headers


def apply(db: Session):
    rows, _ = plan(db)
    if not rows:
        return {"created": False, "moved": 0}
    target = _existing(db)
    if target is None:
        doc = AccrualDocument(
            accrual_date=date(2019, 1, 1),
            title=MERGE_TITLE,
            doc_kind="oneoff",
            comment="2 000 за аудит дымоходов (кв 4,7,9,11,12,13,14,17) — единый перс-документ "
                    "(объединение 8 разовых).",
        )
        audit_document_create(doc, AUDIT, "Объединение перс.-строк аудит дымоходов jan-2019 в один документ")
        db.add(doc)
        db.flush()
        target_id = doc.id
    else:
        target_id = target[0]

    acc_ids = [r[0] for r in rows]
    db.execute(text("UPDATE accruals_register SET accrual_document_id=:t WHERE id=ANY(:ids)"),
               {"t": target_id, "ids": acc_ids})
    # удалить пустые headers 22..29
    db.execute(text("DELETE FROM accrual_documents WHERE id=ANY(:ids) AND doc_kind='oneoff'"), {"ids": SRC_DOCS})
    db.commit()
    return {"created": target_id, "moved": len(acc_ids)}


def main():
    db = SessionLocal()
    try:
        rows, headers = plan(db)
        print(f"Осталось строк в docs 22..29: {len(rows)} (заголовков: {headers})")
        for accr, kv in rows:
            print(f"   accr={accr} кв={kv} amount=2000")
        if rows:
            print("\ndry-run: для применения --apply")
        else:
            print("уже объединено / нечего переносить")
        if "--apply" in sys.argv and rows:
            out = apply(db)
            print("\n== ПРИМЕНЕНО ==")
            print("   перс-документ id:", out["created"], "перенесено строк:", out["moved"])
    finally:
        db.close()


if __name__ == "__main__":
    main()
