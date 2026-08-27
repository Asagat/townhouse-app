#!/usr/bin/env bash
# ============================================================
# Обновление Townhouse ERP на VPS.
# Идемпотентно: безопасно запускать повторно.
#
# Делает: git pull -> alembic upgrade -> init_data -> create_user
#          -> перезапуск backend-сервиса (systemd, если установлен).
#
# Использование (на VPS, из корня проекта /opt/townhouse):
#   ./scripts/deploy_vps.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
VENV="${ROOT_DIR}/.venv"

SERVICE="townhouse-backend"

echo "▶ Проект: ${ROOT_DIR}"

# 1) .env должен существовать (секреты на VPS не генерятся автоматически)
if [ ! -f "${ROOT_DIR}/.env" ]; then
  echo "❌ Не найден ${ROOT_DIR}/.env. Скопируйте .env.example -> .env и заполните." >&2
  exit 1
fi

# 2) Забрать код и миграции
echo "▶ git pull..."
git -C "${ROOT_DIR}" pull

# 3) venv
if [ ! -d "$VENV" ]; then
  echo "▶ Создаю venv..."
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

# 4) Зависимости (если изменились — сверка с предыдущим коммитом, если он есть)
NEEDS_REQ=0
if git -C "${ROOT_DIR}" rev-parse --verify HEAD~1 >/dev/null 2>&1; then
  if git -C "${ROOT_DIR}" diff --name-only HEAD~1 HEAD | grep -q "backend/requirements.txt"; then
    NEEDS_REQ=1
  fi
else
  # Первый деплой — переустановить зависимые наверняка.
  NEEDS_REQ=1
fi
if [ "$NEEDS_REQ" = "1" ]; then
  echo "▶ (Пере)устанавливаю зависимости бэкенда..."
  pip install -r "${BACKEND_DIR}/requirements.txt"
else
  echo "▶ requirements.txt не менялся — переустановка не требуется."
fi

# 5) Миграции, справочники, админ
cd "${BACKEND_DIR}"
echo "▶ alembic upgrade head..."
alembic upgrade head
echo "▶ init_data.py (справочники)..."
python init_data.py
echo "▶ create_user.py (админ)..."
python create_user.py

# 6) Перезапуск сервиса
if systemctl list-unit-files 2>/dev/null | grep -q "^${SERVICE}\.service"; then
  echo "▶ Перезапускаю ${SERVICE}.service..."
  systemctl restart "${SERVICE}"
  systemctl --no-pager --lines=0 status "${SERVICE}" || true
else
  echo "⚠️  Юнит ${SERVICE}.service не установлен."
  echo "   Установите его: (пример в deploy/townhouse-backend.service)"
  echo "   cp deploy/townhouse-backend.service /etc/systemd/system/"
  echo "   systemctl daemon-reload && systemctl enable --now ${SERVICE}"
fi

echo
echo "✅ Развёртывание завершено."
