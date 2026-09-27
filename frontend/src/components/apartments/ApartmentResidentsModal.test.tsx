// src/components/apartments/ApartmentResidentsModal.test.tsx
// RTL-тесты модалки «Жильцы квартиры» (Б8): загрузка списка жильцов квартиры
// (http.get с фильтром apartment_id), отрисовка строк (ФИО/статус/даты проживания),
// добавление (POST /apartment_residents), удаление через Popconfirm (DELETE .../:id),
// пустой список, режим «только чтение» (canEdit=false) и обработка ошибок (detail).
//
// Сеть не используется: модуль `../../auth/http` замокан фабрикой vi.mock — axios-инстанс
// заменён на vi.fn-заглушки. Refine-хуки компонент не использует, поэтому провайдер не нужен.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { http } from "../../auth/http";
import { ApartmentResidentsModal } from "./ApartmentResidentsModal";

vi.mock("../../auth/http", () => ({
    apiUrl: "/api",
    http: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        patch: vi.fn(),
        delete: vi.fn(),
    },
}));

const APARTMENT = { id: 10, apartment_number: 13 };

const RESIDENTS = [
    {
        id: 1,
        apartment_id: 10,
        full_name: "Иванов Иван Иванович",
        birth_date: "1980-05-12",
        role: "Собственник",
        date_from: "2020-01-01",
        date_to: null,
    },
    {
        id: 2,
        apartment_id: 10,
        full_name: "Петрова Мария",
        birth_date: null,
        role: "Проживающий",
        date_from: null,
        date_to: "2023-12-31",
    },
];

/** Рендер модалки с дефолтными пропсами; можно переопределить open/canEdit. */
const renderModal = (overrides: { open?: boolean; canEdit?: boolean } = {}) => {
    const onClose = vi.fn();
    render(
        <ApartmentResidentsModal
            open={overrides.open ?? true}
            apartment={APARTMENT}
            onClose={onClose}
            canEdit={overrides.canEdit ?? true}
        />,
    );
    return { onClose };
};

/** Кнопка-иконка удаления строки (DeleteOutlined). */
const deleteIconButton = (): HTMLButtonElement | null =>
    (document.querySelector(".anticon-delete")?.closest("button") as HTMLButtonElement) ?? null;

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(http.get).mockResolvedValue({ data: [] } as any);
    vi.mocked(http.post).mockResolvedValue({ data: { id: 99 } } as any);
    vi.mocked(http.delete).mockResolvedValue({ data: {} } as any);
});

afterEach(() => {
    vi.clearAllMocks();
});

describe("ApartmentResidentsModal — загрузка списка", () => {
    it("грузит жильцов квартиры (http.get с apartment_id) и рисует ФИО, статус и даты", async () => {
        vi.mocked(http.get).mockResolvedValue({ data: RESIDENTS } as any);

        renderModal();

        expect(await screen.findByText("Иванов Иван Иванович")).toBeTruthy();
        expect(vi.mocked(http.get)).toHaveBeenCalledWith(
            "/api/apartment_residents?_start=0&_end=200&_sort=id&_order=asc&apartment_id=10",
        );

        // Заголовок модалки содержит номер квартиры.
        expect(screen.getByText("Жильцы квартиры 13")).toBeTruthy();

        // Строки: ФИО и статус.
        expect(screen.getByText("Петрова Мария")).toBeTruthy();
        expect(screen.getByText("Собственник")).toBeTruthy();
        expect(screen.getAllByText("Проживающий").length).toBeGreaterThanOrEqual(1);

        // Даты форматируются как DD.MM.YYYY; для date_to=null — «по н.в.».
        expect(screen.getByText("12.05.1980")).toBeTruthy();
        expect(screen.getByText("01.01.2020")).toBeTruthy();
        expect(screen.getByText("31.12.2023")).toBeTruthy();
        expect(screen.getByText("по н.в.")).toBeTruthy();
        // Пустые birth_date/date_from у второй строки — прочерки.
        expect(screen.getAllByText("—").length).toBe(2);
    });

    it("пустой список показывает «Жильцы не заведены»", async () => {
        renderModal();
        expect(await screen.findByText("Жильцы не заведены")).toBeTruthy();
    });

    it("при open=false список не запрашивается", () => {
        renderModal({ open: false });
        expect(vi.mocked(http.get)).not.toHaveBeenCalled();
    });

    it("ошибка загрузки показывает detail из ответа", async () => {
        vi.mocked(http.get).mockRejectedValue({ response: { data: { detail: "Нет доступа к квартире" } } });

        renderModal();

        expect(await screen.findByText("Нет доступа к квартире")).toBeTruthy();
    });
});

