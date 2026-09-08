# AGENTS.md — Townhouse App

> Дополнительный проектный контекст (архитектура, бизнес-правила, ADR,
> доменная карта, dev-практики) лежит в папке `.ai/` — см. `.ai/*.md`.
> Здесь AGENTS.md — краткий контракт правил; при расхождении приоритет — этот файл.
>
> **Язык:** всегда работай и отвечай только на русском (переход на английский не допускается).

## Architecture & Constraints
- FastAPI backend + React/Refine frontend stack deployed across Proxmox LXC containers.
- Strictly adhere to existing modular patterns; do not introduce conflicting architectural layers.

## Source of Truth
- Backend calculations, validation, and database states are the absolute source of truth.
- Frontend components provide UI presentation and preliminary previews only.

## Database & API Rules
- Use SQLAlchemy and Alembic for database changes and migrations.
- API endpoints must include input validation, proper status codes, and authorization checks.

## Permissions & Testing
- Frontend visibility does not replace backend security checks.
- Keep tests updated for all business logic changes.

## Prohibitions
- Do not silently refactor large modules (e.g., `services.py`) without an explicit standalone refactoring task.
- Do not guess missing requirements or unknown data structures; explicitly use `UNKNOWN` and ask.
