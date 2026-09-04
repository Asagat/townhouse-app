"""
Разрешения доступа к ресурсам по ролям.

Ролевая модель (см. models.UserRole и ROADMAP):
admin / operator(Оператор-расчётный) / cashier(Кассир) / controller(Контролер) / resident(Житель).

Принцип:
  - operator >= cashier (иерархия уровней), плюс operator умеет запускать начисления/списание;
  - «Настройки» (тарифы, виды услуг, кассы, типы тарифов) — запись только admin, остальным чтение;
  - удаление — только admin (и operator для операционных справочников/документов).
  - controller видит только показания и минимально квартиры/счета для выбора.
  - resident — отдельно (только свой счёт; на этом этапе списками не пользуется).
"""

from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth import ROLE_LEVEL, get_current_user
from database import get_db
from models import User, UserRole

# Ресурсы, которые являются «настройками» (запись только admin).
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

# Что видит/использует controller (только показания): читает документы показаний,
# регистр показаний, счетчики и справочники для выбора (квартиры/счета/контрагенты).
CONTROLLER_ALLOWED = {
    "meter_reading_documents",
    "meter_readings",
    "meters",
    "apartments",
    "accounts",
    "owners",
}


def _role_level(user: User) -> int:
    return ROLE_LEVEL.get(user.role, -1)


def _read_allowed(user: User, resource: str) -> bool:
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.auditor:
        # Аудитор видит весь учёт (включая настройки/регистры) — только чтение.
        return True
    if user.role == UserRole.controller:
        return resource in CONTROLLER_ALLOWED
    if user.role in (UserRole.operator, UserRole.cashier):
        # Внутренние роли читают весь учёт (в т.ч. настройки — в режиме чтения).
        return True
    return False  # resident


def _create_update_allowed(user: User, resource: str) -> bool:
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.operator:
        # Оператор меняет весь учёт, кроме настроек (settings read-only).
        return resource not in SETTINGS_RESOURCES
    if user.role == UserRole.cashier:
        # Кассир — операционные документы/справочники, без настроек и регистров.
        return resource not in SETTINGS_RESOURCES and resource not in REGISTER_RESOURCES
    if user.role == UserRole.controller:
        # Контролер вносит показания (создаёт/правит документ показаний) и правит счетчики;
        # квартиры/счета/контрагенты — только чтение (для выбора).
        return resource in {"meter_reading_documents", "meters"}
    return False


def _delete_allowed(user: User, resource: str) -> bool:
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.operator:
        return resource in OPERATION_WRITE_DELETE
    return False


# Удаление операционных данных доступно admin и operator.
OPERATION_WRITE_DELETE = {
    "payments",
    "transactions",
    "accrual_documents",
    "receipt_documents",
    "meter_reading_documents",
    "owners",
    "apartments",
    "accounts",
    "meters",
}


# Роли только на чтение: auditor (и resident для документов/операций).
READONLY_ROLES = {UserRole.auditor, UserRole.resident}


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
    """Зависимость для generic-эндпоинтов CRUD: проверяет роль на (метод, ресурс)."""
    method = (request.method or "GET").upper()
    if method in ("GET", "HEAD"):
        if not _read_allowed(user, resource):
            raise HTTPException(status_code=403, detail="Недостаточно прав на просмотр")
    elif method == "DELETE":
        if not _delete_allowed(user, resource):
            raise HTTPException(status_code=403, detail="Недостаточно прав на удаление")
    else:  # POST / PATCH / PUT
        if not _create_update_allowed(user, resource):
            raise HTTPException(status_code=403, detail="Недостаточно прав на изменение")
    return user
