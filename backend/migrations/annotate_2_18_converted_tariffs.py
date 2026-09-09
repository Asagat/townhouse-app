"""
Аннотирует тарифы, созданные конверсией 2.18 (comment содержит «Конверсия 2.18…»).

По просьбе владельца: к уже существующей сгенерированной строке
«Конверсия 2.18: месячная ставка <сумма> (<год-мес>)» добавляется короткая
поясняющая причина, где она достоверно известна из документов/исходника
(без выдумывания). Правит ТОЛЬКО поле tariffs.comment (затрагивает суммы
начислений / регистры, перепроводка не нужна; у tariffs нет аудит-полей —
история фиксируется самим comment + журналом миграции).

Причины взяты из:
  - расшифровок массовых разовых «домовых» сборов в скрипте импорта
    (HAZ: HOME_RAZOV в migrations/migrate_prepare_sources.py);
  - журнала чистки видов услуг / переноса «Прочие расходы» на «Фонд».
Идемпотентен: если причина уже присутствует в comment — не дублирует.

Запуск из каталога backend:
    python migrations/annotate_2_18_converted_tariffs.py            # dry-run
    python migrations/annotate_2_18_converted_tariffs.py --apply    # применить
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402

# id тарифа -> короткая достоверная причина (почему в этом месяце особый тариф).
# Периоды и суммы перепроверены по начислениям (17/16 л/с одного вида услуги).
KNOWN_REASON = {
    262: "разовый домовой сбор: замена э/э счётчиков",        # Фонд 48 216, март 2018
    263: "разовый домовой сбор: подключение холодной воды",   # Фонд 121 000, апр 2018
    264: "разовый домовой сбор: обслуживание дымоходов",      # Фонд 15 500, окт 2019
    268: "разовый досбор к базовому «Фонду» (2000): сбор «Прочие расходы/Проверка газа» 7560",  # Фонд 9 560, март 2024
    269: "разовый домовой сбор (30000)",                      # Фонд 30 000, ноя 2024
    272: "разовый домовой сбор",                              # Фонд 148 850, апр 2026
}


def _rows(db):
    """Текущее состояние аннотируемых тарифов (только известные)."""
    if not KNOWN_REASON:
        return []
    return db.execute(
        text(f"SELECT id, comment FROM tariffs WHERE id IN ({','.join(map(str, KNOWN_REASON))}) ORDER BY id")
    ).fetchall()


def plan(db):
    """Список (id, current_comment, will_append) без изменений БД."""
    out = []
    for r in _rows(db):
        rid = r[0]
        cur = r[1] or ""
        add = KNOWN_REASON[rid]
        if add in cur:
            out.append((rid, cur, None))  # уже есть — не трогаем
        else:
            out.append((rid, cur, add))
    return out


def apply(db):
    """Дописывает причину в comment (если ещё нет)."""
    changed = 0
    for rid, cur, add in plan(db):
        if add is None:
            continue
        new = f"{cur.rstrip()} — {add}".strip()
        db.execute(text("UPDATE tariffs SET comment = :c WHERE id = :id"), {"c": new, "id": rid})
        changed += 1
    db.commit()
    return changed


def main():
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        print("Тарифы конверсии 2.18 — аннотация причин:")
        for rid, cur, add in plan(db):
            status = f"-> добавить: {add}" if add else "(уже есть причина)"
            print(f"  #{rid}: {cur!r}\n      {status}")
        if not apply_mode:
            print("\ndry-run: для применения выполните скрипт с ключом --apply")
            return
        n = apply(db)
        print(f"\nОбновлено комментариев: {n}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
