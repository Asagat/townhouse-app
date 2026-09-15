# Демо-контур (автономная папка)

Показательная копия системы на NAS Synology: **отдельные** контейнеры, БД, volume,
сеть и секреты — прод-контур (`fth.sagacloud.synology.me`) и его данные не
затрагиваются. Публичный адрес демо — `demo.sagacloud.synology.me`.

Схема — проверенная 3-контейнерная (как в проде): `postgres` + `backend` (FastAPI) +
`frontend` (nginx: SPA + прокси `/api/`). Все данные в демо **вымышленные** и
генерируются скриптом `backend/migrations/seed_demo_data.py`.

## Состав папки

| Файл | Назначение |
|---|---|
| `docker-compose.demo.yml` | Стек демо-контура (префикс имён `townhouse-demo-*`, volume `townhouse_demo_pgdata`, сеть `townhouse_demo`) |
| `.env.demo.example` | Шаблон окружения (скопировать в `.env` и заполнить секреты) |
| `README.md` | Этот файл — порядок запуска |

## Первый запуск (на NAS, в каталоге проекта)

```bash
cd deploy/demo
cp .env.demo.example .env      # заполнить POSTGRES_PASSWORD / AUTH_SECRET_KEY / ADMIN_PASSWORD
# APP_PORT=8081, CORS_ORIGINS=https://demo.sagacloud.synology.me, TOWNHOUSE_TAG=<релиз>

docker compose -f docker-compose.demo.yml up -d
```

Дальше — разовые шаги внутри контейнера (схема, справочники, админ, демо-данные):

```bash
DC="docker compose -f docker-compose.demo.yml"

# 1) схема БД (миграции сами не накатываются — в образе только uvicorn)
$DC exec backend python -m alembic upgrade head

# 2) системные справочники (услуги, типы тарифов, статьи аналитики) — идемпотентно
$DC exec backend python init_data.py

# 3) администратор демо (пароль из ADMIN_PASSWORD) — ДО генерации: документы
#    получат корректные аудит-поля (created_by)
$DC exec backend python create_user.py

# 4) демонстрационные данные: сначала план (dry-run), затем генерация
$DC exec backend python migrations/seed_demo_data.py
$DC exec backend python migrations/seed_demo_data.py --apply
```

Открыть `http://<NAS>:8081` и войти администратором (`admin` / `ADMIN_PASSWORD`).

## Что создаёт генератор

10 собственников с казахстанскими ФИО (первый — «Мыркынбаева Мыркынбая»), квартиры
1–10, лицевые счёта `LS-0001…LS-0010`, счётчики, документы показаний, документы
начислений, квитанции, касса и производные регистры — весь путь «документ → регистр».
По умолчанию: **последние 3 завершённых месяца** (на дату запуска), детерминированный
seed; логины жителей **не создаются** (`--residents` не передаём — ЛК жителя
показывается из админки).

Период можно зафиксировать, если нужна неизменная картинка:
`--end 2026-08 --months 3 --seed 20260915`.

Генератор отказывается писать в непустую БД (печатает, что найдено) — чтобы демо не
смешалось с чем-то ещё.

## Сброс демо-данных

Пересоздать демонстрационный набор поверх текущего (очистив бизнес-данные):

```bash
docker compose -f docker-compose.demo.yml exec backend \
  python migrations/seed_demo_data.py --apply --wipe
```

`--wipe` удаляет только бизнес-данные и демо-жителей; справочники и пользователи-
сотрудники остаются.

## HTTPS и домен (Synology DSM)

«Панель управления → Вход → Обратный прокси»:

- источник: `demo.sagacloud.synology.me`, HTTPS `443`;
- назначение: `http://<NAS>:8081` (или localhost:8081 на самом NAS);
- сертификат — существующий DSM-сертификат для `*.sagacloud.synology.me`.

Ничего дополнительно настраивать в контейнерах не нужно: HTTPS терминирует DSM,
внутри остаётся HTTP (как в проде).

## Обновление версии

Выкат — **из CLI** (кнопки «Обновить» в Container Manager нет):

```bash
cd deploy/demo
docker compose -f docker-compose.demo.yml pull
docker compose -f docker-compose.demo.yml up -d
docker compose -f docker-compose.demo.yml exec backend python -m alembic upgrade head
```

> ⚠️ Не используйте «Очистить» в Container Manager — удаляются контейнеры проекта и
> может унести volume с данными БД.

## Важные технические заметки

- **Имена сервисов** в `docker-compose.demo.yml` — `postgres`, `backend`, `frontend` —
> менять нельзя: это DNS-имена, и nginx внутри образа фронтенда проксирует `/api/`
> на `backend:8000`. Префикс даётся только именам контейнеров/volume/сети.
- Демо-контур **не пересекается** с прод-контуром: контейнеры `townhouse-demo-*`,
  volume `townhouse_demo_pgdata`, сеть `townhouse_demo`, отдельные секреты.
- Прод-shell и демо-shell — разные: команды всегда через
  `docker compose -f deploy/demo/docker-compose.demo.yml`.
- Упрощение до 2 контейнеров (SPA отдаёт FastAPI, убрать nginx) — отдельная задача,
  см. `ROADMAP.md` (раздел «Технический долг»).
