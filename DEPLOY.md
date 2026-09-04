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
- `create_user.py` **идемпотентен**: повторный запуск не ошибка — он обновляет пароль (и роль/имя)
  существующего пользователя на актуальный. Это удобно при многократном развёртывании.

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

### 3.0. Новый VPS (чистый сервер) — автоматически

Для **нового** сервера (Ubuntu/Debian, ничего ещё не стоит) есть готовый скрипт
[`scripts/setup_vps.sh`](scripts/setup_vps.sh): он ставит системные пакеты, клонирует
репозиторий, делает venv/зависимости, `.env`, схему/справочники/админа, systemd-юнит
бэкенда и production-сборку фронтенда. Останется только nginx + DNS (подсказки скрипт
печатает в конце).

```bash
# на новом сервере, от root/sudo:
sudo bash -c 'curl -fsSL -o /tmp/setup_vps.sh https://raw.githubusercontent.com/Asagat/townhouse-app/main/scripts/setup_vps.sh && bash /tmp/setup_vps.sh'
# или — предварительно скопировать репо и:
bash scripts/setup_vps.sh
```

> Перед первым успешным прогоном отредактируйте созданный `.env` (БД, пароли, CORS).

### 3.1. Ручные действия — подробная инструкция (после установки на новом VPS)

После `setup_vps.sh` остаются шаги, которые нельзя автоматизировать полностью
(требуют вашего ввода: домен, реквизиты СУБД, DNS). По шагам:

#### 1) Создать базу данных и пользователя PostgreSQL

Если Postgres ещё не установлен/не создана база — выполните от root:

```bash
apt-get install -y postgresql
systemctl enable --now postgresql
```

Затем от пользователя `postgres` создайте роль и БД. Имена возьмите те же, что указаны
в `.env` (`POSTGRES_USER` / `POSTGRES_DB` / `POSTGRES_PASSWORD`):

```bash
sudo -u postgres psql <<'SQL'
CREATE USER townhouse_user WITH PASSWORD 'сложный-пароль';
-- ВАЖНО: DB должна быть UTF8, а НЕ SQL_ASCII (по умолчанию на кластере с локалью C).
-- При SQL_ASCII кириллица в справочниках/документах приведёт к
-- UnicodeEncodeError: 'ascii' codec can't encode ... при psycopg2.
CREATE DATABASE townhouse OWNER townhouse_user ENCODING 'UTF8' LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8' TEMPLATE template0;
SQL
```

Если база уже создана без `ENCODING 'UTF8'` (т.е. в `SQL_ASCII`) — кодировку БД нельзя изменить
на лету: пересоздайте её (данные тестовые можно сбросить):

```bash
sudo -u postgres psql <<'SQL'
DROP DATABASE IF EXISTS townhouse;
CREATE DATABASE townhouse OWNER townhouse_user ENCODING 'UTF8' LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8' TEMPLATE template0;
SQL
```

Проверка кодировки:
```bash
sudo -u postgres psql -d townhouse -c "SHOW server_encoding;"   # должно быть UTF8
```

Убедитесь, что в `.env` установлено:
```ini
POSTGRES_USER=townhouse_user
POSTGRES_PASSWORD=сложный-пароль
POSTGRES_DB=townhouse
POSTGRES_HOST=127.0.0.1   # или IP сервера БД
POSTGRES_PORT=5432
```

> Если строка `.env` задана через `DATABASE_URL=postgresql://...`, не дублируйте —
> хватает либо `DATABASE_URL`, либо набора `POSTGRES_*`.

#### 2) Проверить подключение к БД и повторно прогнать установку

Повторный запуск `setup_vps.sh` **идемпотентен** (не сломает готовые части):

```bash
bash scripts/setup_vps.sh
```

Он создаст схему (Alembic), справочники и админа, запустит systemd-юнит.

#### 3) Проверить, что бэкенд поднялся

```bash
systemctl status townhouse-backend
curl -s http://127.0.0.1:8000/openapi.json | head -c 200   # схема API (HTTP 200) — сервис поднялся

> Примечание: эндпоинта `/health` в коде нет — 404 на нём не является признаком проблемы.
```

Если сервис не встал — смотрите логи:
```bash
journalctl -u townhouse-backend -n 50 --no-pager
```

#### 4) Настроить nginx

Из шаблона `deploy/nginx.conf.template` создайте конфиг, заменив `__DOMAIN__`
и `__APP_DIR__`:

```bash
sed -e 's|__DOMAIN__|ваш-домен.example|' \
    -e 's|__APP_DIR__|/opt/townhouse|' \
    deploy/nginx.conf.template \
    > /etc/nginx/sites-available/townhouse

ln -s /etc/nginx/sites-available/townhouse /etc/nginx/sites-enabled/townhouse
nginx -t
systemctl reload nginx
```

