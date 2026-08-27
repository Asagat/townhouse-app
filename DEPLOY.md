# Развёртывание Townhouse ERP

Документированный процесс установки/обновления окружения.
Принцип: **весь код и схема — только через git; настройки и секреты — только через `.env`.**

---

## 1. Переменные окружения (.env)

В корне репозитория скопируйте шаблон и заполните своими значениями:

```bash
cp .env.example .env
# отредактируйте .env: DATABASE_URL, AUTH_SECRET_KEY, CORS_ORIGINS, ...
```

- Никогда не коммитьте `.env` (он в `.gitignore`). Шаблон всех переменных — в `.env.example`.
- Пароль администратора передаётся через `ADMIN_PASSWORD` (или генерируется случайно) — см. `backend/create_user.py`.

---

## 2. Требования / предусловия

- **Python 3.11+** и доступ к **PostgreSQL**.
- **PostgreSQL должен быть запущен** и доступен по `DATABASE_URL` из `.env` (хост, порт, пользователь, пароль, имя БД). Проверка подключения — через SQLAlchemy (корректно при любом префиксе драйвера):
  ```bash
  python -c "import os;from dotenv import load_dotenv;load_dotenv();from sqlalchemy import create_engine;create_engine(os.getenv('DATABASE_URL')).connect().close();print('DB ok')"
  ```
  Если СУБД не запущена — запустите Postgres (или контейнер `docker run -d -e POSTGRES_USER=... -e POSTGRES_PASSWORD=... -e POSTGRES_DB=... -p 5432:5432 postgres:16`) и создайте базу.

> **Автоматическая сборка `DATABASE_URL`.** Если в `.env` не задан `DATABASE_URL`, строка
> подключения к Postgres собирается автоматически из `POSTGRES_HOST`/`POSTGRES_PORT`/
> `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` (см. `backend/database.py`). Поэтому
> достаточно задать либо `DATABASE_URL`, либо набор `POSTGRES_*` — дублировать не нужно.
- **Node 18+/npm** для фронтенда.

---

## 3. Установка «с нуля» (локальная разработка или новый VPS)

Ключевой принцип: **инициализация схемы — только через Alembic** (`alembic upgrade head`).
Отдельный `bootstrap_db.py` (raw `create_all`) для развёртывания **не нужен** — вся схема
воспроизводится ревизиями Alembic (включая масштабирующую ревизию `0002_schema_squash`).

```bash
# 1) Python-зависимости в виртуальном окружении
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt

# 2) Перейти в каталог backend — ВСЕ команды ниже выполняются из него
cd backend

# 3) СХЕМА БД — только Alembic (создаёт все таблицы + users + alembic_version)
alembic upgrade head

# 4) Системные справочники (типы тарифов, услуги, тарифы по умолчанию) — идемпотентно
python init_data.py

# 5) Создать администратора (пароль из ADMIN_PASSWORD или будет сгенерирован)
python create_user.py

# 6) Запуск API (локальная разработка — с авто-перезагрузкой)
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

> Скрипты бэкенда (`init_data.py`, `create_user.py`, `alembic`) выполняются строго из
> каталога `backend/` — так модули (`database`, `models`, `auth`) корректно попадают в
> `sys.path`. Отдельная передача `PYTHONPATH=backend` не требуется.
> `init_data.py` идемпотентен — создаёт только недостающие справочники.
> `create_user.py` выводит сгенерированный пароль один раз в консоль.

---

## 4. Фронтенд

```bash
cd frontend
npm install
# для локального dev:
echo "VITE_DEV_HOST=localhost" >> .env
npm run dev          # dev-сервер на http://localhost:5173
```

Production-сборка: `npm run build` (соберёт в `dist/`, статику отдаёт nginx).

---

## 5. Обновление уже развёрнутого окружения (VPS)

```bash
cd /opt/townhouse
git pull                       # забрать код и миграции
cd backend
alembic upgrade head            # применить новые миграции схемы
cd ..
# перезапустить сервис (см. пункт 7)
```

Новые файлы бэкенда используют установленные Python-зависимости; переустановка
`requirements.txt` нужна только если в нём изменились зависимости.

---

## 6. Тесты

```bash
cd backend && python -m pytest tests/ -q   # тесты бэкенда
cd frontend && npx tsc --noEmit             # проверка типов фронтенда
```

---

## 7. Запуск через Docker (опционально)

В корне проекта есть `docker-compose.yml`:

```bash
docker compose up -d --build
```

- `backend` читает окружение из `.env` (`env_file: .env`) и подключается к вашей Postgres.
- `frontend` — dev-сервер Vite с `VITE_API_URL`.

**Локально (нужна БД):** в `docker-compose.yml` раскомментируйте сервис `postgres`
(поднимет БД из `POSTGRES_*`). Тогда `docker compose up -d --build` создаст и БД, и сервисы.
На VPS сервис `postgres` закомментирован — там Postgres внешний.

Для продакшена бэкенд лучше запускать через systemd-юнит (uvicorn) + nginx,
а не dev-режимом.

---

## 8. Резервное копирование БД (дамп)

Дамп PostgreSQL хранится в **корне проекта** как файл `townhouse_db.sql.gz`.
Он содержит данные (включая чувствительные), поэтому **в git не коммитится**
(см. `.gitignore`). Используется для переноса локальной базы на VPS и обратно,
а также как точка восстановления.

Создать дамп (с параметрами подключения из `.env`, из корня проекта):

```bash
.venv/bin/python -c "from dotenv import load_dotenv;load_dotenv();import os;print(os.getenv('DATABASE_URL'))"
# затем:
pg_dump "$DATABASE_URL" | gzip > townhouse_db.sql.gz
```

Восстановить из дампа (пересоздав базу):

```bash
gunzip < townhouse_db.sql.gz | psql "$DATABASE_URL"
```

> Если `pg_dump`/`psql` недоступны в PATH, их можно взять из контейнера `postgres`
> (`docker exec -i <pg-container> pg_dump ...`). Точную схему/VARS удобно считывать через
> `DATABASE_URL` из `.env`.

---

## 9. Ключевые команды / скрипты

| Команда (из каталога backend) | Назначение |
|---|---|
| `alembic upgrade head` | Применить миграции Alembic (создание всей схемы с нуля — единственный канал) |
| `python init_data.py` | Системные справочники (типы тарифов, услуги, тарифы) |
| `python create_user.py` | Создать пользователя (пароль из env/случайный) |
| `python bootstrap_db.py` | **Только отладочный fallback** (raw `create_all`). Для развёртывания не нужен. |
| `python -m pytest tests/ -q` | Запустить тесты бэкенда |
| `uvicorn app:app --host 0.0.0.0 --port 8000` | Запустить API |
