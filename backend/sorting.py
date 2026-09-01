# backend/sorting.py
"""Общее решение серверной сортировки по вложенным/вычисляемым полям (роадмап 1.5).

Вместо рукописного SQL на каждую пару (ресурс, поле) здесь декларативно описывается
ТОЛЬКО путь к нужному полю (список relationship-связей), а коррелированный скалярный
подзапрос строится автоматически через SQLAlchemy expression language.

Почему не raw-SQL-`text()`: при наличии eager-load (joinedload одно-ко-многим,
напр. `ReceiptDocument.items`) и pagination (limit/offset) SQLAlchemy оборачивает
запрос в подзапрос (`anon_1`), и `text()`-выражение со ссылкой на «сырую» таблицу
перестаёт коррелировать и падает с `missing FROM-clause`. Скалярные подзапросы
SQLAlchemy коррелируют к алиасу из внешнего запроса корректно.

Виды описаний в `SORT_FIELDS`:
  - {"path": [rel1, rel2, ...], "col": "..."}   — путь по многие-к-одному к столбцу;
  - {"creator_name": True}                        — автор: COALESCE(full_name, username, '');
  - {"aggregate": "count"|"sum", "rel": "...", "col": "..."} — агрегат по дочерним записям.

`build_order_clause(resource, model, sort_key)` возвращает SQLAlchemy-выражение/столбец
для ORDER BY, либо None (поле не сортируется — оставляем текущий порядок).
"""

from sqlalchemy import literal, select, func

from models import User


# --- ДЕКЛАРАТИВНОЕ ОПИСАНИЕ СОРТИРУЕМЫХ ПОЛЕЙ ---
# Ключ — (нормализованный ресурс, ключ сортировки из фронта). Прямые столбцы моделей
# (id, amount и т.п.) здесь НЕ нужны — сортируются через hasattr.

SORT_FIELDS: dict[tuple[str, str], dict] = {
    # --- Приход/Расход (таблица transactions; ресурсы payments и transactions) ---
    ("transactions", "article.name"): {"path": ["article"], "col": "name"},
    ("transactions", "cash_point.name"): {"path": ["cash_point"], "col": "name"},
    ("transactions", "account.account_number"): {"path": ["account"], "col": "account_number"},
    ("transactions", "owner.full_name"): {"path": ["account", "apartment", "owner"], "col": "full_name"},
    ("transactions", "apartment.apartment_number"): {"path": ["account", "apartment"], "col": "apartment_number"},
    ("transactions", "created_by_name"): {"creator_name": True},
    ("transactions", "article_name"): {"path": ["article"], "col": "name"},

    # --- Квартиры ---
    ("apartments", "owner.full_name"): {"path": ["owner"], "col": "full_name"},
    ("apartments", "owner.phone"): {"path": ["owner"], "col": "phone"},

    # --- Лицевые счета ---
    ("accounts", "apartment.owner.full_name"): {"path": ["apartment", "owner"], "col": "full_name"},
    ("accounts", "apartment.apartment_number"): {"path": ["apartment"], "col": "apartment_number"},

    # --- Регистр начислений ---
    ("accruals_register", "account.account_number"): {"path": ["account"], "col": "account_number"},
    ("accruals_register", "services_type.services_type"): {"path": ["services_type"], "col": "services_type"},
    ("accruals_register", "apartment.apartment_number"): {"path": ["account", "apartment"], "col": "apartment_number"},
    ("accruals_register", "document_title"): {"path": ["accrual_document"], "col": "title"},

    # --- Регистр взаиморасчётов ---
    ("accounts_register", "account.account_number"): {"path": ["account"], "col": "account_number"},
    ("accounts_register", "services_type.services_type"): {"path": ["services_type"], "col": "services_type"},
    ("accounts_register", "apartment.apartment_number"): {"path": ["account", "apartment"], "col": "apartment_number"},
    # document_title во взаиморасчётах берётся из документа начислений ИЛИ прихода/расхода.
    ("accounts_register", "document_title"): {
        "coalesce": [
            {"path": ["accrual", "accrual_document"], "col": "title"},
            {"path": ["transaction"], "col": "title"},
        ]
    },

    # --- Регистр денежных средств ---
    ("cash_register", "account.account_number"): {"path": ["account"], "col": "account_number"},
    ("cash_register", "apartment.apartment_number"): {"path": ["account", "apartment"], "col": "apartment_number"},

    # --- Показания (регистр) ---
    ("meter_readings", "services_type.services_type"): {"path": ["services_type"], "col": "services_type"},
    ("meter_readings", "meter.serial_number"): {"path": ["meter"], "col": "serial_number"},
    ("meter_readings", "document.title"): {"path": ["document"], "col": "title"},
    ("meter_readings", "apartment.apartment_number"): {"path": ["apartment"], "col": "apartment_number"},

    # --- Показания (документы) ---
    ("meter_reading_documents", "services_type.services_type"): {"path": ["services_type"], "col": "services_type"},
    ("meter_reading_documents", "readings_count"): {"aggregate": "count", "rel": "readings"},
    ("meter_reading_documents", "created_by_name"): {"creator_name": True},

    # --- Начисления (документы) ---
    ("accrual_documents", "accruals_count"): {"aggregate": "count", "rel": "accruals"},
    ("accrual_documents", "total_amount"): {"aggregate": "sum", "rel": "accruals", "col": "amount"},
    ("accrual_documents", "created_by_name"): {"creator_name": True},

    # --- Квитанции ---
    ("receipt_documents", "created_by_name"): {"creator_name": True},

    # --- Списания ---
    ("writeoff_documents", "created_by_name"): {"creator_name": True},
    ("writeoff_documents", "items_count"): {"aggregate": "count", "rel": "items"},
    ("writeoff_documents", "total_allocated"): {"aggregate": "sum", "rel": "items", "col": "allocated"},

    # --- Тарифы ---
    ("tariffs", "services_type.services_type"): {"path": ["services_type"], "col": "services_type"},
    ("tariffs", "tariff_type.name"): {"path": ["tariff_type"], "col": "name"},

    # --- Счётчики ---
    ("meters", "apartment.apartment_number"): {"path": ["apartment"], "col": "apartment_number"},
    ("meters", "services_type.services_type"): {"path": ["services_type"], "col": "services_type"},
}