describe("ApartmentResidentsModal — добавление жильца", () => {
    it("«Добавить» шлёт POST с телом (apartment_id, full_name, роль по умолчанию)", async () => {
        renderModal();
        await screen.findByText("Жильцы не заведены");

        fireEvent.change(screen.getByPlaceholderText("ФИО"), { target: { value: "Сидоров Пётр" } });
        fireEvent.click(screen.getByRole("button", { name: /Добавить/u }));

        await waitFor(() =>
            expect(vi.mocked(http.post)).toHaveBeenCalledWith(
                "/api/apartment_residents",
                expect.objectContaining({
                    apartment_id: 10,
                    full_name: "Сидоров Пётр",
                    role: "Проживающий",
                }),
            ),
        );
        expect(await screen.findByText("Жилец добавлен")).toBeTruthy();
    });

    it("ошибка добавления показывает detail из ответа", async () => {
        vi.mocked(http.post).mockRejectedValue({ response: { data: { detail: "Квартира не найдена" } } });

        renderModal();
        await screen.findByText("Жильцы не заведены");

        fireEvent.change(screen.getByPlaceholderText("ФИО"), { target: { value: "Сидоров Пётр" } });
        fireEvent.click(screen.getByRole("button", { name: /Добавить/u }));

        expect(await screen.findByText("Квартира не найдена")).toBeTruthy();
    });

    it("пустое ФИО: форма не отправляется и не валится (ошибки валидации у полей, без unhandled rejection)", async () => {
        renderModal();
        await screen.findByText("Жильцы не заведены");

        fireEvent.click(screen.getByRole("button", { name: /Добавить/u }));

        // antd подсвечивает ошибку у поля, а POST не уходит.
        expect(await screen.findByText("Укажите ФИО")).toBeTruthy();
        expect(vi.mocked(http.post)).not.toHaveBeenCalled();
    });
});

describe("ApartmentResidentsModal — удаление жильца", () => {
    it("Popconfirm подтверждает удаление и шлёт DELETE /apartment_residents/:id", async () => {
        vi.mocked(http.get).mockResolvedValue({ data: RESIDENTS } as any);

        renderModal();
        await screen.findByText("Иванов Иван Иванович");

        fireEvent.click(deleteIconButton() as HTMLButtonElement);
        expect(await screen.findByText("Удалить запись о жильце?")).toBeTruthy();

        fireEvent.click(screen.getByRole("button", { name: "OK" }));

        await waitFor(() =>
            expect(vi.mocked(http.delete)).toHaveBeenCalledWith("/api/apartment_residents/1"),
        );
        expect(await screen.findByText("Запись удалена")).toBeTruthy();
    });

    it("ошибка удаления показывает detail из ответа", async () => {
        vi.mocked(http.get).mockResolvedValue({ data: RESIDENTS } as any);
        vi.mocked(http.delete).mockRejectedValue({ response: { data: { detail: "Запись уже удалена" } } });

        renderModal();
        await screen.findByText("Иванов Иван Иванович");

        fireEvent.click(deleteIconButton() as HTMLButtonElement);
        await screen.findByText("Удалить запись о жильце?");
        fireEvent.click(screen.getByRole("button", { name: "OK" }));

        expect(await screen.findByText("Запись уже удалена")).toBeTruthy();
    });
});

describe("ApartmentResidentsModal — режим только для чтения", () => {
    it("canEdit=false скрывает форму добавления и колонку действий", async () => {
        vi.mocked(http.get).mockResolvedValue({ data: RESIDENTS } as any);

        renderModal({ canEdit: false });
        await screen.findByText("Иванов Иван Иванович");

        expect(screen.queryByText("Добавить жильца")).toBeNull();
        expect(screen.queryByPlaceholderText("ФИО")).toBeNull();
        expect(screen.queryByRole("button", { name: /Добавить/u })).toBeNull();
        expect(deleteIconButton()).toBeNull();
    });
});
