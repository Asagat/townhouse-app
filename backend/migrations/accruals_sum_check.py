"""AccrualsSumCheck — сверка сумм начислений «файл-источник ↔ БД» (методика владельца).

Методика (6 срезов):
  1. месячные суммы начислений (по месяцу);
  2. месячные суммы по видам услуг  (месяц × услуга);
  3. месячные суммы по квартире     (месяц × квартира);
  4. итоговая сумма начислений       (по всем периодам);
  5. итоговая сумма по квартире;
  6. итоговая сумма по видам услуг.

Каждый срез: файл == БД (допуск 0.01 ₸ на агрегат). Источник истины периодов —
accrual_date строк accruals_register (в файле «Период_Начисление» — первое число месяца),
а «вид услуги» приводится к каноническим ключам (вниз от фактических строчек исходника,
включая слияние «Прочие расходы»→«Фонд развития» и варианты «охрана-электроэнергия»).

Файл читается напрямую с листов «Начисления-Фиксированные»/«Начисления-Переменные»
(нулевые строки не учитываются — в БД они не создаются; кв13/вывоз учитывается по факту
ненулевых сумм). Это работает и как самостоятельный скрипт-контроль при миграции в прод,
и как источник для pytest.

Запуск (из backend, файл-источник рядом templates/... или MIGRATION_SRC_XLSX):
    python migrations/accruals_sum_check.py --per-slice   # полная разбивка Δ
    python migrations/accruals_sum_check.py               # только итог расхождений
"""

import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    import openpyxl  # noqa: F401  
except Exception:  # pragma: no cover
    openpyxl = None

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Код «Виды задолженностей» источника -> код-услуги (в файле), см. *_accruals.
SRC_AN = {
    "1": "Электроэнергия", "2": "Охрана", "3": "Охрана - электроэнергия",
    "4": "Обслуживание ТП", "5": "Вывоз мусора", "6": "Фонд развития",
    "7": "Фонд развития",  # «Прочие расходы» сольются в «Фонд развития»
}


def _to_dec(x) -> Decimal | None:
    if x is None:
        return None
    try:
        return Decimal(str(x).replace(",", ".")).quantize(Decimal("0.01"))
    except Exception:
        return None


