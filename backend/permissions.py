"""
Разрешения доступа к ресурсам по ролям (задача 2.6: настраиваемая матрица).

Ролевая модель: admin / operator(Оператор-расчётный) / cashier(Кассир) /
controller(Контролер) / auditor(Аудитор) / resident(Житель).

Матрица прав хранится в таблице `role_permissions` (модель `RolePermission`) и
задаётся админом в UI («Пользователи и права» → вкладка «Права доступа»).
Backend — источник истины: `require_resource_access`/`require_permission` читают
эффективные права из БД на каждом запросе. Отсутствующая строка = дефолт из кода
(`default_permissions`), поэтому новые ресурсы не блокируются «случайно».

Две независимые оси по каждому (роль, ресурс):
  - **menu**  — виден ли раздел в меню (не то же, что «чтение»: справочники
                читаются формами/фильтрами — напр. кассир грузит «Статьи» для
                документа «Приход/Расход», хотя пункта меню у него нет);
  - **can_read / can_create / can_edit / can_delete** — права на generic CRUD
                (`/api/{resource}`), а для разделов-отчётов — только `can_read`.

Фиксированные правила (не редактируются матрицей):
  - `admin` — полный доступ; `resident` — только личный кабинет;
  - `LOCKED_ACTIONS` (создание/правка/удаление `tariff_types`, `accounts_register`,
    `cash_register`) запрещены на уровне ресурса всем ролям (записи в регистры и
    системный справочник создаются документом, а не вручную);
  - пункты `users` (только admin) и `cabinet` (только resident) в матрицу не входят.
"""

from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import RolePermission, User, UserRole

# Порядок ролей для UI.
ROLES = ["admin", "operator", "cashier", "controller", "auditor", "resident"]

# Роли, для которых матрица не действует (всегда дефолт).
FIXED_ROLES = {"admin", "resident"}

# Действия, запрещённые на уровне ресурса для ВСЕХ ролей (в т.ч. admin):
# записи в регистры и системный справочник создаются документами, не вручную.
LOCKED_ACTIONS: dict[str, set[str]] = {
    "tariff_types": {"create", "edit", "delete"},
    "accounts_register": {"create", "edit", "delete"},
    "cash_register": {"create", "edit", "delete"},
}

# --- КОНСТАНТЫ ДЕФОЛТНЫХ ПРАВИЛ (историческая ролевая модель) ---

# Ресурсы-«настройки» (запись только admin).
SETTINGS_RESOURCES = {
    "tariffs",
    "services_type",
    "tariff_types",
    "cash_points",
}

# Операционные регистры — только чтение для внутренних ролей (формируются документами).
REGISTER_RESOURCES = {
    "accounts_register",
    "accruals_register",
    "cash_register",
    "meter_readings",
}

# Что видит/использует controller (показания + справочники для выбора).
CONTROLLER_ALLOWED = {
    "meter_reading_documents",
    "meter_readings",
    "meters",
    "apartments",
    "apartment_residents",
    "accounts",
    "owners",
}

# Создание/правка по ролям (вариант A для кассира — только операционные документы/справочники).
CASHIER_CREATE = {"payments", "apartments", "apartment_residents", "accounts", "owners"}
CASHIER_EDIT = {"apartments", "apartment_residents", "accounts", "owners"}
CONTROLLER_CREATE = {"meter_reading_documents", "meters"}

# Удаление операционных данных доступно admin и operator.
OPERATION_WRITE_DELETE = {
    "payments",
    "transactions",
    "accrual_documents",
    "receipt_documents",
    "meter_reading_documents",
    "owners",
    "apartments",
    "apartment_residents",
    "accounts",
    "meters",
}

# Роли только на чтение (для кастомных write-эндпоинтов).
READONLY_ROLES = {UserRole.auditor, UserRole.resident}


