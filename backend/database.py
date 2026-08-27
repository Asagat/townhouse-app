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

# Пытаемся взять URL из окружения, если нет — используем локальный Postgres.
# В продакшене всегда задавайте DATABASE_URL явно.
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/townhouse_db"
)

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
