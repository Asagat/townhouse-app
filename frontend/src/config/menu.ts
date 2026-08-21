// --- СТРУКТУРА МЕНЮ: соответствует разделам админ-панели (sqladmin) ---
export type ResourceItem = { key: string; label: string; icon: string };
export type Category = { title: string; items: ResourceItem[] };

export const categories: Category[] = [
    {
        title: "1. Операции",
        items: [
            {
              key: "payments",
              label: "Приход/Расход",
              icon: "fa-solid fa-exchange-alt",
            },

            {
              key: "meter_readings",
              label: "Показания",
              icon: "fa-solid fa-pen-to-square",
            },

            {
              key: "accruals_register",
              label: "Начисления",
              icon: "fa-solid fa-calculator",
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
              key: "accounts_register",
              label: "Регистр взаиморасчетов",
              icon: "fa-solid fa-book",
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
              key: "service_types",
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
