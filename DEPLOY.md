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

Никогда не коммитьте `.env`. Шаблон всех переменных — в `.env.example`.
Пароль администратора передаётся через `ADMIN_PASSWORD` (или генерируется случайно) — см. `backend/create_user.py`.

---

## 2. Развёртывание «с нуля» (локальная разработка или новый VPS)

Порядок для **свежей, пустой** БД:

```bash
# 1) Установка python-зависимостей (в каталоге с виртуальным окружением)
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt

# 2) Создание СХЕМЫ БД из моделей (идемпотентно, «create_all»)
python backend/bootstrap_db.py

# 3) Системные справочники (типы тарифов, услуги, тарифы по умолчанию) — идемпотентно
python backend/init_data.py

# 4) Применить Alembic-миграции (пользователи и последующие изменения)
cd backend && alembic upgrade head && cd ..

# 5) Создать администратора (пароль из ADMIN_PASSWORD или будет сгенерирован)
cd backend && python create_user.py && cd ..

# 6) Запуск API
cd backend && uvicorn app:app --host 0.0.0.0 --port 8000
```

> `bootstrap_db.py` создаёт только отсутствующие таблицы и безопасен на уже
> развёрнутой БД. `init_data.py` идемпотентен — создаёт только недостающие
> справочники. `alembic upgrade head` приводит схему к актуальному состоянию.

---

## 3. Фронтенд

```bash
cd frontend
npm install
# для локального dev:
echo "VITE_DEV_HOST=localhost" >> .env
npm run dev          # dev-сервер на http://localhost:5173
```

Production-сборка: `npm run build` (соберёт в `dist/`, статику отдаёт nginx).

---

## 4. Обновление уже развёрнутого окружения (VPS)

```bash
cd /opt/townhouse
git pull                  # забрать код и миграции
cd backend && alembic upgrade head   # применить новые миграции
# перезапустить сервис (см. ниже)
```

Новые файлы бэкенда в venv не требуют переустановки java-зависимостей, кроме
случаев изменения `requirements.txt` (тогда `pip install -r requirements.txt`).

---

## 5. Запуск через Docker (опционально)

В корне проекта используется `docker-compose.yml`:

```bash
docker compose up -d --build
```

- `backend` читает окружение из `.env` (`env_file: .env`) и подключается к вашей Postgres.
- `frontend` — dev-сервер Vite с `VITE_API_URL`.

Для продакшена бэкенд лучше запускать через systemd-юнит (uvicorn) + nginx,
а не dev-режимом.

---

## 6. Ключевые команды / скрипты

| Команда | Назначение |
|---|---|
| `backend/bootstrap_db.py` | Создать схему из моделей (create_all) |
| `backend/init_data.py` | Системные справочники (типы тарифов, услуги, тарифы) |
| `backend/create_user.py` | Создать пользователя (пароль из env/cлучайный) |
| `alembic upgrade head` | Применить миграции Alembic |
| `cd backend && python -m pytest tests/ -q` | Запустить тесты бэкенда |
| `cd frontend && npx tsc --noEmit` | Проверка типов фронтенда |