class AccrualsSumCheck:
    def __init__(self, db, src_path: Path | None = None):
        self.db = db
        self.fix_rows = None
        self.var_rows = None
        if src_path is None:
            src_path = os.getenv("MIGRATION_SRC_XLSX")
        if src_path:
            src_path = Path(src_path)
            if not src_path.exists():
                src_path = None
        if src_path is None:
            cand = _REPO_ROOT / "templates" / "Миграция данных FTH.xlsx"
            src_path = cand if cand.exists() else None
        self.src_path = Path(src_path) if src_path else None

    # ---------- исходник ----------
    def _iter_fix_rows(self):
        if not self.fix_rows:
            return
        for r in self.fix_rows:
            an = SRC_AN.get(str(r[3]).strip())
            if not an:
                continue
            amt = _to_dec(r[7])
            if not amt:
                continue
            yield int(r[1]), an, f"{r[4].year:04d}-{r[4].month:02d}", amt

    def _iter_var_rows(self):
        if not self.var_rows:
            return
        for r in self.var_rows:
            an = SRC_AN.get(str(r[4]).strip())
            if not an:
                continue
            amt = _to_dec(r[10])
            if not amt:
                continue
            yield int(r[1]), an, f"{r[5].year:04d}-{r[5].month:02d}", amt

    def load(self):
        if not self.src_path or openpyxl is None:
            self.fix_rows = self.var_rows = None
            return
        wb = openpyxl.load_workbook(self.src_path, read_only=True, data_only=True)
        ws_fix = wb["Начисления-Фиксированные"]
        self.fix_rows = list(ws_fix.iter_rows(values_only=True))[1:]
        ws_var = wb["Начисления-Переменные"]
        self.var_rows = list(ws_var.iter_rows(values_only=True))[1:]
        wb.close()

    # ---------- агрегация источника ----------
    def source_slices(self):
        by_m = defaultdict(Decimal)
        by_ms = defaultdict(Decimal)
        by_ma = defaultdict(Decimal)
        total = Decimal(0)
        tot_a = defaultdict(Decimal)
        tot_s = defaultdict(Decimal)
        for it in list(self._iter_fix_rows()) + list(self._iter_var_rows()):
            kv, an, ym, amt = it
            by_m[ym] += amt
            by_ms[(ym, an)] += amt
            by_ma[(ym, kv)] += amt
            total += amt
            tot_a[kv] += amt
            tot_s[an] += amt
        return {
            "by_month": dict(by_m), "by_month_service": dict(by_ms),
            "by_month_apt": dict(by_ma), "total": total,
            "total_by_apt": dict(tot_a), "total_by_svc": dict(tot_s),
        }

    # ---------- агрегация БД ----------
    def db_slices(self):
        def q(sql):
            return self.db.execute(text(sql)).fetchall()

        by_m = defaultdict(Decimal)
        by_ms = defaultdict(Decimal)
        by_ma = defaultdict(Decimal)
        total = Decimal(0)
        tot_a = defaultdict(Decimal)
        tot_s = defaultdict(Decimal)

        svc_name = {}
        for r in q("SELECT id, services_type FROM services_type"):
            svc_name[r[0]] = r[1]
        for r in q(
            "SELECT ap.apartment_number, a.account_id, a.services_type_id, "
            "       a.amount, to_char(a.accrual_date,'YYYY-MM') AS ym "
            "FROM accruals_register a "
            "JOIN accounts acc ON acc.id = a.account_id "
            "JOIN apartments ap ON ap.id = acc.apartment_id"
        ):
            kv = int(r[0]); svc = svc_name.get(r[2], "?") or "?"
            an = self._canon_bd_service(svc)
            amt = Decimal(str(r[3])).quantize(Decimal("0.01"))
            ym = r[4]
            by_m[ym] += amt
            by_ms[(ym, an)] += amt
            by_ma[(ym, kv)] += amt
            total += amt
            tot_a[kv] += amt
            tot_s[an] += amt
        return {
            "by_month": dict(by_m), "by_month_service": dict(by_ms),
            "by_month_apt": dict(by_ma), "total": total,
            "total_by_apt": dict(tot_a), "total_by_svc": dict(tot_s),
        }

    @staticmethod
    def _canon_bd_service(name: str) -> str:
        n = name.strip().replace(" ", " ").replace("  ", " ")
        variants = {"Охрана - электроэнергия": "Охрана - электроэнергия",
                    "Охрана-электроэнергия": "Охрана - электроэнергия",
                    "Электричество охраны": "Охрана - электроэнергия"}
        if n in variants:
            return variants[n]
        # нейтральные
        if n in {"Электроэнергия", "Охрана", "Обслуживание ТП", "Вывоз мусора",
                 "Фонд развития", "Прочие расходы"}:
            return n if n != "Прочие расходы" else "Фонд развития"
        return n

    # ---------- сравнение ----------
    @staticmethod
    def _diff(left, right, tol=Decimal("0.01")):
        keys = sorted(set(left) | set(right))
        diffs = []
        for k in keys:
            a = left.get(k, Decimal(0)); b = right.get(k, Decimal(0))
            if abs(a - b) >= tol:
                diffs.append((k, a, b))
        return diffs

    def diff_summary(self):
        left = self.source_slices()
        right = self.db_slices()
        out = {}
        out["month"] = self._diff(left["by_month"], right["by_month"])
        out["month_service"] = self._diff(left["by_month_service"], right["by_month_service"])
        out["month_apt"] = self._diff(left["by_month_apt"], right["by_month_apt"])
        out["total"] = [("TOTAL", left["total"], right["total"])] if abs(
            left["total"] - right["total"]) >= Decimal("0.01") else []
        out["total_apt"] = self._diff(left["total_by_apt"], right["total_by_apt"])
        out["total_svc"] = self._diff(left["total_by_svc"], right["total_by_svc"])
        return out


def main() -> None:
    from database import SessionLocal  # noqa: E402
    db = SessionLocal()
    try:
        c = AccrualsSumCheck(db)
        c.load()
        if c.src_path is None:
            print("Файл-источник не найден (задайте MIGRATION_SRC_XLSX).")
            return
        d = c.diff_summary()
        names = {
            "month": "Месячные суммы",
            "month_service": "Месяц × услуга",
            "month_apt": "Месяц × квартира",
            "total": "Итог (все периоды)",
            "total_apt": "Итог по квартире",
            "total_svc": "Итог по виду услуги",
        }
        for key, label in names.items():
            lst = d[key]
            if not lst:
                print(f"[OK]  {label}:  совпадение")
                continue
            print(f"[Δ]   {label}: {len(lst)} расхождений")
            for i, (k, a, b) in enumerate(lst[:25], 1):
                print(f"    {k}: файл {a:.2f} vs БД {b:.2f} (Δ={b - a:.2f})")
            if len(lst) > 25:
                print(f"    … ещё {len(lst) - 25}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
