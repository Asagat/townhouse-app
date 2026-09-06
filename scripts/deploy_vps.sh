#!/usr/bin/env bash
# ============================================================
# Обновление Townhouse ERP на VPS.
# Идемпотентно: безопасно запускать повторно.
#
# Делает: git fetch -> фиксация кода -> alembic upgrade -> init_data
#          -> create_user -> сборка фронтенда (npm ci + npm run build)
#          -> перезапуск backend-сервиса (systemd, если установлен).
#
# Использование (на VPS, из корня проекта /opt/townhouse):
#   ./scripts/deploy_vps.sh                  # авто-выкат: git pull (main)
#   ./scripts/deploy_vps.sh <ветка|тег|SHA>  # выкат конкретного состояния
#                                            # (ветка фиксируется на origin/<ветка>;
#                                            # тег/SHA — detached HEAD)
#
# Без аргумента после деплоя по тегу репозиторий может остаться в detached HEAD —
# вернитесь на main:  git checkout -f main && ./scripts/deploy_vps.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
VENV="${ROOT_DIR}/.venv"

SERVICE="townhouse-backend"

# Необязательный аргумент/переменная: ветка, тег или SHA для выката.
TARGET_REF="${1:-${TARGET_REF:-}}"

echo "▶ Проект: ${ROOT_DIR}"

# 1) .env должен существовать (секреты на VPS не генерятся автоматически)
if [ ! -f "${ROOT_DIR}/.env" ]; then
  echo "❌ Не найден ${ROOT_DIR}/.env. Скопируйте .env.example -> .env и заполните." >&2
  exit 1
fi

# 2) Забрать код и миграции
(
  cd "${ROOT_DIR}"
  git fetch --prune origin --tags
  if [ -n "${TARGET_REF}" ]; then
    echo "▶ Фиксирую код на ${TARGET_REF}..."
    if git show-ref --verify --quiet "refs/remotes/origin/${TARGET_REF}"; then
      # Ветка: переходим на неё и жёстко фиксируем на состояние origin/<ветка>.
      git checkout -f "${TARGET_REF}" 2>/dev/null || git checkout -f -b "${TARGET_REF}" --track "origin/${TARGET_REF}"
      git reset --hard "origin/${TARGET_REF}"
    else
      # Тег или SHA: подтягиваем объект и отцепляем HEAD.
      git fetch origin "${TARGET_REF}" || true
      git checkout -f --detach "${TARGET_REF}"
    fi
  else
    # Авто-выкат по умолчанию: подтянуть текущую ветку (обычно main).
    if git symbolic-ref --quiet HEAD >/dev/null; then
      echo "▶ git pull..."
      git pull
    else
      echo "❌ Репозиторий в состоянии detached HEAD (после деплоя по тегу)." >&2
      echo "   Вернитесь на main и повторите:  git checkout -f main && ./scripts/deploy_vps.sh" >&2
      exit 1
    fi
  fi
)

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

# 6) Фронтенд — production-сборка (nginx отдаёт статику из frontend/dist).
# Собираем при каждом деплое: гарантирует, что dist соответствует выкачанному коду
# даже при откате/деплое по тегу (diff HEAD~1..HEAD тогда не показатель).
if command -v npm >/dev/null 2>&1; then
  cd "${ROOT_DIR}/frontend"
  echo "▶ npm ci (фронтенд)..."
  npm ci || npm install
  echo "▶ npm run build (в dist.tmp, затем атомарная замена dist)..."
  rm -rf dist.tmp
  # --outDir/--emptyOutDir npm дописывает в конец скрипта "tsc && vite build"
  # (т.е. достаются только vite build); tsc не затрагивается.
  npm run build -- --outDir dist.tmp --emptyOutDir
  rm -rf dist
  mv dist.tmp dist
  cd "${BACKEND_DIR}"
else
  echo "⚠️ npm не найден — фронтенд не пересобран (nginx продолжит отдавать прежнюю статику)."
fi

# 7) Перезапуск сервиса
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
