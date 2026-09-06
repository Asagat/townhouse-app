# backend/filtering.py
"""Общий механизм серверной фильтрации списков (роадмап Б10).

GET /api/<resource>?<field>[_{like|ne|gte|lte}]=<value>

Формат параметров повторяет сериализацию @refinedev/simple-rest:
  - `full_name_like=Иван`  → contains (ILIKE по тексту; для нестроковых полей — по CAST AS text);
  - `transaction_type=Доход` → равно (eq, значение без суффикса);
  - `amount_gte=1000` / `amount_lte=5000` / `amount_ne=0` → диапазоны/не равно;
  - `is_active=true` → равно для boolean.

Разрешение полей — то же, что для сортировки (sorting.SORT_FIELDS): прямые столбцы
моделей, вложенные поля через relationship (account.account_number и т.п.), агрегаты
(readings_count >= N) и автор (created_by_name). Неразрешимые/неприменимые параметры
молча пропускаются (запрос не падает), пустые значения игнорируются.
"""

from decimal import Decimal, InvalidOperation
from datetime import date, datetime, time

from sqlalchemy import String, cast
from sqlalchemy import types as satypes
from sqlalchemy import Enum as SAEnum

from sorting import SORT_FIELDS, _build_descriptor

# Ресурсы-алиасы одной и той же таблицы (как в sorting/app: payments = transactions).
_ALIAS_RESOURCES = {"payments": "transactions"}

_OPERATOR_SUFFIXES = (("_like", "like"), ("_ne", "ne"), ("_gte", "gte"), ("_lte", "lte"))


# --- Определение «вида» значения поля по типу столбца ---

def _kind_of_column(column) -> str | None:
    """Классификация типа столбца: str/int/num/date/datetime/bool."""
    t = column.type
    if isinstance(t, satypes.Boolean):
        return "bool"
    if isinstance(t, (satypes.SmallInteger, satypes.Integer, satypes.BigInteger)):
        return "int"
    if isinstance(t, (satypes.Numeric, satypes.Float)):
        return "num"
    if isinstance(t, satypes.DateTime):
        return "datetime"
    if isinstance(t, satypes.Date):
        return "date"
    return "str"


def _direct_column(model, field):
    """Прямой столбец модели (через mapper, без инстанцирования)."""
    mapper = model.__mapper__
    attr = mapper.column_attrs.get(field) if hasattr(mapper, "column_attrs") else None
    if attr is not None and getattr(attr, "columns", None):
        return attr.columns[0]
    return None


def _path_leaf_type(base_model, path, column):
    """Тип «листового» столбца для пути по relationship (для SORT_FIELDS path-дескрипторов)."""
    mapper = base_model.__mapper__
    for rel_name in path:
        rel = mapper.relationships.get(rel_name)
        if rel is None:
            return None
        mapper = rel.mapper
    leaf = mapper.class_.__table__
    if column not in leaf.c:
        return None
    return leaf.c[column].type


def _descriptor_kind(base_model, descriptor: dict) -> str:
    """Вид значения для дескриптора из sorting.SORT_FIELDS."""
    if "creator_name" in descriptor:
        return "str"
    if "aggregate" in descriptor:
        return "int" if descriptor["aggregate"] == "count" else "num"
    if "coalesce" in descriptor:
        # В SORT_FIELDS coalesce используется только для текстовых названий документов.
        return "str"
    if "path" in descriptor:
        t = _path_leaf_type(base_model, descriptor["path"], descriptor["col"])
        return _kind_of_column(t) if t is not None else "str"
    return "str"


def _resolve_field(resource: str, model, field: str):
    """Возвращает {"expr": …, "kind": …, "col": …} либо None."""
    descriptor = SORT_FIELDS.get((resource, field))
    if descriptor is not None:
        expr = _build_descriptor(model, descriptor)
        if expr is None:
            return None
        return {"expr": expr, "kind": _descriptor_kind(model, descriptor), "col": None}
    col = _direct_column(model, field)
    if col is not None:
        return {"expr": col, "kind": _kind_of_column(col) or "str", "col": col}
    return None


