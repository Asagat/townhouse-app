# Architecture: Townhouse App

## System Architecture
- Client-server architecture separating a React/Refine frontend from a robust FastAPI backend.
- Frontend — UI и предварительные предпросмотры; **все расчёты/валидации/состояние — на backend** (см. `.ai/BUSINESS_RULES.md`).

## Components & Layers
- **Presentation:** React (Refine) SPA — `frontend/` (`pages/`, `components/`, `config/`, `auth/`).
- **API Layer:** FastAPI routers (`backend/routers/`) handling HTTP requests and responses.
- **Business Logic Layer:** Service modules (`backend/services.py` и др.) encapsulating domain logic and rules.
- **Data Access Layer:** SQLAlchemy models (`backend/models.py`) and database persistence (PostgreSQL).

## Dependencies & Data Flow
- Request -> Router -> Service -> Database Model -> Return payload.
- State mutation and critical validations happen strictly within the backend services.
- Учёт показаний/начислений построен как «документ → регистр» (подробности структуры полей и API — в корневом `PROJECT_STRUCTURE.md`).

## Schema & reasoning pointers
- Изменение схемы — только через Alembic-ревизии (`backend/migrations/README.md`).
- Зафиксированные решения по стеку — `.ai/DECISIONS.md` (ADR).