# --- КАТАЛОГ РЕСУРСОВ И РАЗДЕЛОВ ---
# key — ключ ресурса (generic CRUD, `/api/{key}`) либо раздела меню без CRUD.
# kind: "resource" | "section". Для section значимо только «чтение» (для отчётов/
# дашборда — используется в проверке; для cabinet_admin — только видимость меню).

PERMISSION_CATALOG: list[dict[str, Any]] = [
    # Главная
    {"key": "dashboard", "label": "Главная", "group": "Главная", "kind": "section", "read_enforced": True},
    # Документы
    {"key": "payments", "label": "Приход/Расход", "group": "1. Документы", "kind": "resource"},
    {"key": "accrual_documents", "label": "Начисления", "group": "1. Документы", "kind": "resource"},
    {"key": "meter_reading_documents", "label": "Показания", "group": "1. Документы", "kind": "resource"},
    {"key": "receipt_documents", "label": "Квитанции", "group": "1. Документы", "kind": "resource"},
    # Справочники
    {"key": "tariffs", "label": "Тарифы", "group": "2. Справочники", "kind": "resource"},
    {"key": "cash_points", "label": "Кассы/Счета", "group": "2. Справочники", "kind": "resource"},
    {"key": "owners", "label": "Контрагенты", "group": "2. Справочники", "kind": "resource"},
    {"key": "apartments", "label": "Квартиры", "group": "2. Справочники", "kind": "resource"},
    {"key": "accounts", "label": "Лицевые счета", "group": "2. Справочники", "kind": "resource"},
    # Регистры
    {"key": "meter_readings", "label": "Регистр показаний", "group": "3. Регистры", "kind": "resource"},
    {"key": "accounts_register", "label": "Регистр взаиморасчётов", "group": "3. Регистры", "kind": "resource"},
    {"key": "accruals_register", "label": "Регистр начислений", "group": "3. Регистры", "kind": "resource"},
    {"key": "cash_register", "label": "Регистр денежных средств", "group": "3. Регистры", "kind": "resource"},
    # Настройки
    {"key": "tariff_types", "label": "Типы тарифов", "group": "4. Настройки", "kind": "resource"},
    {"key": "services_type", "label": "Виды услуг", "group": "4. Настройки", "kind": "resource"},
    {"key": "analytic_articles", "label": "Статьи доходов и расходов", "group": "4. Настройки", "kind": "resource"},
    {"key": "writeoff_documents", "label": "Списания", "group": "4. Настройки", "kind": "resource"},
    {"key": "meters", "label": "Счётчики", "group": "4. Настройки", "kind": "resource"},
    # Администрирование (только видимость раздела ЛК; эндпоинты ЛК вне матрицы)
    {"key": "prefixes", "label": "Префиксы", "group": "5. Администрирование", "kind": "section", "read_enforced": False},
    {"key": "cabinet_admin", "label": "Личный кабинет жителя", "group": "5. Администрирование", "kind": "section", "read_enforced": False},
    # Отчёты (разделы: проверяется только «чтение»)
    {"key": "cash_report", "label": "По кассе", "group": "Отчёты", "kind": "section", "read_enforced": True},
    {"key": "expense_report", "label": "По расходам", "group": "Отчёты", "kind": "section", "read_enforced": True},
    {"key": "debtors_report", "label": "По должникам", "group": "Отчёты", "kind": "section", "read_enforced": True},
    {"key": "statement_report", "label": "Выписка по счёту", "group": "Отчёты", "kind": "section", "read_enforced": True},
    # Служебные ресурсы (нет пункта меню; доступны как generic CRUD/дочерние)
    {"key": "transactions", "label": "Транзакции (алиас «Приход/Расход»)", "group": "Служебные", "kind": "resource"},
    {"key": "apartment_residents", "label": "Жильцы квартиры", "group": "Служебные", "kind": "resource"},
    {"key": "receipt_items", "label": "Строки квитанций", "group": "Служебные", "kind": "resource"},
    {"key": "writeoff_items", "label": "Строки списаний", "group": "Служебные", "kind": "resource"},
]