Шаблон обрабатывает:
- `location /api/` → прокси на `127.0.0.1:8000` (бэкенд);
- `location /` → отдаёт статику SPA из `frontend/dist`;
- заголовки `X-Real-IP`/`X-Forwarded-*` для корректного логирования и CORS.

> В dev-режиме, если фронт на Vite (`:5173`), в шаблоне раскомментируйте
> `location / { proxy_pass http://127.0.0.1:5173; }` вместо статики.

#### 5) DNS-запись

На ваш DNS-провайдер добавьте A/AAAA-запись:

```text
townhouse.sagacloud.kz.   IN   A   <IP-вашего-VPS>
```

Проверка:
```bash
dig townhouse.sagacloud.kz +short
# должно вернуть IP сервера
```

#### 6) HTTPS (рекомендуется)

Установите TLS через Let's Encrypt / certbot:

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d townhouse.sagacloud.kz
# certbot самостоятельно пропишет SSL в nginx и настроит продление
```

#### 7) Администратор и первичные данные

Администратор создаётся автоматически скриптом (`create_user.py`). Если нужно
обновить его пароль — повторно из `backend/`:

```bash
cd /opt/townhouse/backend
ADMIN_PASSWORD='новый-пароль' ../.venv/bin/python create_user.py
systemctl restart townhouse-backend
```

#### 8) Секреты и прод-безопасность

- `AUTH_SECRET_KEY` обязательно замените на случайный (лог предупредит, если не задан):
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- `CORS_ORIGINS` оставьте свой домен, уберите лишние `localhost`-значения при необходимости.
- Пароль админа / строка БД не должны попадать в git (`.env` — в `.gitignore`).

### 3.2. Ручная установка (без скриптов, как альтернатива)

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
> `create_user.py` создаёт пользователя, а при повторном запуске обновляет его пароль
> (идемпотентно); сгенерированный пароль печатается один раз в консоль.

---

## 4. Фронтенд

```bash
cd frontend
npm install
npm run dev          # dev-сервер на http://localhost:5173
```

- **`frontend/.env` создаётся автоматически**: скрипт `predev` (`ensure-env`) копирует
  `frontend/.env.example` в `frontend/.env`, если его ещё нет. Явно создавать `.env` не обязательно.
- **Dev-прокси по умолчанию**: `vite.config.ts` переадресует запросы `/api` на бэкенд
  (`VITE_PROXY_TARGET`, по умолчанию `http://localhost:8000`). Поэтому локально внешний
  адрес/CORS для бэкенда не нужны — фронтенд на :5173 сам проксирует запросы.
- Локальные переменные уточняйте в `frontend/.env`: `VITE_PROXY_TARGET`, `VITE_DEV_HOST=localhost`,
  `VITE_DEV_PORT`.

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

> **Рекомендуемый способ — скрипты (см. `scripts/`):**
>
> ```bash
> # Локальная разработка (venv, alembic, справочники, админ, uvicorn --reload):
> ./scripts/dev.sh
> # --full — дополнительно pip install по requirements.txt.
>
> # Обновление VPS (git pull, alembic, справочники, админ, restart сервиса):
> ./scripts/deploy_vps.sh
> ```
>
> Для надёжного запуска бэкенда на VPS используйте systemd-юнит
> `deploy/townhouse-backend.service` (управляет uvicorn без `--reload`):
>
> ```bash
> cp deploy/townhouse-backend.service /etc/systemd/system/
> systemctl daemon-reload
> systemctl enable --now townhouse-backend
> ```

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
- `frontend` — dev-сервер Vite (проксирует `/api` на бэкенд через `VITE_PROXY_TARGET`).

**Локально (нужна БД):** в `docker-compose.yml` раскомментируйте сервис `postgres`
(поднимет БД из `POSTGRES_*`). Тогда `docker compose up -d --build` создаст и БД, и сервисы.
На VPS сервис `postgres` закомментирован — там Postgres внешний.

Для продакшена бэкенд лучше запускать через systemd-юнит (uvicorn) + nginx,
а не dev-режимом.

---

## 8. Резервное копирование БД (дамп)

Дамп PostgreSQL хранится в **корне проекта** как файл `townhouse_db.sql.gz` (удобно для переноса локаль↔VPS).
Данные (включая чувствительные) **в git не коммитятся** (см. `.gitignore`).

Создать дамп (используется DATABASE_URL из `.env`):

```bash
.venv/bin/python -c "from dotenv import load_dotenv;load_dotenv();import os;print(os.getenv('DATABASE_URL'))"
# затем:
pg_dump "$DATABASE_URL" | gzip > townhouse_db.sql.gz
```

> Если `pg_dump`/`psql` недоступны в PATH, их можно взять из контейнера `postgres`:
> `docker exec -i <pg-container> pg_dump -U townhouse_user -d townhouse -Fc - | cat > townhouse_db.dump`.
> Точные значения VARS удобно считывать через `DATABASE_URL` из `.env`.