# --- Нормализация значений и построение условий ---

def _to_bool(value: str):
    v = value.strip().lower()
    if v in ("true", "1", "да", "yes"):
        return True
    if v in ("false", "0", "нет", "no"):
        return False
    return None


def _to_number(value: str):
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def _to_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _escape_like(value: str) -> str:
    return (value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_"))


def _make_condition(expr, kind: str, op: str, value: str, col=None):
    """Строит SQL-условие по (выражение, вид, оператор, значение). None — не применимо."""
    if kind == "bool":
        b = _to_bool(value)
        if b is None:
            return None
        if op in ("eq", "ne"):
            return expr.is_(b) if op == "eq" else expr.is_not(b)
        return None

    if kind in ("int", "num"):
        num = _to_number(value)
        if num is None:
            return None
        if op == "eq":
            return expr == num
        if op == "ne":
            return expr != num
        if op == "gte":
            return expr >= num
        if op == "lte":
            return expr <= num
        return None

    if kind == "date":
        d = _to_date(value)
        if d is None:
            return None
        if op == "eq":
            return expr == d
        if op == "ne":
            return expr != d
        if op == "gte":
            return expr >= d
        if op == "lte":
            return expr <= d
        return None

    if kind == "datetime":
        # date-строка (обычный случай из UI): gte — начало суток, lte — конец суток
        # (чтобы фильтр «по день» включал все время внутри дня).
        d = _to_date(value)
        if d is not None:
            base = datetime.combine(d, time.max if op == "lte" else time.min)
        else:
            try:
                base = datetime.fromisoformat(value.replace("T", " "))
            except ValueError:
                return None
        if op == "eq":
            return expr == base
        if op == "ne":
            return expr != base
        if op == "gte":
            return expr >= base
        if op == "lte":
            return expr <= base
        return None

    # Строки и прочие типы. Для нативных PG-enum (например, transactions.transaction_type
    # хранит ИМЯ члена in_cash/out_cash, а не русское значение) приводим значение к члену
    # enum — иначе сравнение enum-колонки с произвольной строкой некорректно/ошибочно.
    v = value.strip()
    if col is not None and isinstance(col.type, SAEnum) and getattr(col.type, "enum_class", None):
        enum_cls = col.type.enum_class
        member = None
        try:
            member = enum_cls[v]  # по имени члена (так хранится в БД)
        except KeyError:
            try:
                member = enum_cls(v)  # запасной вариант: по значению
            except ValueError:
                member = None
        if member is not None:
            if op == "eq":
                return expr == member
            if op == "ne":
                return expr != member
    if op == "like":
        return cast(expr, String).ilike(f"%{_escape_like(v)}%", escape="\\")
    if op == "eq":
        return expr == v
    if op == "ne":
        return expr != v
    return None


def build_filter_clauses(resource: str, model, params) -> list:
    """Собирает список SQL-условий из query-параметров запроса.

    params — итерируемый набор (ключ, значение) (request.query_params.multi_items()).
    Служебные параметры (начинающиеся с '_' — пагинация/сортировка) пропускаются.
    """
    resource = _ALIAS_RESOURCES.get(resource, resource)
    clauses = []
    for raw_key, raw_value in params:
        key = str(raw_key)
        value = str(raw_value)
        if not value or key.startswith("_"):
            continue

        field, op = key, "eq"
        for suffix, operator in _OPERATOR_SUFFIXES:
            if key.endswith(suffix):
                field = key[: -len(suffix)]
                op = operator
                break

        info = _resolve_field(resource, model, field)
        if info is None:
            continue
        cond = _make_condition(info["expr"], info["kind"], op, value, col=info.get("col"))
        if cond is not None:
            clauses.append(cond)
    return clauses
