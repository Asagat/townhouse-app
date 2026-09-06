#!/usr/bin/env bash
# ============================================================================
# update_db_after_pull.sh — автообновление БД сразу после `git pull`.
# ============================================================================
# Вызывается из git-hook post-merge (см. scripts/install_post_merge_hook.sh),
# можно запускать и вручную после pull.
#
# Делает (всё идемпотентно):
#   1) догон СХЕМЫ до актуального кода: alembic upgrade head + справочники
#      (init_data.py) + админ (create_user.py) — на ЛЮБОМ ПК;
#   2) зеркальный импорт ДАННЫХ, только если в .env задан DB_MIRROR_BACKUPS
#      и в источнике появился новый дамп (скрипт refresh_from_backups.sh).
#
# Безопасно для машин, где DB_MIRROR_BACKUPS не задан: шаг (2) молча пропускается.
# ============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "▶ После-pull обновление БД ($(date '+%F %T'))"

# ---- 1) схема + справочники + админ (идемпотентно) ------------------------
# Окружение бэкенда: .venv (нативный запуск, snowflake) или backend-контейнер
# (docker compose, corsus) — выбирается автоматически.
run_backend_py() {
  if [ -x "$ROOT/.venv/bin/python" ]; then
    (cd "$ROOT/backend" && "$ROOT/.venv/bin/python" "$@")
    return $?
  fi
  local cid
  cid="$(docker compose -f "$ROOT/docker-compose.yml" ps -q backend 2>/dev/null || true)"
  if [ -n "$cid" ]; then
    docker compose -f "$ROOT/docker-compose.yml" exec -T backend python "$@"
    return $?
  fi
  echo "⚠️  Нет .venv и нет backend-контейнера — догон схемы пропущен."
  echo "   Настройте окружение один раз: ./scripts/dev.sh --full (snowflake) / docker compose up (corsus)."
  return 0
}

echo "▶ alembic upgrade head..."
run_backend_py -m alembic upgrade head
echo "▶ init_data.py (справочники)..."
run_backend_py init_data.py
echo "▶ create_user.py (админ)..."
run_backend_py create_user.py

# ---- 2) зеркальные данные (если машина зеркальная) ------------------------
"$SCRIPT_DIR/refresh_from_backups.sh" --yes

echo "✅ Обновление БД после pull завершено."
