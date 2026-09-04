#!/usr/bin/env bash
# ============================================================================
# restore_townhouse.sh — восстановление БД Townhouse из plain-SQL дампов
# ============================================================================
# Восстанавливает данные (и при необходимости роли) на PostgreSQL.
# Поддерживает окружение Docker (`docker compose`) и локальный доступ psql.
#
# Параметры подключения берутся из .env в корне проекта
# (POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_PORT / POSTGRES_DB),
# либо задаются переменными окружения.
#
# Дампы (создаются рядом, см. раздел Резервное копирование):
#   backend/backups/townhouse_<дата>.sql          — полный: схема + данные (plain SQL)
#   backend/backups/townhouse_roles_<дата>.sql    — только роли/пользователи кластера
#
# ИСПОЛЬЗОВАНИЕ:
#   ./scripts/restore_townhouse.sh data <файл.sql>            # залить данные в существующую БД
#   ./scripts/restore_townhouse.sh data --fresh <файл.sql>    # СТЕРЕТЬ БД и пересоздать, затем залить
#   ./scripts/restore_townhouse.sh roles [--force] <роли.sql> # применить роли
#   ./scripts/restore_townhouse.sh all --fresh <файл.sql> <роли.sql>
# ============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---- значения подключения (.env или дефолты/переменные) ---------------------
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

# Определяем container id postgres (если в Docker compose).
PG_CID="$(docker compose -f "$ROOT/docker-compose.yml" ps -q postgres 2>/dev/null || true)"

# psql-стрелка: читает SQL из СВОЕГО stdin.
# $1 = целевая база ('postgres' для DDL уровня кластера, иначе $PG_DB)
run_psql() {
  local db="$1"
  shift
  if [ -n "$PG_CID" ]; then
    PGPASSWORD="$PG_PASS" docker exec -i "$PG_CID" env PGPASSWORD="$PG_PASS" \
      psql -U "$PG_USER" -d "$db" -v ON_ERROR_STOP=0 "$@"
  else
    PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$db" \
      -v ON_ERROR_STOP=0 "$@"
  fi
}

require_backend() {
  if [ -z "$PG_CID" ] && ! command -v psql >/dev/null 2>&1; then
    echo "ОШИБКА: нет запущенного postgres-контейнера (docker compose ps) и нет локального psql." >&2
    exit 1
  fi
}

# ============================= данные ========================================
restore_data() {
  local fresh=0
  [ "${1:-}" = "--fresh" ] && { fresh=1; shift; }
  local file="${1:-}"
  [ -n "$file" ] && [ -f "$file" ] || { echo "ОШИБКА: файл дампа не найден: $file" >&2; exit 1; }
  require_backend

  if [ "$fresh" -eq 1 ]; then
    echo ">> ВНИМАНИЕ: БД '$PG_DB' будет СТЁРТА и пересоздана. Отвечайте 'yes' для продолжения:"
    read -r ans
    [ "$ans" = "yes" ] || { echo "Прервано пользователем."; exit 1; }

    echo ">> завершение активных сессий к '$PG_DB' ..."
    printf "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='%s' AND pid<>pg_backend_pid();\n" "$PG_DB" | run_psql postgres >/dev/null 2>&1 || true
    echo ">> drop/create '$PG_DB' ..."
    printf "DROP DATABASE IF EXISTS \"%s\";\nCREATE DATABASE \"%s\" OWNER \"%s\";\n" "$PG_DB" "$PG_DB" "$PG_USER" | run_psql postgres -v ON_ERROR_STOP=1
  fi

  echo ">> заливаем '$file' -> '$PG_DB' ..."
  run_psql "$PG_DB" -v ON_ERROR_STOP=1 < "$file"
  echo ">> Готово: данные восстановлены в '$PG_DB'."
}

# ============================== роли =========================================
restore_roles() {
  local force=0
  [ "${1:-}" = "--force" ] && { force=1; shift; }
  local file="${1:-}"
  [ -n "$file" ] && [ -f "$file" ] || { echo "ОШИБКА: файл ролей не найден: $file" >&2; exit 1; }
  require_backend

  if [ "$force" -eq 1 ]; then
    # попытка удалить роли из дампа (ошибки пропускаем: если роли используют другие объекты)
    sed -nE 's/^CREATE ROLE ([^ ;]+);/\1/p' "$file" | sort -u | while read -r r; do
      [ -n "${r:-}" ] || continue
      printf 'DROP ROLE IF EXISTS "%s";\n' "$r" | run_psql postgres -v ON_ERROR_STOP=0 >/dev/null 2>&1 || true
    done
  fi

  echo ">> применяем '$file' (уже существующие роли: CREATE ROLE будет проигнорирован) ..."
  # ON_ERROR_STOP=0: CREATE ROLE для существующих даёт ошибку — пропускаем, ALTER/прочее применяется.
  run_psql postgres -v ON_ERROR_STOP=0 < "$file" || true
  echo ">> Роли применены (с --force удалены и пересозданы)."
}

# ============================= dispatch ======================================
main() {
  [ $# -ge 1 ] || { echo "Недостаточно аргументов. См. шапку скрипта."; exit 1; }
  case "$1" in
    data)
      shift; restore_data "$@";;
    roles)
      shift; restore_roles "$@";;
    all)
      shift
      local fresh=0
      [ "${1:-}" = "--fresh" ] && { fresh=1; shift; }
      [ $# -ge 2 ] || { echo "Использование: all [--fresh] <данные.sql> <роли.sql>"; exit 1; }
      local df="${1:-}" rf="${2:-}"
      restore_data $([ "$fresh" -eq 1 ] && echo --fresh || true) "$df"
      restore_roles "$rf";;
    *)
      echo "Неизвестная команда: $1" >&2; exit 1;;
  esac
}

main "$@"
