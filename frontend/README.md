# Townhouse — Frontend

SPA-клиент управления ЖКХ на **React 18 + Refine + Vite + TypeScript + Ant Design**.

## Быстрый старт

```bash
npm install        # установить зависимости
npm run dev        # dev-сервер Vite (по умолчанию http://localhost:5173)
npm run build      # проверка типов (tsc) + production-сборка в dist/
npm run preview    # локальный предпросмотр production-сборки
```

Перед `dev` есть скрипт `ensure-env`: если нет `frontend/.env`,
создаётся копия из `frontend/.env.example`.

## Структура `src/`

- `main.tsx`, `App.tsx` — точка входа, провайдеры Refine и маршрутизация.
- `pages/` — страницы: `GenericList.tsx` (универсальный CRUD-список),
  кабинеты, отчёты, `Login.tsx`, `Users.tsx`.
- `components/` — переиспользуемые компоненты (`common/`, `layout/`,
  предметные: `accruals/`, `meter-readings/`, `receipts/`, `writeoffs/`,
  `cabinet/`).
- `config/` — конфигурация колонок, фильтров, меню, форматтеров, цветов.
- `auth/` — провайдер авторизации Refine, проверка прав (`can.ts`), HTTP.
- `hooks/` — `useColumnSettings`, `useSidebarState`.
- `types/` — общие TypeScript-типы.

Подробнее об архитектуре и устройстве проекта — в корневом
[`PROJECT_STRUCTURE.md`](../PROJECT_STRUCTURE.md).
