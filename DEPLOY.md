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
- **PostgreSQL должен быть запущен** и доступен по `DATABASE_URL` из `.env` (хост, порт, пользователь, пароль, имя БД). Проверка подключения:
  ```bash
  python -c "import os;from dotenv import load_dotenv;load_dotenv();import psycopg2;psycopg2.connect(os.getenv('DATABASE_URL'));print('DB ok')"
  ```
  Если СУБД не запущена — запустите Postgres (или контейнер `docker run -d -e POSTGRES_PASSWORD=... postgres`) и создайте базу.
- **Node 18+/npm** для фронтенда.

---

## 3. Установка «с нуля» (локальная разработка или новый VPS)

Ключевой принцип: **инициализация схемы — только через Alembic** (`alembic upgrade head`).
Отдельный `bootstrap_db.py` (raw `create_all`) для развёртывания **не нужен** — вся схема
воспроизводится ревизиями Alembic (включая масштабирующую ревизию `0002_schema_squash`).

```bash
# 1) Python- зависимости в виртуальном окружении
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt

# 2) СХЕМА БД — только Alembic (создаёт все таблицы + users + alembic_version)
#    Выполняется ИЗ КАТАЛОГА backend (alembic.env.py добавляет backend в sys.path).
cd backend
alembic upgrade head
cd ..

# 3) Системные справочники (типы тарифов, услуги, тарифы по умолчанию) — идемпотентно
python backend/init_data.py

# 4) Создать администратора (пароль из ADMIN_PASSWORD или будет сгенерирован)
python backend/create_user.py

# 5) Запуск API (из backend/)
cd backend && uvicorn app:app --host 0.0.0.0 --port 8000
```

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

Для продакшена бэкенд лучше запускать через systemd-юнит (uvicorn) + nginx,
а не dev-режимом.

---

## 8. Ключевые команды / скрипты

| Команда (из каталога backend) | Назначение |
|---|---|
| `alembic upgrade head` | Применить миграции Alembic (создание всей схемы с нуля — единственный канал) |
| `python init_data.py` | Системные справочники (типы тарифов, услуги, тарифы) |
| `python create_user.py` | Создать пользователя (пароль из env/случайный) |
| `python bootstrap_db.py` | **Только отладочный fallback** (raw `create_all`). Для развёртывания не нужен. |
| `python -m pytest tests/ -q` | Запустить тесты бэкенда |
| `uvicorn app:app --host 0.0.0.0 --port 8000` | Запустить API |
