# backend/routers/preferences.py
"""Серверные настройки интерфейса пользователя (роадмап 2.13).

GET  /api/preferences            — все настройки текущего пользователя
                                   [{resource, data}, ...];
PUT  /api/preferences/{resource} — сохранить JSON-настройки раздела (upsert).

`data` — произвольный JSON (порядок/видимость/ширины колонок, сортировка,
применённые фильтры, pageSize). Каждый пользователь видит/меняет только свои
настройки; настройки доступны всем аутентифицированным ролям (личные UI-настройки,
не учётные данные — auditor тоже может сохранять вид списков).
"""

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User, UserPreference

router = APIRouter(prefix="/api")

# Ограничения «на всякий случай»: длина имени ресурса и число ключей/размер JSON.
MAX_RESOURCE_LEN = 100


@router.get("/preferences")
def my_preferences(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(UserPreference)
        .filter(UserPreference.user_id == user.id)
        .order_by(UserPreference.resource.asc())
        .all()
    )
    return [{"resource": r.resource, "data": r.data} for r in rows]


@router.put("/preferences/{resource}")
def save_preference(
    resource: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if len(resource) > MAX_RESOURCE_LEN or not resource.strip():
        raise HTTPException(status_code=422, detail="Недопустимое имя ресурса")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Настройки должны быть объектом JSON")

    row = (
        db.query(UserPreference)
        .filter(
            UserPreference.user_id == user.id,
            UserPreference.resource == resource.strip(),
        )
        .first()
    )
    if row is None:
        row = UserPreference(user_id=user.id, resource=resource.strip(), data=payload)
        db.add(row)
    else:
        row.data = payload
    db.commit()
    return {"resource": row.resource, "data": row.data}
