import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Загружаем переменные из .env. Ищем файл в корне репозитория и — на всякий случай —
# в каталоге backend/. Явный путь избавляет от зависимости от текущей рабочей директории
# запуска (uvicorn можно стартовать из любого каталога).
_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_BACKEND_DIR / ".env")


# Автоматическая сборка строки подключения к PostgreSQL.
#
# Приоритет:
#   1) DATABASE_URL, если задан (полный SQLAlchemy URL, напр. с драйвером
#      postgresql+psycopg2:// или нестандартным портом) — используется как есть;
#   2) иначе URL собирается из POSTGRES_* переменных (удобно для local-разработки
#      и docker-compose): POSTGRES_HOST / POSTGRES_PORT / POSTGRES_USER /
#      POSTGRES_PASSWORD / POSTGRES_DB.
#
# Так в .env достаточно указать либо DATABASE_URL, либо набор POSTGRES_* — дублировать
# не нужно.
def build_database_url() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit and explicit.strip():
        return explicit.strip()

    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db = os.getenv("POSTGRES_DB", "townhouse")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


SQLALCHEMY_DATABASE_URL = build_database_url()

# Создаем движок подключения
# pool_pre_ping=True — критически важно для Docker/LXC:
# проверяет живо ли соединение перед использованием, предотвращая ошибки 500
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)

# Фабрика сессий для работы с данными
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для всех моделей (его импортируем в models.py)
Base = declarative_base()


# Вспомогательная функция (Dependency) для FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
