// frontend/src/config/menu.ts
export type ResourceItem = { key: string; label: string; icon: string };
export type Category = { title: string; items: ResourceItem[] };

export const categories: Category[] = [
    {
        title: "1. Документы",
        items: [
            {
              key: "payments",
              label: "Приход/Расход",
              icon: "fa-solid fa-exchange-alt",
            },
            {
              key: 'accrual_documents',
              label: 'Начисления',
              icon: 'fa-solid fa-file-invoice',
            },
            {
              key: 'meter_reading_documents',
              label: 'Документы показаний',
              icon: 'fa-solid fa-file-pen',
            },
        ],
    },
    {
        title: "2. Справочники",
        items: [
            {
              key: "tariffs",
              label: "Тарифы",
              icon: "fa-solid fa-money-bill-wave",
            },
            {
              key: "cash_points",
              label: "Кассы/Счета",
              icon: "fa-solid fa-vault"
            },
            {
              key: "owners",
              label: "Контрагенты",
              icon: "fa-solid fa-user",
            },
            {
              key: "apartments",
              label: "Квартиры",
              icon: "fa-solid fa-house",
            },
            {
              key: "accounts",
              label: "Лицевые счета",
              icon: "fa-solid fa-file-invoice-dollar",
            },
        ],
    },
    {
        title: "3. Регистры",
        items: [
            {
              key: "meter_readings",
              label: "Регистр показаний",
              icon: "fa-solid fa-table",
            },
            {
              key: "accounts_register",
              label: "Регистр взаиморасчетов",
              icon: "fa-solid fa-book",
            },
            {
              key: "accruals_register",
              label: "Регистр начислений",
              icon: "fa-solid fa-calculator",
            },
        ],
    },
    {
        title: "4. Настройки",
        items: [
          {
            key: "tariff_types",
            label: "Типы тарифов",
            icon: "fa-solid fa-tags",
            },
            {
              key: "services_type",
              label: "Виды услуг",
              icon: "fa-solid fa-list-check",
            },
            {
              key: "meters",
              label: "Счетчики",
              icon: "fa-solid fa-gauge-high",
            },
        ],
    },
];

export const allResources = categories.flatMap((c) => c.items);
