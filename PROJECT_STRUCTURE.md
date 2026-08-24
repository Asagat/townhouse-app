Вот обновленный файл `PROJECT_STRUCTURE.md` со всеми замечаниями:

---

# Структура проекта Townhouse Frontend

## Обзор
Проект представляет собой SPA (Single Page Application) для управления жилищно-коммунальным хозяйством. Разработан на React с использованием Refine framework.

## Технологический стек
- **React 18** - библиотека для построения пользовательских интерфейсов
- **Refine** - фреймворк для CRUD-приложений
- **React Router v6** - маршрутизация в приложении
- **Ant Design** - библиотека компонентов UI
- **TypeScript** - типизированный JavaScript
- **Vite** - сборщик и dev-сервер
- **Docker** - контейнеризация приложения
- **dayjs** - работа с датами и временем

---

## 📁 Структура папок и файлов

### Корневая директория: `src/`

```
src/
├── App.tsx                    # Главный компонент, роутинг, провайдеры
├── main.tsx                   # Точка входа, монтирование React
│
├── components/                # Переиспользуемые компоненты
│   ├── common/               # Общие компоненты для всего приложения
│   │   ├── RecordFormModal.tsx      # Модалка создания/редактирования
│   │   ├── ReferenceSelect.tsx      # Выбор из справочников (FK)
│   │   └── renderFieldControl.tsx   # Рендер полей формы
│   │
│   ├── layout/               # Компоненты макета
│   │   ├── Sidebar.tsx               # Главное боковое меню
│   │   ├── SidebarHeader.tsx         # Шапка сайдбара
│   │   ├── SidebarExpandedCategory.tsx # Раскрытая категория
│   │   └── SidebarCollapsedCategory.tsx # Свернутая категория
│   │
│   ├── meter-readings/       # Компоненты для показаний счетчиков
│   │   └── BulkReadingsModal.tsx     # Массовый ввод показаний
│   │
│   └── accruals/             # Компоненты для начислений
│       └── AccrualsCalculationModal.tsx # Расчет и начисление услуг
│
├── config/                   # Конфигурационные файлы
│   ├── columns.ts           # Конфигурация колонок таблиц
│   ├── formatters.ts        # Функции форматирования данных
│   ├── menu.ts              # Конфигурация меню и ресурсов
│   └── colors.ts            # Цветовая схема приложения
│
├── pages/                    # Страницы приложения
│   └── GenericList.tsx      # Универсальная страница списка
│
├── types/                    # TypeScript типы
│   └── index.ts             # Глобальные типы данных
│
└── hooks/                    # Кастомные хуки
    └── useSidebarState.ts   # Управление состоянием сайдбара
```

---

## 🔐 Переменные окружения

Файл `.env` в корне проекта содержит переменные окружения:

```bash
# URL бэкенда для API запросов
VITE_API_URL=/api

# Другие переменные могут быть добавлены по необходимости
```

**Важно:** 
- Переменные должны начинаться с `VITE_` для доступа в клиентском коде
- Используются через `import.meta.env.VITE_*`

---

## 📄 Описание ключевых файлов

### 1. `App.tsx` - Главный компонент (~50 строк)

**Что делает:**
- Настраивает провайдеров (ConfigProvider, Refine, Router)
- Определяет маршруты приложения
- Отрисовывает общий макет (Sidebar + Content)

**Ключевые особенности:**
```typescript
// Минималистичный, только роутинг и провайдеры
<Refine dataProvider={dataProvider("/api")}>
    <Routes>
        <Route path="/:resource" element={<GenericList />} />
    </Routes>
</Refine>
```

---

### 2. `pages/GenericList.tsx` - Универсальная страница (~200 строк)

**Что делает:**
- Отображает таблицу с данными для любого ресурса
- Обрабатывает CRUD операции (Create, Read, Update, Delete)
- Управляет модальными окнами
- Интегрируется с метаданными бэкенда

**Ключевые особенности:**
- Динамически строит таблицу на основе конфигурации
- Поддерживает массовый ввод показаний
- Поддерживает расчет начислений

---

### 3. `config/columns.ts` - Конфигурация колонок

**Что делает:**
- Определяет колонки для каждого ресурса
- Применяет форматтеры к данным
- Предоставляет утилиты для работы с колонками

**Пример конфигурации:**
```typescript
export const columnsConfig: Record<string, Column[]> = {
    apartments: [
        { key: 'apartment_number', label: '№ квартиры' },
        { key: 'square', label: 'Площадь, м²', format: formatNumber },
    ],
    // ...
};
```

---

### 4. `config/formatters.ts` - Форматтеры данных

**Что делает:**
- Форматирует даты, числа, булевы значения
- Единое место для всех форматов
- Используется во всем приложении

**Доступные форматтеры:**
- `formatDate` - ДД.ММ.ГГГГ
- `formatDateTime` - ДД.ММ.ГГГГ ЧЧ:ММ:СС
- `formatNumber` - 1 234 567
- `formatBool` - Да/Нет
- `formatPrice` - 1 234 567 ₸

