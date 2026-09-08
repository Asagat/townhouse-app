# Контекст проекта: Townhouse App

- **Назначение проекта:** стек бэкенд/фронтенд для операционного управления посёлком таунхаусов.
- **Технологический стек:** Python, FastAPI, SQLAlchemy, Alembic, Vite, React, фреймворк Refine, PostgreSQL, Docker Compose, LXC Proxmox VE.
- **Структура репозитория:** монолит с папками backend, frontend и скриптами настройки.
- **Основные компоненты:** REST API на FastAPI, SPA-панель на React.
- **Внешние системы:** экземпляры PostgreSQL.
- **Среда разработки:** Linux (Fedora Workstation), Docker Compose / Podman.
- **Тестирование:** проверка бэкенда через Pytest.
- **Развёртывание:** контейнеры LXC Proxmox.

## Канонические источники (единые точки правды)

Чтобы не расходиться в деталях, ключевые факты храним в одном месте, а остальные документы на них ссылаются:

- **Переменные окружения:** шаблон `.env.example` (корень репозитория) + `docker-compose.yml`; справку по настройке — см. `DEPLOY.md §1`.
- **Схема и миграции Alembic:** справочник `backend/migrations/README.md`; файлы `DEPLOY.md` и `PROJECT_STRUCTURE.md` лишь ссылаются на него.
- **Запуск в разработке:** `scripts/dev.sh` (бэкенд и база) и `cd frontend && npm run dev` (Vite); Docker-стек — `DEPLOY.md §7`.
- **Тесты и непрерывная интеграция:** канон — `.github/workflows/ci.yml`; локальные команды — `DEPLOY.md §6`.
- **Проверка типов и сборка фронтенда:** `frontend/package.json` (`npm run build` = `tsc` + `vite build`); локальный обзор — `frontend/README.md`.

Файл `AGENTS.md` — краткий контракт правил для агента; папка `.ai/*.md` — расширенный контекст (архитектура, бизнес-правила, учёт решений, карта доменов и практики разработки).
