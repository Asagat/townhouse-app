#!/usr/bin/env bash
# ============================================================
# Полная установка Townhouse ERP на НОВОМ сервере VPS (Ubuntu/Debian).
# Отличается от deploy_vps.sh (тот — обновление уже стоящего проекта):
# этот скрипт делает всё «с нуля» на чистом сервере.
#
# Что делает:
#   - ставит системные пакеты (git, python3-venv/pip, npm, ...);
#   - клонирует репозиторий;
#   - создаёт venv, ставит зависимости;
#   - помогает с .env и создаёт схему/справочники/админа;
#   - устанавливает systemd-юнит для бэкенда и включает его;
#   - собирает фронтенд (build) и подсказывает конфиг nginx.
#
# Запуск:  sudo bash scripts/setup_vps.sh
# ============================================================
set -euo pipefail

# Гарантируем UTF-8 для всех Python/системных утилит независимо от локали сервера.
# Если LANG/LC_ALL отсутствуют или равны C (ascii), то: 1) python-print кириллицы даст
# UnicodeEncodeError; 2) alembic не прочитает alembic.ini с кириллицей (configparser
# использует locale-кодировку). C.UTF-8 есть на Ubuntu/Debian по умолчанию и решает обе
# проблемы за счёт locale.getpreferredencoding()==utf-8.
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
# PYTHONUTF8 / PYTHONIOENCODING дополнительно принуждают UTF-8-mode Python.
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

# --- Настройки (при необходимости измените) -------------------------
GIT_REPO="${GIT_REPO:-https://github.com/Asagat/townhouse-app.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/townhouse}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
# --------------------------------------------------------------------

if [ "$(id -u)" -ne 0 ]; then
  echo "❌ Запустите с sudo или от root." >&2
  exit 1
fi

echo "▶ ОС: $(. /etc/os-release && echo "$PRETTY_NAME")"

# 1) Системные пакеты
echo "▶ Устанавливаю системные пакеты (git, python, venv, pip, nodejs, npm)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git python3 python3-venv python3-pip nodejs npm \
  libpq-dev build-essential nginx

# 2) Клонирование репозитория
if [ ! -d "${APP_DIR}/.git" ]; then
  mkdir -p "${APP_DIR}"
  echo "▶ Клонирую ${GIT_REPO} (${BRANCH}) в ${APP_DIR}..."
  git clone --branch "${BRANCH}" --depth 1 "${GIT_REPO}" "${APP_DIR}"
else
  echo "▶ Репозиторий уже есть — обновляю..."
  git -C "${APP_DIR}" fetch --depth 1 origin "${BRANCH}"
  git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
fi
cd "${APP_DIR}"

# 3) .env
if [ ! -f "${APP_DIR}/.env" ]; then
  cp .env.example .env
  echo "ⓘ Создан ${APP_DIR}/.env из примера."
  echo "   ОБЯЗАТЕЛЬНО отредактируйте его:"
  echo "     - DATABASE_URL или POSTGRES_*;"
  echo "     - AUTH_SECRET_KEY (задайте случайный);"
  echo "     - CORS_ORIGINS под ваш домен;"
  echo "   затем перезапустите скрипт:  bash scripts/setup_vps.sh"
else
  echo "▶ .env уже есть — не перезаписываю."
fi

# 4) venv + зависимости
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

# 5) Проверка подключения к БД и её кодировки (кириллица ⇒ нужен UTF8, не SQL_ASCII)
python -X utf8 - <<'PY'
import os, sys
from sqlalchemy import create_engine, text
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))
os.chdir("backend")
from database import SQLALCHEMY_DATABASE_URL
engine = None
try:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    with engine.connect() as conn:
        enc = conn.execute(text("SHOW server_encoding")).scalar()
    print(f"▶ Подключение к БД — OK (server_encoding={enc})")
    if enc and enc != "UTF8":
        print("❌ Кодировка БД не UTF8, а", enc, "— кириллица будет падать с UnicodeEncodeError.")
        print("   Пересоздайте БД с ENCODING 'UTF8' (см. DEPLOY.md):")
        print("     CREATE DATABASE townhouse OWNER townhouse_user ENCODING 'UTF8' LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8' TEMPLATE template0;")
        sys.exit(1)
except SystemExit:
    raise
except Exception as e:
    print("❌ Не удалось подключиться к БД:", e)
    print("   Создайте базу (см. ниже) и исправьте .env, затем повторите.")
    sys.exit(1)
finally:
    if engine is not None:
        engine.dispose()
PY

# 6) Схема, справочники, админ
# -X utf8 принудительно включает UTF-8 mode Python на случай не-C.UTF-8 локалей,
# чтобы кириллица в логах/выводе никогда не падала с UnicodeEncodeError.
cd backend
alembic upgrade head
python -X utf8 init_data.py
if [ -z "${ADMIN_PASSWORD:-}" ]; then
  echo "▶ create_user.py (пароль из ADMIN_PASSWORD или случайный)..."
  python -X utf8 create_user.py
else
  ADMIN_PASSWORD="$ADMIN_PASSWORD" python -X utf8 create_user.py
fi
cd ..

# 7) systemd-юнит для бэкенда
echo "▶ Устанавливаю systemd-юнит townhouse-backend..."
sed -e "s|/opt/townhouse|${APP_DIR}|g" \
    deploy/townhouse-backend.service > /etc/systemd/system/townhouse-backend.service
systemctl daemon-reload
systemctl enable --now townhouse-backend
systemctl --no-pager --lines=5 status townhouse-backend || true

# 8) Фронтенд — production-сборка
echo "▶ Собираю фронтенд (npm run build)..."
cd frontend
npm install
npm run build
cd ..

echo
echo "✅ Установка завершена. Что осталось вручную:"
echo "  1. nginx: из deploy/nginx.conf.template (замените __DOMAIN__ и __APP_DIR__):"
echo "       sed -e 's|__DOMAIN__|ваш домен|' -e 's|__APP_DIR__|${APP_DIR}|' deploy/nginx.conf.template > /etc/nginx/sites-available/townhouse"
echo "       ln -s /etc/nginx/sites-available/townhouse /etc/nginx/sites-enabled/ || true"
echo "       nginx -t && systemctl reload nginx"
echo "  2. domain/DNS → на IP сервера."
echo "  3. Бэкап данных: см. DEPLOY.md раздел «Резервное копирование»."
