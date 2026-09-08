# Domain Map: Townhouse App

## Domain: Core Operations
- **Models:** Defined via SQLAlchemy in backend models.
- **API:** FastAPI router endpoints under backend app.
- **Services:** Business logic handlers.
- **Source of Truth:** PostgreSQL database / Backend calculations.
- **Important Invariants:** Transaction integrity and authorization checks must never be bypassed.
