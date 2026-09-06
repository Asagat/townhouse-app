#!/usr/bin/env bash
# ============================================================================
# dump_to_sync.sh — выгрузка дампа «активным» ПК в общую синхронизируемую папку
# ============================================================================
# Симметричный режим (corsus <-> snowflake): разработка ведётся ПО ОЧЕРЕДИ.
# Тот ПК, на котором сейчас работают с БД («активный»), в конце сеанса выгружает
# состояние БД в папку, синхронизируемую через Synology Drive. Другой ПК
# подхватит дамп автоматически после следующего `git pull`
# (update_db_after_pull.sh / refresh_from_backups.sh, см. DEPLOY §7.4).
#
# Куда кладётся дамп:
#   - DB_MIRROR_BACKUPS из .env (та же переменная, что у refresh_from_backups.sh),
#     если задана: на corsus — backend/backups, на snowflake — ../townhouse-app/backend/backups;
#   - иначе — backend/backups в корне проекта.
#
# После успешной выгрузки ставится маркер .git/db_refresh.state на этот дамп:
# это означает «локальная БД уже соответствует этому дампу», поэтому свой же
# свежий дамп НЕ будет повторно импортирован этим ПК при следующем pull.
#
# Использование (на активном ПК, когда заканчиваете сеанс работы):
#   ./scripts/dump_to_sync.sh
# ============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---- значения подключения из .env (как в restore_townhouse.sh) -------------
get_env() { # name  fallback
  local name="$1" fallback="${2:-}"
  local inline
  inline="$(grep -E "^${name}=" "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)"
  echo "${inline:-${!name:-$fallback}}"
}

PG_USER="$(get_env POSTGRES_USER townhouse_user)"
PG_PASS="$(get_env POSTGRES_PASSWORD)"
PG_PORT="$(get_env POSTGRES_PORT 5432)"
PG_DB="$(get_env POSTGRES_DB townhouse)"
PG_HOST="$(get_env POSTGRES_HOST 127.0.0.1)"

# --- куда складывать дамп --------------------------------------------------
MIRROR="$(get_env DB_MIRROR_BACKUPS 'backend/backups')"
if [[ "$MIRROR" = /* ]]; then
  OUT_DIR="$MIRROR"
else
  OUT_DIR="$(realpath -m "$ROOT/$MIRROR")"
fi
mkdir -p "$OUT_DIR"

# --- источник: postgres-контейнер (docker compose) либо локальный PG --------
PG_CID="$(docker compose -f "$ROOT/docker-compose.yml" ps -q postgres 2>/dev/null || true)"

if [ -n "$PG_CID" ]; then
  echo "▶ Источник: postgres-контейнер ($PG_CID)"
  run_pg_dump() { # $@ -> pg_dump-аргументы (вывод в stdout)
    docker exec -i "$PG_CID" sh -c "PGPASSWORD=\"$PG_PASS\" pg_dump -U \"$PG_USER\" -d \"$PG_DB\" $*"
  }
  run_pg_dumpall_roles() {
    docker exec -i "$PG_CID" sh -c "PGPASSWORD=\"$PG_PASS\" pg_dumpall --roles-only -U \"$PG_USER\""
  }
else
  command -v pg_dump >/dev/null 2>&1 || { echo "ОШИБКА: нет postgres-контейнера и нет локального pg_dump." >&2; exit 1; }
  echo "▶ Источник: локальный PostgreSQL ($PG_HOST:$PG_PORT/$PG_DB)"
  run_pg_dump() {
    PGPASSWORD="$PG_PASS" pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" "$@"
  }
  run_pg_dumpall_roles() {
    PGPASSWORD="$PG_PASS" pg_dumpall --roles-only -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER"
  }
fi

# --- сам дамп --------------------------------------------------------------
STAMP="$(date +%Y%m%d_%H%M%S)"
DATA_NAME="townhouse_${STAMP}.sql"
ROLES_NAME="townhouse_roles_${STAMP}.sql"

echo "▶ Выгружаю данные (схема+данные, --no-owner --no-privileges)..."
run_pg_dump --no-owner --no-privileges > "$OUT_DIR/$DATA_NAME"
echo "   -> $OUT_DIR/$DATA_NAME ($(du -h "$OUT_DIR/$DATA_NAME" | cut -f1))"

if run_pg_dumpall_roles > "$OUT_DIR/$ROLES_NAME" 2>/dev/null; then
  echo "▶ Роли выгружены -> $OUT_DIR/$ROLES_NAME"
else
  rm -f "$OUT_DIR/$ROLES_NAME"
  echo "⚠️  Роли не выгружены (нужен суперпользователь/доступ к кластеру)."
  echo "   Файл ролей необязателен — на Docker-базе роли уже созданы из .env."
fi

# --- маркер: «локальная БД соответствует этому дампу» ----------------------
if [ -d "$ROOT/.git" ]; then
  echo "$DATA_NAME" > "$ROOT/.git/db_refresh.state"
  echo "▶ Маркер обновлён: .git/db_refresh.state = $DATA_NAME"
else
  echo "⚠️  Не git-репозиторий — маркер не ставится."
fi

echo
echo "✅ Дамп готов к передаче: '$DATA_NAME' в '$OUT_DIR'."
echo "   На другом ПК он применится автоматически после следующего 'git pull'"
echo "   (или вручную: ./scripts/update_db_after_pull.sh)."
