#!/usr/bin/env bash
# ============================================================================
# test_backend.sh — ИЗОЛИРОВАННЫЙ прогон backend-тестов (ТД-3).
# ============================================================================
# Зачем: раньше `docker compose exec backend python -m pytest` гонял тесты против
# РАБОЧЕЙ dev-БД. Тесты идемпотентны (создают уникальные метки и убирают их), но
# результат зависел от живых данных (флейки test_filtering), а ошибка в тесте могла
# задеть рабочую БД.
#
# Теперь тесты идут против ОДНОРАЗОВОЙ PostgreSQL:
#   - поднимается сервис postgres-test (docker-compose.test.yml, данные в tmpfs);
#   - на него накатываются схема (alembic upgrade head) и справочники (init_data.py);
#   - запускается pytest;
#   - контейнер и БД удаляются (данные не сохраняются).
# Рабочая БД (townhouse-postgres) при этом не задействуется вообще.
#
# Использование (из корня репозитория):
#   ./scripts/test_backend.sh                    # весь набор backend-тестов
#   ./scripts/test_backend.sh tests/test_x.py    # только выбранный файл
#   ./scripts/test_backend.sh tests/test_x.py::test_y -k foo   # произвольные аргументы pytest
# ============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.test.yml)

# URL тестовой БД. Хост — имя сервиса postgres-test: одноразовый backend-контейнер
# запускается в той же сети compose-проекта, где это имя резолвится.
TEST_DB_URL="postgresql://townhouse_test:townhouse_test@postgres-test:5432/townhouse_test"

cleanup() {
  # Удаляем контейнер и его tmpfs-данные; ошибку удаления не считаем фатальной.
  "${COMPOSE[@]}" rm -sf postgres-test >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo ">> Поднимаю одноразовую PostgreSQL (postgres-test, данные в tmpfs)..."
"${COMPOSE[@]}" up -d --wait postgres-test

echo ">> Прогон тестов против изолированной БД..."
# --no-deps: НЕ поднимать рабочие сервисы (postgres/backend/frontend). Backend
# запускается как одноразовый `run` в сети проекта (там резолвится postgres-test).
# Аргументы после скрипта передаются в pytest; по умолчанию — каталог tests/.
"${COMPOSE[@]}" run --rm --no-deps \
  -e DATABASE_URL="$TEST_DB_URL" \
  -e PYTHONUTF8=1 -e PYTHONIOENCODING=utf-8 \
  backend sh -c 'python -m alembic upgrade head && python init_data.py && python -m pytest "$@" -q' _ "${@:-tests/}"

echo ">> Готово: тесты выполнены на одноразовой БД (рабочая БД не затронута)."