---

### 5. `components/common/RecordFormModal.tsx` - Модалка CRUD

**Что делает:**
- Динамически строит форму на основе метаданных
- Поддерживает все типы полей (текст, число, дата, enum, reference)
- Обрабатывает отправку данных

**Поддерживаемые типы:**
- `text` - текстовое поле
- `integer` - число без дробной части
- `decimal` - число с дробной частью
- `date` - выбор даты
- `boolean` - переключатель
- `enum` - выпадающий список
- `reference` - выбор из справочника

---

### 6. `components/common/ReferenceSelect.tsx` - Выбор справочников

**Что делает:**
- Загружает данные из справочника
- Форматирует отображение записей
- Поддерживает поиск

**Примеры форматтеров:**
```typescript
owners: (item) => item.full_name
apartments: (item) => `№ ${item.apartment_number} — ${item.owner?.full_name}`
accounts: (item) => `${item.account_number} (${item.account_name})`
```

---

### 7. `components/meter-readings/BulkReadingsModal.tsx`

**Что делает:**
- Массовый ввод показаний счетчиков
- Показывает список всех квартир
- Позволяет вводить показания для каждой квартиры
- Автоматически проверяет ошибки

**Бизнес-логика:**
1. Оператор выбирает вид услуги (вода, свет, газ)
2. Выбирает дату показания
3. Вводит показания напротив каждой квартиры
4. Пустые строки пропускаются
5. Ошибки показываются в таблице

---

### 8. `components/accruals/AccrualsCalculationModal.tsx`

**Что делает:**
- Расчет начислений за период
- Предварительный просмотр
- Выборочное сохранение

**Бизнес-логика:**
1. Оператор выбирает месяц/год
2. Система рассчитывает начисления по всем счетам
3. Отображается таблица с предварительными строками
4. Оператор выбирает строки для сохранения
5. Выбранные строки сохраняются в регистр

---

### 9. `types/index.ts` - Глобальные типы

**Основные типы:**
```typescript
// Колонка таблицы
type Column = { key: string; label: string; format?: Function }

// Метаданные поля
type FieldMeta = { name: string; label: string; type: string; required: boolean }

// Состояние модалки
type ModalState = { mode: 'create' | 'edit'; record?: any }

// Строка начислений
type AccrualPreviewRow = { row_number: number; amount: number; /* ... */ }
```

---

## 🔄 Поток данных

### 1. Загрузка списка
```
Пользователь открывает страницу
    ↓
GenericList → useTable() → API запрос
    ↓
Получение данных + метаданных
    ↓
Отображение таблицы
```

### 2. Создание записи
```
Пользователь нажимает "Добавить"
    ↓
RecordFormModal → поля из метаданных
    ↓
Пользователь заполняет форму
    ↓
useCreate() → POST /api/{resource}
    ↓
Обновление таблицы
```

### 3. Массовый ввод показаний
```
Пользователь открывает модалку
    ↓
BulkReadingsModal → загрузка квартир
    ↓
Пользователь вводит показания
    ↓
POST /api/meter_readings/bulk
    ↓
Обработка ошибок и успех
```

### 4. Расчет начислений
```
Пользователь выбирает период
    ↓
GET /api/accruals_register/calculate
    ↓
Отображение предварительных строк
    ↓
Пользователь выбирает строки
    ↓
POST /api/accruals_register/generate
    ↓
Сохранение в регистр
```

---

## 🎨 Особенности UI

### Типы полей в формах:

| Тип | Компонент | Пример |
|-----|-----------|--------|
| `text` | TextArea | Примечание |
| `string` | Input | Название |
| `integer` | InputNumber | Количество |
| `decimal` | InputNumber (step 0.01) | Сумма |
| `date` | DatePicker | Дата начисления |
| `boolean` | Switch | Активен |
| `enum` | Select | Тип операции |
| `reference` | ReferenceSelect | Лицевой счет |

### Форматирование в таблицах:

| Тип | Формат | Пример |
|-----|--------|--------|
| Дата | ДД.ММ.ГГГГ | 24.08.2026 |
| Дата+время | ДД.ММ.ГГГГ ЧЧ:ММ:СС | 24.08.2026 14:30:00 |
| Число | 1 234 567 | 1 234 567.50 |
| Булево | Да/Нет | Да |
| Цена | 1 234 567 ₸ | 1 234 567 ₸ |

---

## 🚀 Команды для разработки

### Запуск в Docker:
```bash
# Перезапуск фронтенда
docker compose restart frontend

# Просмотр логов
docker compose logs frontend --tail=30

# Полная пересборка
docker compose up -d --build frontend

# Просмотр логов в реальном времени
docker compose logs frontend -f
```