_CATALOG_BY_KEY = {e["key"]: e for e in PERMISSION_CATALOG}


# Дефолтная видимость раздела меню по ролям (исторический menuAccess.resourceRoles).
# auditor видит все разделы матрицы (кроме users/cabinet, которых в матрице нет).
MENU_DEFAULTS: dict[str, set[str]] = {
    "dashboard": {"admin", "operator", "cashier", "auditor"},
    "payments": {"admin", "operator", "cashier"},
    "accrual_documents": {"admin", "operator"},
    "meter_reading_documents": {"admin", "operator", "controller"},
    "receipt_documents": {"admin", "operator"},
    "writeoff_documents": {"admin", "operator"},
    "tariffs": {"admin", "operator"},
    "cash_points": {"admin", "operator"},
    "owners": {"admin", "operator", "cashier", "controller"},
    "apartments": {"admin", "operator", "cashier", "controller"},
    "accounts": {"admin", "operator", "cashier", "controller"},
    "meter_readings": {"admin", "operator", "controller"},
    "accounts_register": {"admin", "operator", "cashier"},
    "accruals_register": {"admin", "operator", "cashier"},
    "cash_register": {"admin", "operator", "cashier"},
    "tariff_types": {"admin", "operator"},
    "services_type": {"admin", "operator"},
    "analytic_articles": {"admin", "operator"},
    "meters": {"admin", "operator", "controller"},
    "prefixes": {"admin"},
    "cabinet_admin": {"admin", "auditor"},
    "cash_report": {"admin", "operator", "cashier", "auditor"},
    "expense_report": {"admin", "operator", "cashier", "auditor"},
    "debtors_report": {"admin", "operator", "cashier", "auditor"},
    "statement_report": {"admin", "operator", "cashier", "auditor"},
}


def _action_perm(role: str, key: str, action: str) -> bool:
    """Дефолтное право на действие по историческим правилам.

    action ∈ {"read", "create", "edit", "delete"}. Для разделов (section) права на
    запись всегда False.
    """
    entry = _CATALOG_BY_KEY.get(key)
    if entry is None:
        return False
    if action == "read" and entry["kind"] == "section":
        return role in MENU_DEFAULTS.get(key, set())
    if action in ("create", "edit", "delete") and entry["kind"] == "section":
        return False
    if action in ("create", "edit", "delete") and action in LOCKED_ACTIONS.get(key, set()):
        return False

    if action == "read":
        if role == "admin":
            return True
        if role == "auditor":
            return True
        if role == "controller":
            return key in CONTROLLER_ALLOWED
        if role in ("operator", "cashier"):
            return True
        return False  # resident

    if action == "create":
        if role == "admin":
            return True
        if role == "operator":
            return key not in SETTINGS_RESOURCES and key not in REGISTER_RESOURCES
        if role == "cashier":
            return key in CASHIER_CREATE and key not in REGISTER_RESOURCES
        if role == "controller":
            return key in CONTROLLER_CREATE
        return False

    if action == "edit":
        if role == "admin":
            return True
        if role == "operator":
            return key not in SETTINGS_RESOURCES and key not in REGISTER_RESOURCES
        if role == "cashier":
            return key in CASHIER_EDIT and key not in REGISTER_RESOURCES
        if role == "controller":
            return key in CONTROLLER_CREATE
        return False

    if action == "delete":
        if role == "admin":
            return True
        if role == "operator":
            return key in OPERATION_WRITE_DELETE
        return False

    return False


def _menu_perm(role: str, key: str) -> bool:
    """Дефолтная видимость раздела меню.

    Аудитор видит все разделы матрицы (`users`/`cabinet` в неё не входят — они по фолбэку).
    """
    if role == "auditor":
        return True
    return role in MENU_DEFAULTS.get(key, set())


