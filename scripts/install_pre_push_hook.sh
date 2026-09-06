#!/usr/bin/env bash
# ============================================================================
# install_pre_push_hook.sh — установка git-hook pre-push в текущий клон.
# ============================================================================
# Перед каждым `git push` автоматически снимается дамп БД
# (scripts/dump_to_sync.sh): свежее состояние (схема + данные, включая правки
# справочников) уезжает в синхронизируемую папку (Synology Drive) и второй ПК
# подхватит его после своего `git pull` (post-merge → update_db_after_pull.sh).
#
# Подходит для обеих машин симметричного режима (DEPLOY §7.4): кто «активен» и
# пушит код — тот и выгружает дамп автоматически. Лог каждого запуска —
# .git/pre-push.log. Сбой дампа пуш НЕ блокирует (только предупреждение).
#
# Использование:
#   ./scripts/install_pre_push_hook.sh            # установить hook
#   ./scripts/install_pre_push_hook.sh --remove   # удалить hook
# ============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_DIR="$ROOT/.git/hooks"
HOOK="$HOOK_DIR/pre-push"

if [ ! -d "$ROOT/.git" ]; then
  echo "❌ Не git-репозиторий: $ROOT/.git не найден." >&2
  exit 1
fi

if [ "${1:-}" = "--remove" ]; then
  rm -f "$HOOK"
  echo "🗑️  Hook удалён: $HOOK"
  exit 0
fi

mkdir -p "$HOOK_DIR"
cat > "$HOOK" <<'HOOK_EOF'
#!/usr/bin/env bash
# Автодамп БД перед push — см. DEPLOY.md §7.4 и scripts/.
# Параметры remote-name/url игнорируем: дамп снимаем при любом push.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG="$ROOT/.git/pre-push.log"
echo "▶ pre-push: снимаю дамп БД ($(date '+%F %T'))..."
"$ROOT/scripts/dump_to_sync.sh" 2>&1 | tee -a "$LOG"
rc="${PIPESTATUS[0]}"
if [ "$rc" -ne 0 ]; then
  echo "⚠️  Дамп БД НЕ снят (rc=$rc) — подробности в $LOG. Пуш продолжается."
fi
exit 0
HOOK_EOF
chmod +x "$HOOK"

echo "✅ Hook установлен: $HOOK"
echo "   Перед каждым 'git push' будет запускаться scripts/dump_to_sync.sh."
echo "   Лог: $ROOT/.git/pre-push.log   (удалить hook: $0 --remove)"
