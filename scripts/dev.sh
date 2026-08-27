#!/usr/bin/env bash
# ============================================================
# Локальное развёртывание Townhouse ERP (dev-режим).
# Идемпотентно: можно запускать повторно — подтянет недостающее.
#
# Использование:
#   ./scripts/dev.sh            # развернуть и запустить бэкенд (uvicorn --reload)
#   ./scripts/dev.sh --full     # то же + установка Python-зависимостей (pip install)
#
# Требует: python3, (npm для фронтенда), PostgreSQL по DATABASE_URL/POSTGRES_* из .env
# ============================================================
set -euo pipefail

# Корень проекта = каталог скрипта /../..
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
VENV="${ROOT_DIR}/.venv"

FULL=0
for arg in "$@"; do
  [ "$arg" = "--full" ] && FULL=1
done

echo "▶ Проект: ${ROOT_DIR}"

# 1) Виртуальное окружение
if [ ! -d "$VENV" ]; then
  echo "▶ Создаю venv..."
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

if [ "$FULL" = "1" ] || ! pip show fastapi >/dev/null 2>&1; then
  echo "▶ Устанавливаю зависимости бэкенда..."
  pip install -r "${BACKEND_DIR}/requirements.txt"
fi

# 2) Проверка .env
if [ ! -f "${ROOT_DIR}/.env" ] && [ -f "${ROOT_DIR}/.env.example" ]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  echo "▶ Создан ${ROOT_DIR}/.env из примера — заполните его (пароли, CORS, ...)!"
fi

# 3) Схема БД (только Alembic) + справочники + админ
cd "${BACKEND_DIR}"
echo "▶ alembic upgrade head..."
alembic upgrade head
echo "▶ init_data.py (справочники)..."
python init_data.py
echo "▶ create_user.py (админ; пароль из ADMIN_PASSWORD или случайный)..."
python create_user.py

# 4) Проверка подключения к БД
python - <<'PY'
import os
from sqlalchemy import create_engine
from database import SQLALCHEMY_DATABASE_URL
create_engine(SQLALCHEMY_DATABASE_URL).connect().close()
print("▶ Подключение к БД — OK")
PY

echo
echo "✅ Бэкенд готов. Фронтенд — в отдельном терминале:"
echo "   cd frontend && npm install && npm run dev   # http://localhost:5173"
echo "▶ Запускаю API на http://localhost:8000 (Ctrl+C — остановить)..."
exec uvicorn app:app --host 0.0.0.0 --port 8000 --reload
