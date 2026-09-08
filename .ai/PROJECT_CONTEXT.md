# Project Context: Townhouse App

- **Project Purpose:** Management and operational backend/frontend stack for townhouse operations.
- **Technology Stack:** Python, FastAPI, SQLAlchemy, Alembic, Vite, React, Refine framework, PostgreSQL, Docker Compose, Proxmox VE LXC.
- **Repository Structure:** Monorepo containing backend, frontend, and configuration scripts.
- **Main Components:** FastAPI REST API, React SPA dashboard.
- **External Systems:** PostgreSQL database instances.
- **Development Environment:** Linux (Fedora Workstation), Docker Compose / Podman.
- **Testing:** Pytest for backend verification.
- **Deployment:** Proxmox LXC containers.

## Canonical references (single sources of truth)

Чтобы не расходиться в деталях, ключевые факты держим в одном месте, а доки на них ссылаются:

- **env-переменные:** шаблон `.env.example` (корень репозитория) + `docker-compose.yml`; руководство по настройке — `DEPLOY.md §1`.
- **Схема/миграции Alembic:** справочник `backend/migrations/README.md`; `DEPLOY.md` и `PROJECT_STRUCTURE.md` лишь ссылаются на него.
- **Запуск (dev):** `scripts/dev.sh` (бэкенд+БД), `cd frontend && npm run dev` (Vite); Docker-стек — `DEPLOY.md §7`.
- **Тесты/CI:** канон в `.github/workflows/ci.yml`; локальные команды — `DEPLOY.md §6`.
- **Проверка типов фронтенда/сборка:** `frontend/package.json` (`npm run build` = `tsc` + `vite build`), локальный README — `frontend/README.md`.

`AGENTS.md` — краткий контракт правил для агента; данная папка `.ai/*.md` — расширенный контекст (архитектура, бизнес-правила, ADR, доменная карта, dev-практики).
