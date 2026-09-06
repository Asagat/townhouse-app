#!/usr/bin/env bash
# ============================================================================
# refresh_from_backups.sh — импорт свежих дампов «основной» копии в БД
# зеркального ПК (snowflake).
# ============================================================================
# Назначение: БД на зеркальном ПК должна повторять состояние основного ПК и
# обновляться импортом дампов из синхронизируемой папки (например, Synology
# Drive): ../townhouse-app/backend/backups. Каталог в git НЕ коммитится, поэтому
# дампы приходят не через git, а через синхронизацию папок.
#
# Включение — в корневом .env зеркального ПК:
#   DB_MIRROR_BACKUPS=../townhouse-app/backend/backups   # путь к дампам (или абсолютный)
# Без этой переменной скрипт ничего не делает (машина не зеркальная).
#
# Использование:
#   ./scripts/refresh_from_backups.sh            # спросит подтверждение (drop/create БД!)
#   ./scripts/refresh_from_backups.sh --yes      # без запроса (для git-hook/автоматизации)
#   ./scripts/refresh_from_backups.sh --dry-run  # показать план, БД не трогать
#
# Что делает: находит САМЫЕ свежие townhouse_*.sql / townhouse_roles_*.sql,
# сравнивает с маркером последнего применённого дампа (.git/db_refresh.state) и,
# если появился новый, полностью пересоздаёт БД (restore_townhouse.sh all --fresh),
# затем догоняет схему/справочники/админа до кода (alembic + init_data + create_user).
# ============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---- флаги ----------------------------------------------------------------
YES=0
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes)     YES=1; shift;;
    --dry-run) DRY=1; shift;;
    *) echo "Неизвестный аргумент: $1" >&2; exit 1;;
  esac
done

# ---- значение из .env (как в restore_townhouse.sh) ------------------------
get_env() { # name  fallback
  local name="$1" fallback="${2:-}"
  local inline
  inline="$(grep -E "^${name}=" "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)"
  echo "${inline:-${!name:-$fallback}}"
}

MIRROR="$(get_env DB_MIRROR_BACKUPS '')"
if [ -z "$MIRROR" ]; then
  echo "▶ DB_MIRROR_BACKUPS не задан в .env — машина не зеркальная, ничего не делаю."
  exit 0
fi

# Каталог с дампами: абсолютный как есть, относительный — от корня репозитория
# (так '../townhouse-app/backend/backups' укажет на синхронизируемую копию-соседа).
if [[ "$MIRROR" = /* ]]; then
  SRC_DIR="$MIRROR"
else
  SRC_DIR="$(realpath -m "$ROOT/$MIRROR")"
fi

if [ ! -d "$SRC_DIR" ]; then
  echo "⚠️  Каталог дампов не найден (Synology Drive ещё не синхронизировал?): $SRC_DIR"
  exit 0
fi

# ---- самые свежие дампы ---------------------------------------------------
# Выбор по встроенной в имя метке времени (townhouse_ГГГГММДД_ЧЧММСС.sql),
# а не по mtime: при синхронизации (Synology Drive) mtime ненадёжен.
# Внимание: файл ролей (townhouse_roles_*.sql) тоже подходит под townhouse_*.sql —
# поэтому данные и роли выбираем раздельными масками.
DATA="$(ls "$SRC_DIR"/townhouse_*.sql 2>/dev/null | grep -v '/townhouse_roles_' | sort | tail -1 || true)"
ROLES="$(ls "$SRC_DIR"/townhouse_roles_*.sql 2>/dev/null | sort | tail -1 || true)"
if [ -z "${DATA:-}" ]; then
  echo "⚠️  В '$SRC_DIR' нет дампов townhouse_*.sql — жду первой синхронизации."
  exit 0
fi

DATA_NAME="$(basename "$DATA")"

# ---- маркер последнего применённого дампа (per-clone, внутри .git) --------
MARKER="$ROOT/.git/db_refresh.state"
LAST=""
[ -f "$MARKER" ] && LAST="$(cat "$MARKER" 2>/dev/null || true)"

if [ -n "$LAST" ] && [ "$LAST" = "$DATA_NAME" ]; then
  echo "▶ Дамп '$DATA_NAME' уже применён (маркер $MARKER). Новых дампов нет — выход."
  exit 0
fi

echo "=============================================================="
echo " Зеркальное обновление БД из дампов:"
echo "   источник : $SRC_DIR"
echo "   данные  : $DATA_NAME${ROLES:+ (+ $(basename "$ROLES"))}"
echo "   маркер  : ${LAST:-<не было>}"
if [ "$DRY" -eq 1 ]; then
  echo " --dry-run: план готов, БД НЕ трогаю."
  exit 0
fi
echo " ВНИМАНИЕ: локальная БД будет СТЁРТА и пересоздана из дампа."
echo "=============================================================="

if [ "$YES" -eq 0 ]; then
  echo "Продолжить? Введите 'yes':"
  read -r ans
  [ "$ans" = "yes" ] || { echo "Прервано пользователем."; exit 1; }
fi

# ---- импорт данных (полная замена) ----------------------------------------
if [ -n "${ROLES:-}" ]; then
  "$SCRIPT_DIR/restore_townhouse.sh" all --fresh --yes "$DATA" "$ROLES"
else
  echo ">> Файл ролей не найден — импортирую только данные."
  "$SCRIPT_DIR/restore_townhouse.sh" data --fresh --yes "$DATA"
fi

# ---- догон схемы до кода (если код новее дампа) ---------------------------
# Окружение бэкенда выбирается автоматически: .venv (нативный запуск, snowflake)
# либо backend-контейнер (docker compose, corsus).
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
  echo "⚠️  Нет .venv и нет backend-контейнера — команда python '$1' пропущена." >&2
  return 0
}

echo ">> Догоняю схему/справочники до актуального кода..."
run_backend_py -m alembic upgrade head
run_backend_py init_data.py
run_backend_py create_user.py

# ---- обновить маркер -------------------------------------------------------
echo "$DATA_NAME" > "$MARKER"
echo "✅ Готово: БД приведена к дампу '$DATA_NAME' (+ актуальная схема кода)."