def _build_path_expression(base_model, path: list[str], column: str):
    """Скалярный подзапрос для пути по многие-к-одному relationship к столбцу.

    Например для `transactions` + `['account', 'apartment', 'owner']` + `'full_name'`:
        (SELECT owners.full_name FROM owners
         WHERE owners.id = (SELECT apartments.owner_id FROM apartments
                            WHERE apartments.id = (SELECT accounts.apartment_id FROM accounts
                                                   WHERE accounts.id = transactions.account_id)))
    Возвращает None, если путь или колонка не разрешаются.
    """
    mapper = base_model.__mapper__
    t0 = base_model.__table__
    hops = []  # hops[i] соединяет t_i -> t_(i+1)
    for rel_name in path:
        rel = mapper.relationships.get(rel_name)
        if rel is None:
            return None
        local = list(rel.local_columns)
        pk = list(rel.mapper.primary_key)
        if len(local) != 1 or len(pk) != 1:
            return None
        hops.append({
            "fk": local[0].name,            # FK-колонка на стороне t_i
            "to_table": rel.mapper.class_.__table__,
            "to_pk": pk[0].name,            # PK на стороне t_(i+1)
        })
        mapper = rel.mapper

    if not hops:
        return None
    leaf_tbl = mapper.class_.__table__
    if column not in leaf_tbl.c:
        return None

    n = len(hops)
    # Внутренний скаляр — ссылка на FK базовой таблицы (коррелирует к алиасу).
    inner = t0.c[hops[0]["fk"]]
    # Промежуточные уровни: (SELECT t_i.fk_next FROM t_i WHERE t_i.pk = <inner>)
    for i in range(1, n):
        ti = hops[i - 1]["to_table"]
        inner = (
            select(ti.c[hops[i]["fk"]])
            .where(ti.c[hops[i - 1]["to_pk"]] == inner)
            .scalar_subquery()
            .correlate(t0)  # убрать базовую таблицу из FROM подзапроса (корреляция к внеш. запросу)
        )
    inner = (
        select(leaf_tbl.c[column])
        .where(leaf_tbl.c[hops[n - 1]["to_pk"]] == inner)
        .scalar_subquery()
        .correlate(t0)
    )
    return inner


def _build_creator_name(base_model) -> "object | None":
    """Автор документа: COALESCE(full_name, username, '') через created_by -> users."""
    rel = base_model.__mapper__.relationships.get("creator")
    if rel is None:
        return None
    local = list(rel.local_columns)
    if len(local) != 1:
        return None
    return (
        select(func.coalesce(User.full_name, User.username, literal("")))
        .where(User.id == base_model.__table__.c[local[0].name])
        .scalar_subquery()
        .correlate(base_model.__table__)
    )


def _build_aggregate(base_model, rel_name: str, func_name: str, column: str | None = None):
    """Агрегат по дочерним записям связи один-ко-многим (COUNT или SUM/COALESCE)."""
    rel = base_model.__mapper__.relationships.get(rel_name)
    if rel is None:
        return None
    parent_tab = base_model.__tablename__
    child = rel.mapper.class_.__table__
    parent_pk = list(rel.local_columns)
    if len(parent_pk) != 1:
        return None
    # FK-колонка на стороне дочерней таблицы, ссылающаяся на родителя.
    child_fk = [f.parent.name for f in child.foreign_keys if f.column.table.name == parent_tab]
    if len(child_fk) != 1:
        return None
    cond = child.c[child_fk[0]] == base_model.__table__.c[parent_pk[0].name]
    base_tab = base_model.__table__
    if func_name == "count":
        return select(func.count()).where(cond).scalar_subquery().correlate(base_tab)
    if func_name == "sum" and column is not None and column in child.c:
        return (
            select(func.coalesce(func.sum(child.c[column]), literal(0)))
            .where(cond)
            .scalar_subquery()
            .correlate(base_tab)
        )
    return None


def _build_descriptor(base_model, descriptor: dict):
    if "path" in descriptor:
        return _build_path_expression(base_model, descriptor["path"], descriptor["col"])
    if "creator_name" in descriptor:
        return _build_creator_name(base_model)
    if "aggregate" in descriptor:
        return _build_aggregate(
            base_model, descriptor["rel"], descriptor["aggregate"], descriptor.get("col")
        )
    if "coalesce" in descriptor:
        parts = [_build_descriptor(base_model, p) for p in descriptor["coalesce"]]
        if not all(p is not None for p in parts):
            return None
        return func.coalesce(*parts)  # type: ignore[arg-type]
    return None


def build_order_clause(resource: str, model, sort_key: str):
    """Возвращает SQLAlchemy-выражение/столбец для ORDER BY по sort_key.

    Порядок: дескриптор (вложенные/вычисляемые поля) → прямой атрибут модели.
    None — сортировка недоступна (оставим текущий порядок).
    """
    descriptor = SORT_FIELDS.get((resource, sort_key))
    if descriptor is not None:
        expr = _build_descriptor(model, descriptor)
        if expr is not None:
            return expr
    if hasattr(model, sort_key):
        return getattr(model, sort_key)
    return None