### Локальная разработка:
```bash
# Переход в папку фронтенда
cd /opt/townhouse/frontend

# Установка зависимостей
npm install

# Запуск dev-сервера
npm start

# Сборка для продакшена
npm run build

# Проверка TypeScript ошибок
npx tsc --noEmit

# Проверка линтером
npm run lint
```

---

## 📝 Соглашения по коду

### Именование файлов:
- Компоненты: `PascalCase.tsx` (RecordFormModal.tsx)
- Утилиты: `camelCase.ts` (formatters.ts)
- Конфигурация: `camelCase.ts` (columns.ts)
- Хуки: `useCamelCase.ts` (useSidebarState.ts)
- Типы: `index.ts` (в папке types)

### Именование компонентов:
- Компоненты: `PascalCase`
- Хуки: `useCamelCase`
- Пропсы: `PascalCaseProps` (RecordFormModalProps)
- Обработчики: `handleCamelCase` (handleSubmit)

### Структура компонента:
```typescript
// 1. Импорты (сначала сторонние, потом локальные)
import { useState } from "react";
import { Button } from "antd";
import { useApiUrl } from "@refinedev/core";
import { MyComponent } from "./MyComponent";

// 2. Интерфейсы/Типы
interface MyComponentProps {
    prop1: string;
    prop2?: number;
}

// 3. Компонент
export const MyComponent = ({ prop1, prop2 }: MyComponentProps) => {
    // Состояния
    const [state, setState] = useState();
    
    // Эффекты
    useEffect(() => {
        // ...
    }, []);
    
    // Обработчики
    const handleClick = () => {
        // ...
    };
    
    // Рендер
    return (
        <div>
            {/* JSX */}
        </div>
    );
};

// 4. Экспорт по умолчанию (если нужно)
export default MyComponent;
```

---

## 🔧 Расширение функциональности

### Добавление нового ресурса:
1. Добавить в `config/menu.ts`
2. Добавить колонки в `config/columns.ts`
3. Добавить форматтер в `config/formatters.ts` (если нужно)
4. Готово! GenericList автоматически поддержит новый ресурс

### Добавление нового типа поля:
1. Добавить тип в `types/index.ts` (FieldMeta.type)
2. Добавить обработку в `renderFieldControl.tsx`
3. Добавить обработку в `RecordFormModal.tsx`

### Добавление нового компонента:
1. Создать файл в соответствующей папке
2. Импортировать в нужный компонент
3. Добавить экспорт в index.ts папки (если есть)

---

## 🐛 Частые проблемы и решения

### Проблема: HMR не обновляется
```bash
# Очистка кеша Vite
rm -rf /opt/townhouse/frontend/node_modules/.vite
docker compose restart frontend
```

### Проблема: Ошибка импорта
```bash
# Проверка структуры файлов
find /opt/townhouse/frontend/src -name "*.tsx" -o -name "*.ts"

# Проверка путей в импортах
grep -r "from \"\./" /opt/townhouse/frontend/src/
```

### Проблема: Нет данных в таблице
```bash
# Проверка API
curl http://localhost:5173/api/{resource}

# Проверка логов
docker compose logs frontend --tail=50
docker compose logs backend --tail=50
```

### Проблема: TypeScript ошибки
```bash
# Проверка всех ошибок
npx tsc --noEmit

# Проверка конкретного файла
npx tsc --noEmit src/App.tsx
```

### Проблема: Конфликт зависимостей
```bash
# Удаление node_modules и переустановка
rm -rf node_modules package-lock.json
npm install
```

---

## 📚 Полезные ссылки

### Документация:
- [Refine Documentation](https://refine.dev/docs/)
- [Ant Design Components](https://ant.design/components/overview/)
- [React Router](https://reactrouter.com/en/main)
- [Vite](https://vitejs.dev/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)

### Инструменты:
- [React DevTools](https://react.dev/learn/react-developer-tools)
- [Vite Plugin Inspector](https://github.com/antfu/vite-plugin-inspect)

---

## 📊 Статистика проекта

### Файловая структура:
- **Всего файлов:** 18
- **Компонентов:** 10
- **Конфигураций:** 4
- **Типов:** 1
- **Хуков:** 1

### Размеры ключевых файлов:
| Файл | Строк | Назначение |
|------|-------|------------|
| App.tsx | ~50 | Главный компонент |
| GenericList.tsx | ~200 | Универсальная страница |
| RecordFormModal.tsx | ~80 | Модалка CRUD |
| BulkReadingsModal.tsx | ~150 | Массовый ввод |
| AccrualsCalculationModal.tsx | ~200 | Расчет начислений |

---

*Последнее обновление: Август 2026*

---

## 📝 Список изменений

| Дата | Изменение |
|------|-----------|
| Август 2026 | Создан документ |
| Август 2026 | Добавлен раздел "Переменные окружения" |
| Август 2026 | Добавлен раздел "Статистика проекта" |
| Август 2026 | Добавлены новые команды для разработки |
| Август 2026 | Обновлены соглашения по коду |
| Август 2026 | Добавлен formatPrice в форматтеры |