def default_permissions() -> dict[str, dict[str, dict[str, bool]]]:
    """Дефолтная матрица: {роль: {ключ: {menu, read, create, edit, delete}}}."""
    result: dict[str, dict[str, dict[str, bool]]] = {}
    for role in ROLES:
        result[role] = {
            entry["key"]: {
                "menu": _menu_perm(role, entry["key"]),
                "read": _action_perm(role, entry["key"], "read"),
                "create": _action_perm(role, entry["key"], "create"),
                "edit": _action_perm(role, entry["key"], "edit"),
                "delete": _action_perm(role, entry["key"], "delete"),
            }
            for entry in PERMISSION_CATALOG
        }
    return result


def _clamp_locked(key: str, perms: dict[str, bool]) -> dict[str, bool]:
    """Снимает «разблокированные» в БД права на действия, если ресурс заперт."""
    locked = LOCKED_ACTIONS.get(key)
    if locked:
        for action in locked:
            perms[action] = False
    return perms


def effective_permissions(db: Session, role: str) -> dict[str, dict[str, bool]]:
    """Эффективные права роли: дефолты из кода, перекрытые строками `role_permissions`.

    Для фиксированных ролей (admin/resident) матрица не действует — возвращаются дефолты.
    """
    base = default_permissions().get(role)
    if base is None:
        return {}
    if role in FIXED_ROLES:
        return base
    rows = db.query(RolePermission).filter(RolePermission.role == role).all()
    for row in rows:
        if row.resource in base:
            base[row.resource] = _clamp_locked(
                row.resource,
                {
                    "menu": bool(row.menu),
                    "read": bool(row.can_read),
                    "create": bool(row.can_create),
                    "edit": bool(row.can_edit),
                    "delete": bool(row.can_delete),
                },
            )
    return base


def sanitize_permissions(key: str, perms: dict[str, bool]) -> dict[str, bool]:
    """Приводит набор прав к допустимому для ключа (перед записью в БД):
    у разделов (section) запись всегда False; для `LOCKED_ACTIONS` — действия снимаются."""
    entry = _CATALOG_BY_KEY.get(key)
    if entry is None:
        return perms
    if entry["kind"] == "section":
        perms["create"] = False
        perms["edit"] = False
        perms["delete"] = False
    return _clamp_locked(key, perms)


# --- ЗАВИСИМОСТИ ---

_ACTION_FOR_METHOD = {"POST": "create", "PATCH": "edit", "PUT": "edit", "DELETE": "delete"}
_ACTION_ERROR = {
    "read": "Недостаточно прав на просмотр",
    "create": "Недостаточно прав на создание",
    "edit": "Недостаточно прав на изменение",
    "delete": "Недостаточно прав на удаление",
}


def require_write_access(user: User = Depends(get_current_user)) -> User:
    """Зависимость для кастомных write-эндпоинтов (документы/квитанции и т.п.):
    запрещает изменение read-only-ролям (auditor/resident), остальные роли
    проходят как раньше (исторические проверки этих эндпоинтов сохранены)."""
    if user.role in READONLY_ROLES:
        raise HTTPException(
            status_code=403, detail="Роль только для просмотра — изменения запрещены"
        )
    return user


def require_resource_access(
    resource: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Зависимость для generic-эндпоинтов CRUD: права роли на (действие, ресурс) из матрицы."""
    method = (request.method or "GET").upper()
    if method in ("GET", "HEAD"):
        action = "read"
    else:
        action = _ACTION_FOR_METHOD.get(method, "edit")

    perms = effective_permissions(db, user.role.name)
    info = perms.get(resource)
    if info is None or not info.get(action):
        raise HTTPException(status_code=403, detail=_ACTION_ERROR[action])
    return user


def require_permission(key: str, action: str = "read"):
    """Фабрика зависимости для кастомных эндпоинтов-разделов (отчёты, дашборд):
    проверяет право `action` на ключ `key` из матрицы."""

    def dependency(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        perms = effective_permissions(db, user.role.name)
        info = perms.get(key)
        if info is None or not info.get(action):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return user

    return dependency
