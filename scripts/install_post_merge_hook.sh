#!/usr/bin/env bash
# ============================================================================
# install_post_merge_hook.sh — установка git-hook post-merge в текущий клон.
# ============================================================================
# После установки каждый `git pull` (обычный merge) автоматически запускает
# scripts/update_db_after_pull.sh: догон схемы + импорт новых дампов (если в .env
# задан DB_MIRROR_BACKUPS). Лог каждого запуска — .git/post-merge.log.
#
# Использование:
#   ./scripts/install_post_merge_hook.sh    # установить hook
#   ./scripts/install_post_merge_hook.sh --remove   # удалить hook
# ============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_DIR="$ROOT/.git/hooks"
HOOK="$HOOK_DIR/post-merge"

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
# Автообновление БД после git pull — см. DEPLOY.md §7.3 и scripts/.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
"$ROOT/scripts/update_db_after_pull.sh" 2>&1 | tee -a "$ROOT/.git/post-merge.log"
exit "${PIPESTATUS[0]}"
HOOK_EOF
chmod +x "$HOOK"

echo "✅ Hook установлен: $HOOK"
echo "   После каждого 'git pull' будет запускаться scripts/update_db_after_pull.sh."
echo "   Лог: $ROOT/.git/post-merge.log   (удалить hook: $0 --remove)"
echo
echo "   ВАЖНО: 'git pull --rebase' hook НЕ запускает. Для автообновления"
echo "   используйте обычный 'git pull' (merge)."