### 8.1 Дамп штатного состояния (полный + роли) для переноса на другой ПК

Для копии проекта на другой машине снимите **полный plain-SQL дамп данных** и отдельно **роли/пользователей**:

```bash
cd townhouse-app
mkdir -p backend/backups
STAMP=$(date +%Y%m%d_%H%M%S)

# (а) полный дамп БД townhouse: схема + данные, без владельцев/привилегий
docker exec townhouse-postgres sh -c \
  'PGPASSWORD=... pg_dump -U townhouse_user -d townhouse --no-owner --no-privileges' \
  > "backend/backups/townhouse_${STAMP}.sql"

# (б) роли/пользователи кластера (отдельно от данных)
docker exec townhouse-postgres sh -c \
  'PGPASSWORD=... pg_dumpall --roles-only -U townhouse_user' \
  > "backend/backups/townhouse_roles_${STAMP}.sql"
```

На каждом ПК забираете вместе: и сам проект (`townhouse-app/`), и эти два файла.

### 8.2 Восстановление БД

Есть готовый скрипт: **`scripts/restore_townhouse.sh`** (параметры подключения берёт из `.env`). Убедитесь, что postgres-контейнер запущен (`docker compose ps postgres`).

```bash
# поднять сервисы (если не подняты)
docker compose up -d postgres backend frontend

# (1) восстановить данные (пример: --fresh стирает и пересоздаёт DB)
./scripts/restore_townhouse.sh data --fresh backend/backups/townhouse_YYYYMMDD_HHMMSS.sql

# (2) применить роли/пользователей (первый запуск на новом сервере / если юзер отсутствует)
./scripts/restore_townhouse.sh roles backend/backups/townhouse_roles_YYYYMMDD_HHMMSS.sql
#    ВАЖНО: на Docker-базе, где пользователь уже создан при старте из .env, роли можно НЕ применять,
#    либо использовать --force, чтобы пересоздать роли из дампа.

# (3) перезапустить приложение, чтобы оно подключилось к восстановленным данным
docker restart townhouse-backend townhouse-frontend
```

Вручную то же самое (без скрипта):

```bash
# пересоздать чистую DB и залить
PGPASSWORD=... docker exec -i townhouse-postgres psql -U townhouse_user -d postgres -v ON_ERROR_STOP=1 \
  -c 'DROP DATABASE IF EXISTS townhouse' -c 'CREATE DATABASE townhouse OWNER townhouse_user'
PGPASSWORD=... docker exec -i townhouse-postgres psql -U townhouse_user -d townhouse -v ON_ERROR_STOP=1 \
  < backend/backups/townhouse_YYYYMMDD_HHMMSS.sql
# роли (одноразово) при необходимости
PGPASSWORD=... docker exec -i townhouse-postgres psql -U townhouse_user -d postgres \
  < backend/backups/townhouse_roles_YYYYMMDD_HHMMSS.sql
```

**Замечания:**
- Датамп содержит схему (`CREATE TABLE`) и **не удаляет** существующие объекты — поэтому восстановление лучше делать в **свежую/пересозданную** БД (см. `--fresh`), иначе возможны конфликты существующих таблиц.
- Перед `DROP DATABASE` остановите или отключите backend, иначе сессия удержит базу (скрипт сам гасит активные сессии).
- Дампы `backend/backups/townhouse_*.sql` — рабочие, актуальные снимки; при желании добавьте их паттерн в `.gitignore` (данные чувствительны).

---

## 9. Ключевые команды / скрипты

| Команда (из каталога backend) | Назначение |
|---|---|
| `alembic upgrade head` | Применить миграции Alembic (создание всей схемы с нуля — единственный канал) |
| `python init_data.py` | Системные справочники (типы тарифов, услуги, тарифы) — идемпотентно |
| `python create_user.py` | Создать/обновить пользователя (пароль из env/случайный; повторный запуск обновляет пароль) |
| `python bootstrap_db.py` | **Только отладочный fallback** (raw `create_all`). Для развёртывания не нужен. |
| `python -m pytest tests/ -q` | Запустить тесты бэкенда |
| `uvicorn app:app --host 0.0.0.0 --port 8000` | Запустить API |
| `npm run dev` (в `frontend/`) | Dev-сервер Vite (автосоздаёт `frontend/.env`, проксирует `/api`) |
| `./scripts/dev.sh` | Локальное развёртывание + запуск uvicorn (`--full` — pip install) |
| `./scripts/setup_vps.sh` | Полная установка на НОВОМ VPS (пакеты, clone, .env, БД, systemd, build) |
| `./scripts/deploy_vps.sh` | Обновление VPS (pull, alembic, справочники, админ, restart) |
| `./scripts/restore_townhouse.sh` | Восстановление БД из дампов (см. §8.2): `data [--fresh] <файл.sql>`, `roles [--force] <файл.sql>`, `all ...` |
