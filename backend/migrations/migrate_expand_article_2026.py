"""migrate_expand_article_2026.py — разнесение «Расходы по дому» на новые статьи.

Правила (эталон — backend/migrations/rules_articles_2026.md, подтверждены владельцем,
сент. 2026). Применяются к операциям «Приход/Расход» (`transactions`), у которых сейчас
`article_id = «Расходы по дому»`, по комментарию `notes` (нижний регистр, «первое
совпадение»). Остаток («первое совпадение» не найдено) относится к «Прочие расходы».

После переноса:
  - проверяется отсутствие ссылок на статью «Расходы по дому»;
  - устаревшая статья удаляется.

Примечание: в БД «Статья» НЕ хранится в cash_register/accounts_register — там движение
ссылается на transactions.article_id, поэтому после обновления документа значения
«Статьи» в регистрах и отчётах получаются корректными автоматически.

Остаток мог бы расходиться иначе, если случай удалены записи; контрольные суммы печатаются.

Запуск из каталога backend: python migrations/migrate_expand_article_2026.py
"""

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal  # noqa: E402
from models import AnalyticArticle, AnalyticKind  # noqa: E402
from sqlalchemy import text  # noqa: E402


# Порядок «первого совпадения» важен (идентичен финальному черновому прогону).
RULES: list[tuple[str, list[str]]] = [
    ("Электроэнергия", ["эл.энерг", "эл. энерги", "электроэнерг", "электричеств", "за свет", "освещ"]),
    ("Обслуживание инженерных систем", [
        "подключен холодн", "холодной воды", "кабел", "трансформатор", "тп",
        "канализац", "дымоход", "счетчик", "счётчик", "электрику", "электр.",
        "фонар", "аварийн", "повреждений", "модели для", "трубы",
    ]),
    ("Водоснабжение", ["вод", "поливн"]),
    ("Заработная плата персонала", [
        "охране", "охрану", "зп", "зарплат", "заработ", "окончательный расчет",
        "оразу за работу", "выдач", "ремонт охраны", "ремонт дома охраны",
        "за обогревател для ох", "эл.плита для охран",
    ]),
    ("Благоустройство территории", [
        "асфальт", "арык", "арычн", "лотк", "грунт", "чернозем", "детск",
        "дет.площадк", "воркаут", "баскетб", "стойку", "кольцо", "сетка",
        "парковк", "покрыт", "песочниц", "песок", "озелен", "удобрен", "клён",
        "клен", "газон", "решетк", "шлагбаум", "снегоубороч", "салют", "качел",
        "гирлянд", "украшен", "бесед", "желез", "кровл", "навес", "выключател",
        "3д панел", "доставк", "мягк",
    ]),
    ("Вывоз мусора и утилизация", ["мусор", "утил", "вывоз грунт"]),
    ("Безопасность и проверки", [
        "видеонаблюден", "камеры", "чс", "пожар", "безопасн", "сигнализ",
        "топосъем", "экспертное",
    ]),
    ("Материалы и инвентарь", [
        "бачк", "соль", "материал", "бетон", "арматур", "инвентар", "лопат",
        "тачк", "перчатк", "оборуд", "запчаст", "шкаф", "краск", "хлорк",
        "ножниц", "заклеп", "кран", "шланг", "лент", "метл", "совок",
        "пистолет", "смесител", "сигнальная", "на материлы", "хозтовар",
    ]),
    ("Возвраты жителям", ["возврат", "вернул", "перерасчет", "взаиморасчёт", "расходам на квартиру"]),
]

FALLBACK = "Прочие расходы"


def classify(note: str | None) -> str:
    ln = (note or "").lower()
    for name, keys in RULES:
        for k in keys:
            if k in ln:
                return name
    return FALLBACK


def main() -> int:
    db = SessionLocal()
    try:
        old = db.query(AnalyticArticle).filter(
            AnalyticArticle.name == "Расходы по дому", AnalyticArticle.kind == AnalyticKind.expense
        ).first()
        if old is None:
            print("Статья 'Расходы по дому' не найдена — уже обработано?")
            return 0
        old_id = old.id

        # целевые id по именам (kind=expense)
        target: dict[str, int] = {}
        for a in db.query(AnalyticArticle).filter(AnalyticArticle.kind == AnalyticKind.expense).all():
            if a.name != "Расходы по дому":
                target[a.name] = a.id
        missing = [n for n in dict(RULES) if n not in target]
        if FALLBACK not in target or missing:
            print("Нет целевых статей расходов в справочнике:", missing)
            return 2

        rows = db.execute(
            text("SELECT id, notes FROM transactions WHERE article_id = :o ORDER BY id"),
            {"o": old_id},
        ).fetchall()
        counts: Counter[str] = Counter()
        sums: Counter[str] = Counter()
        total = 0.0
        for tx_id, notes in rows:
            name = classify(notes)
            sid = target[name]
            db.execute(text("UPDATE transactions SET article_id = :s WHERE id = :i"), {"s": sid, "i": tx_id})
            counts[name] += 1
            sums[name] += 0.0
            total += 1.0

        # Проверка: больше нет ссылок на старую статью нигде.
        refs = db.execute(text("SELECT count(*) FROM transactions WHERE article_id = :o"), {"o": old_id}).scalar()
        if refs:
            print(f"Осталось ссылок на 'Расходы по дому': {refs} — прерываю.")
            db.rollback()
            return 3

        db.execute(text("DELETE FROM analytic_articles WHERE id = :o"), {"o": old_id})
        db.commit()

        print(f"Перенесено операций: {len(rows)} (total={total:,.0f}). НОВОЕ распределение по записям:")
        for name, c in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {c:4d}  {name}")

        still = db.query(AnalyticArticle).count()
        print(f"Справочник статей после удаления 'Расходы по дому': всего {still} строк.")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print("Ошибка:", exc)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
