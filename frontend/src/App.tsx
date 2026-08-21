// --- App.tsx ---

import { useEffect, useState } from "react";
import {
    Refine,
    useTable,
    useCreate,
    useUpdate,
    useDelete,
    useList,
    useCustom,
    useCustomMutation,
    useApiUrl,
} from "@refinedev/core";
import dataProvider from "@refinedev/simple-rest";
import routerBindings, { NavigateToResource } from "@refinedev/react-router-v6";
import {
    BrowserRouter,
    Routes,
    Route,
    Outlet,
} from "react-router-dom";
import {
    ConfigProvider,
    Table,
    Button,
    Modal,
    Form,
    Input,
    InputNumber,
    DatePicker,
    Select,
    Switch,
    Popconfirm,
    Space,
    message,
    Checkbox,
} from "antd";
import ruRU from "antd/locale/ru_RU";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import "dayjs/locale/ru";
import "antd/dist/reset.css";
import { allResources } from "./config/menu";
import { Sidebar } from "./components/layout/Sidebar";

// Русская локализация dayjs (дни недели/месяцы в календаре DatePicker) и формат даты в полях ввода
dayjs.locale("ru");
const DATE_FORMAT = "DD.MM.YYYY";

// --- КОЛОНКИ ТАБЛИЦ ПО РЕСУРСАМ (для чтения/отображения) ---
type Column = { key: string; label: string; format?: (value: any) => string };

const formatDate = (v: any) => (v ? new Date(v).toLocaleDateString("ru-RU") : "—");
const formatDateTime = (v: any) =>
    v ? new Date(v).toLocaleString("ru-RU") : "—";
const formatNumber = (v: any) =>
    v != null ? Number(v).toLocaleString("ru-RU") : "—";
const formatBool = (v: any) => (v ? "Да" : "Нет");

const defaultColumns: Column[] = [
    { key: "full_name", label: "ФИО" },
    { key: "phone", label: "Телефон" },
];

const columnsConfig: Record<string, Column[]> = {
    apartments: [
        { key: "apartment_number", label: "№ квартиры" },
        { key: "address", label: "Адрес" },
        { key: "square", label: "Площадь, м²", format: formatNumber },
        { key: "owner_id_label", label: "Собственник" },
    ],
    accounts: [
        { key: "account_number", label: "№ счёта" },
        { key: "account_name", label: "Наименование" },
        { key: "is_active", label: "Активен", format: formatBool },
        { key: "apartment_id_label", label: "Квартира" },
    ],
    cash_points: [
        { key: "name", label: "Наименование" },
        { key: "is_active", label: "Активен", format: formatBool },
    ],
    payments: [
        { key: "transaction_date", label: "Дата", format: formatDateTime },
        { key: "apartment_id_label", label: "Квартира" },
        { key: "amount", label: "Сумма", format: formatNumber },
        { key: "transaction_type", label: "Тип операции" },
        { key: "account_label", label: "Лицевой счёт" },
        { key: "cash_point_id_label", label: "Касса/Счёт" },
        { key: "notes", label: "Примечание" },
    ],
    accruals_register: [
        { key: "accrual_date", label: "Дата начисления", format: formatDate },
        { key: "past_reading_value", label: "Показание прошлое", format: formatNumber },
        { key: "current_reading_value", label: "Показание текущее", format: formatNumber },
        { key: "consumption", label: "Потребление", format: formatNumber },
        { key: "amount", label: "Сумма", format: formatNumber },
        { key: "account_id_label", label: "Лицевой счёт" },
    ],
    accounts_register: [
        { key: "operation_date", label: "Дата операции", format: formatDateTime },
        { key: "income", label: "Приход", format: formatNumber },
        { key: "expense", label: "Расход", format: formatNumber },
        { key: "balance_after", label: "Баланс", format: formatNumber },
        { key: "account_id_label", label: "Лицевой счёт" },
    ],
    service_types: [{ key: "services_type", label: "Вид услуги" }],
    tariff_types: [{ key: "name", label: "Наименование" }],
    tariffs: [
        { key: "price", label: "Цена", format: formatNumber },
        { key: "unit", label: "Ед. изм." },
        { key: "valid_from", label: "Действует с", format: formatDate },
        { key: "services_type_id_label", label: "Вид услуги" },
        { key: "tariff_type_id_label", label: "Тип тарифа" },
    ],
    meters: [
        { key: "serial_number", label: "Серийный номер" },
        { key: "installed_at", label: "Дата установки", format: formatDate },
        { key: "apartment_id_label", label: "Квартира" },
        { key: "services_type_id_label", label: "Вид услуги" },
    ],
    meter_readings: [
        { key: "apartment_id_label", label: "Квартира" },
        { key: "services_type_id_label", label: "Вид услуги" },
        { key: "reading", label: "Показание", format: formatNumber },
        { key: "reading_date", label: "Дата показания", format: formatDate },
        { key: "meter_label", label: "Счётчик" },
    ],
};

// --- Как красиво подписать запись справочника внутри выпадающего списка (FK) ---
const referenceLabelFormatters: Record<string, (item: any) => string> = {
    owners: (item) => item.full_name ?? `#${item.id}`,
    apartments: (item) => `№ ${item.apartment_number} — ${item.owner?.full_name || "Без собственника"}`,
    accounts: (item) => `${item.account_number} (${item.account_name})`,
    cash_points: (item) => item.name,
    service_types: (item) => item.services_type,
    tariff_types: (item) => item.name,
    tariffs: (item) => `${item.price} ₸${item.unit ? " / " + item.unit : ""}`,
    meters: (item) => item.serial_number,
};

// --- МЕТАДАННЫЕ ПОЛЕЙ ФОРМЫ (получены с бэкенда через /api/meta/{resource}) ---
type FieldMeta = {
    name: string;
    label: string;
    type:
        | "string"
        | "text"
        | "integer"
        | "decimal"
        | "date"
        | "datetime"
        | "boolean"
        | "enum"
        | "reference";
    required: boolean;
    reference?: string;
    choices?: { value: string; label: string }[];
    default?: string | number | boolean;
};

// --- Выпадающий список для полей-ссылок (FK) ---
const ReferenceSelect = ({
    resource,
    value,
    onChange,
}: {
    resource: string;
    value?: number;
    onChange?: (value: number) => void;
}) => {
    const { data, isLoading } = useList({ resource, pagination: { mode: "off" } });
    const items = data?.data ?? [];
    const formatter =
        referenceLabelFormatters[resource] ??
        ((item: any) => item.full_name ?? item.name ?? `#${item.id}`);

    return (
        <Select
            showSearch
            allowClear
            loading={isLoading}
            value={value}
            onChange={onChange}
            filterOption={(input, option) =>
                (option?.label ?? "")
                    .toString()
                    .toLowerCase()
                    .includes(input.toLowerCase())
            }
            options={items.map((item: any) => ({
                value: item.id,
                label: formatter(item),  // <-- УБИРАЕМ `#${item.id} — `
            }))}
        />
    );
};

const renderFieldControl = (field: FieldMeta) => {
    switch (field.type) {
        case "text":
            return <Input.TextArea rows={3} />;
        case "integer":
            return <InputNumber style={{ width: "100%" }} precision={0} />;
        case "decimal":
            return <InputNumber style={{ width: "100%" }} step={0.01} />;
        case "boolean":
            return <Switch />;
        case "date":
            return <DatePicker style={{ width: "100%" }} format={DATE_FORMAT} />;
        case "enum":
            return (
                <Select
                    options={(field.choices ?? []).map((c) => ({
                        value: c.value,
                        label: c.label,
                    }))}
                />
            );
        case "reference":
            return <ReferenceSelect resource={field.reference!} />;
        default:
            return <Input />;
    }
};

// --- Модалка динамической формы (используется и для "Добавить", и для "Редактировать") ---
const RecordFormModal = ({
    open,
    title,
    fields,
    initialValues,
    confirmLoading,
    onCancel,
    onSubmit,
}: {
    open: boolean;
    title: string;
    fields: FieldMeta[];
    initialValues?: Record<string, any>;
    confirmLoading: boolean;
    onCancel: () => void;
    onSubmit: (values: Record<string, any>) => void;
}) => {
    const [form] = Form.useForm();

    useEffect(() => {
        if (!open) return;
        const prepared: Record<string, any> = {};
        fields.forEach((field) => {
            const raw = initialValues?.[field.name];

            if (field.type === "date") {
                if (raw) {
                    prepared[field.name] = dayjs(raw);
                } else if (field.default === "today") {
                    prepared[field.name] = dayjs();
                } else {
                    prepared[field.name] = undefined;
                }
            } else if (field.type === "boolean") {
                prepared[field.name] = raw ?? field.default ?? false;
            } else {
                prepared[field.name] = raw ?? field.default;
            }
        });
        form.resetFields();
        form.setFieldsValue(prepared);
    }, [open, initialValues, fields, form]);

    const handleOk = () => {
        form.validateFields().then((values) => {
            const payload: Record<string, any> = {};
            fields.forEach((field) => {
                const value = values[field.name];
                payload[field.name] =
                    field.type === "date" && value ? value.format("YYYY-MM-DD") : value;
            });
            onSubmit(payload);
        });
    };

    return (
        <Modal
            title={title}
            open={open}
            onCancel={onCancel}
            onOk={handleOk}
            confirmLoading={confirmLoading}
            okText="Сохранить"
            cancelText="Отмена"
            destroyOnClose
        >
            <Form form={form} layout="vertical">
                {fields.map((field) => (
                    <Form.Item
                        key={field.name}
                        name={field.name}
                        label={field.label}
                        valuePropName={field.type === "boolean" ? "checked" : "value"}
                        rules={
                            field.required
                                ? [{ required: true, message: `Поле «${field.label}» обязательно` }]
                                : []
                        }
                    >
                        {renderFieldControl(field)}
                    </Form.Item>
                ))}
            </Form>
        </Modal>
    );
};

type ModalState = { mode: "create" | "edit"; record?: Record<string, any> };

// --- МАССОВЫЙ ВВОД ПОКАЗАНИЙ ---
// Ответственный приносит оператору список снятых показаний по одному виду услуги:
// оператор выбирает вид услуги и дату один раз на всю партию,
// затем вводит показания напротив каждой квартиры (пустые строки пропускаются).
const BulkReadingsModal = ({
    open,
    onClose,
    onSaved,
}: {
    open: boolean;
    onClose: () => void;
    onSaved: () => void;
}) => {
    const apiUrl = useApiUrl();
    const { data: apartmentsData, isLoading: apartmentsLoading } = useList({
        resource: "apartments",
        pagination: { mode: "off" },
        sorters: [{ field: "apartment_number", order: "asc" }],
    });
    const { data: serviceTypesData } = useList({
        resource: "service_types",
        pagination: { mode: "off" },
    });

    const apartments = apartmentsData?.data ?? [];
    const serviceTypes = serviceTypesData?.data ?? [];

    const [serviceTypeId, setServiceTypeId] = useState<number | undefined>();
    const [readingDate, setReadingDate] = useState<Dayjs>(dayjs());
    const [readings, setReadings] = useState<Record<number, string>>({});
    const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

    const { mutate: bulkCreate, isLoading: saving } = useCustomMutation();

    useEffect(() => {
        if (open) {
            setServiceTypeId(undefined);
            setReadingDate(dayjs());
            setReadings({});
            setRowErrors({});
        }
    }, [open]);

    const handleSave = () => {
        if (!serviceTypeId) {
            message.error("Выберите вид услуги");
            return;
        }

        const entries = Object.entries(readings)
            .filter(([, value]) => value !== "" && value != null)
            .map(([apartmentId, value]) => ({
                apartment_id: Number(apartmentId),
                reading: Number(value),
            }));

        if (entries.length === 0) {
            message.error("Заполните хотя бы одно показание");
            return;
        }

        bulkCreate(
            {
                url: `${apiUrl}/meter_readings/bulk`,
                method: "post",
                values: {
                    services_type_id: serviceTypeId,
                    reading_date: readingDate.format("YYYY-MM-DD"),
                    entries,
                },
            },
            {
                onSuccess: (response) => {
                    const result: any = response.data;
                    const newRowErrors: Record<number, string> = {};
                    (result.errors ?? []).forEach((err: any) => {
                        newRowErrors[err.apartment_id] = err.detail;
                    });
                    setRowErrors(newRowErrors);

                    const createdCount = result.created?.length ?? 0;
                    const errorCount = result.errors?.length ?? 0;

                    if (createdCount > 0) {
                        message.success(`Сохранено показаний: ${createdCount}`);
                        onSaved();
                    }
                    if (errorCount > 0) {
                        message.warning(
                            `Не удалось сохранить: ${errorCount}. Ошибки показаны в таблице.`,
                        );
                    } else {
                        onClose();
                    }
                },
                onError: (err: any) =>
                    message.error(
                        err?.response?.data?.detail ?? "Не удалось сохранить показания",
                    ),
            },
        );
    };

    const columns = [
        {
            title: "№ квартиры",
            dataIndex: "apartment_number",
            key: "apartment_number",
            width: 110,
        },
        { title: "Адрес", dataIndex: "address", key: "address" },
        {
            title: "Показание",
            key: "reading",
            width: 220,
            render: (_: unknown, record: any) => (
                <div>
                    <InputNumber
                        style={{ width: "100%" }}
                        step={0.001}
                        value={
                            readings[record.id] !== undefined && readings[record.id] !== ""
                                ? Number(readings[record.id])
                                : undefined
                        }
                        status={rowErrors[record.id] ? "error" : undefined}
                        onChange={(value) => {
                            setReadings((prev) => ({
                                ...prev,
                                [record.id]: value === null ? "" : String(value),
                            }));
                            setRowErrors((prev) => {
                                if (!prev[record.id]) return prev;
                                const next = { ...prev };
                                delete next[record.id];
                                return next;
                            });
                        }}
                    />
                    {rowErrors[record.id] && (
                        <div style={{ color: "#ff4d4f", fontSize: 12, marginTop: 4 }}>
                            {rowErrors[record.id]}
                        </div>
                    )}
                </div>
            ),
        },
    ];

    return (
        <Modal
            title="Массовый ввод показаний"
            open={open}
            onCancel={onClose}
            width={800}
            destroyOnClose
            footer={[
                <Button key="cancel" onClick={onClose}>
                    Отмена
                </Button>,
                <Button key="save" type="primary" loading={saving} onClick={handleSave}>
                    Сохранить
                </Button>,
            ]}
        >
            <Space style={{ marginBottom: 16 }} size="large" wrap>
                <div>
                    <div style={{ marginBottom: 4 }}>Вид услуги</div>
                    <Select
                        style={{ width: 220 }}
                        placeholder="Выберите вид услуги"
                        value={serviceTypeId}
                        onChange={setServiceTypeId}
                        options={serviceTypes.map((s: any) => ({
                            value: s.id,
                            label: s.services_type,
                        }))}
                    />
                </div>
                <div>
                    <div style={{ marginBottom: 4 }}>Дата показания</div>
                    <DatePicker
                        value={readingDate}
                        format={DATE_FORMAT}
                        onChange={(value) => value && setReadingDate(value)}
                        allowClear={false}
                    />
                </div>
            </Space>

            <Table
                rowKey="id"
                dataSource={apartments}
                columns={columns}
                loading={apartmentsLoading}
                pagination={false}
                size="small"
                scroll={{ y: 400 }}
            />
        </Modal>
    );
};

// --- РАСЧЁТ НАЧИСЛЕНИЙ ЗА ПЕРИОД ---
// Оператор выбирает месяц/год начисления — сервер рассчитывает по всем лицевым счетам
// и видам услуг предварительные строки (тариф, показания, потребление, сумма).
// Оператор может снять галочки с ненужных строк и сохранить только выбранные в регистр.
type AccrualPreviewRow = {
    row_number: number;
    account_id: number;
    account_id_label: string;
    services_type_id: number;
    services_type_id_label: string;
    tariff_id: number;
    tariff_id_label: string;
    past_reading_value: number | null;
    current_reading_value: number | null;
    consumption: number;
    amount: number;
};

const monthOptions = [
    { value: 1, label: "Январь" },
    { value: 2, label: "Февраль" },
    { value: 3, label: "Март" },
    { value: 4, label: "Апрель" },
    { value: 5, label: "Май" },
    { value: 6, label: "Июнь" },
    { value: 7, label: "Июль" },
    { value: 8, label: "Август" },
    { value: 9, label: "Сентябрь" },
    { value: 10, label: "Октябрь" },
    { value: 11, label: "Ноябрь" },
    { value: 12, label: "Декабрь" },
];

const AccrualsCalculationModal = ({
    open,
    onClose,
    onSaved,
}: {
    open: boolean;
    onClose: () => void;
    onSaved: () => void;
}) => {
    const apiUrl = useApiUrl();
    const now = dayjs();
    const [year, setYear] = useState<number>(now.year());
    const [month, setMonth] = useState<number>(now.month() + 1);
    const [rows, setRows] = useState<AccrualPreviewRow[]>([]);
    const [selectedKeys, setSelectedKeys] = useState<number[]>([]);

    const { refetch, isFetching } = useCustom<{ rows: AccrualPreviewRow[] }>({
        url: `${apiUrl}/accruals_register/calculate`,
        method: "get",
        config: { query: { year, month } },
        queryOptions: {
            enabled: false,
            onSuccess: (response) => {
                const data = response.data.rows ?? [];
                setRows(data);
                setSelectedKeys(data.map((row) => row.row_number));
            },
            onError: (err: any) =>
                message.error(
                    err?.response?.data?.detail ?? "Не удалось рассчитать начисления",
                ),
        },
    });

    const { mutate: generate, isLoading: saving } = useCustomMutation();

    useEffect(() => {
        if (open) {
            const n = dayjs();
            setYear(n.year());
            setMonth(n.month() + 1);
            setRows([]);
            setSelectedKeys([]);
        }
    }, [open]);

    useEffect(() => {
        if (open) {
            refetch();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, year, month]);

    const handleSave = () => {
        const selectedRows = rows.filter((row) =>
            selectedKeys.includes(row.row_number),
        );
        if (selectedRows.length === 0) {
            message.error("Выберите хотя бы одну строку для начисления");
            return;
        }

        generate(
            {
                url: `${apiUrl}/accruals_register/generate`,
                method: "post",
                values: {
                    year,
                    month,
                    rows: selectedRows,
                },
            },
            {
                onSuccess: (response) => {
                    const created = (response.data as any).created?.length ?? 0;
                    message.success(`Начислено записей: ${created}`);
                    onSaved();
                    onClose();
                },
                onError: (err: any) =>
                    message.error(
                        err?.response?.data?.detail ?? "Не удалось сохранить начисления",
                    ),
            },
        );
    };

    const allSelected = rows.length > 0 && selectedKeys.length === rows.length;
    const someSelected = selectedKeys.length > 0 && !allSelected;

    const columns = [
        {
            title: (
                <Checkbox
                    checked={allSelected}
                    indeterminate={someSelected}
                    onChange={(e) =>
                        setSelectedKeys(
                            e.target.checked ? rows.map((row) => row.row_number) : [],
                        )
                    }
                />
            ),
            key: "select",
            width: 50,
            render: (_: unknown, record: AccrualPreviewRow) => (
                <Checkbox
                    checked={selectedKeys.includes(record.row_number)}
                    onChange={(e) =>
                        setSelectedKeys((prev) =>
                            e.target.checked
                                ? [...prev, record.row_number]
                                : prev.filter((key) => key !== record.row_number),
                        )
                    }
                />
            ),
        },
        { title: "№", dataIndex: "row_number", key: "row_number", width: 60 },
        {
            title: "Квартира (Лицевой счёт)",
            dataIndex: "account_id_label",
            key: "account_id_label",
        },
        {
            title: "Вид услуги",
            dataIndex: "services_type_id_label",
            key: "services_type_id_label",
        },
        {
            title: "Показание прошлое",
            dataIndex: "past_reading_value",
            key: "past_reading_value",
            render: formatNumber,
        },
        {
            title: "Показание текущее",
            dataIndex: "current_reading_value",
            key: "current_reading_value",
            render: formatNumber,
        },
        {
            title: "Потребление",
            dataIndex: "consumption",
            key: "consumption",
            render: formatNumber,
        },
        {
            title: "Тариф",
            dataIndex: "tariff_id_label",
            key: "tariff_id_label",
        },
        {
            title: "Сумма",
            dataIndex: "amount",
            key: "amount",
            render: formatNumber,
        },
    ];

    return (
        <Modal
            title="Начисление сумм по коммунальным услугам"
            open={open}
            onCancel={onClose}
            width={1100}
            destroyOnClose
            footer={[
                <Button key="cancel" onClick={onClose}>
                    Отмена
                </Button>,
                <Button
                    key="save"
                    type="primary"
                    loading={saving}
                    disabled={selectedKeys.length === 0}
                    onClick={handleSave}
                >
                    Начислить выбранные ({selectedKeys.length})
                </Button>,
            ]}
        >
            <Space style={{ marginBottom: 16 }} size="large" wrap>
                <div>
                    <div style={{ marginBottom: 4 }}>Месяц</div>
                    <Select
                        style={{ width: 160 }}
                        value={month}
                        onChange={setMonth}
                        options={monthOptions}
                    />
                </div>
                <div>
                    <div style={{ marginBottom: 4 }}>Год</div>
                    <InputNumber
                        style={{ width: 120 }}
                        value={year}
                        min={2000}
                        max={2100}
                        onChange={(value) => value && setYear(Number(value))}
                    />
                </div>
            </Space>

            <Table
                rowKey="row_number"
                dataSource={rows}
                columns={columns}
                loading={isFetching}
                pagination={false}
                size="small"
                scroll={{ y: 450 }}
            />
        </Modal>
    );
};

// --- СПИСОК (правая панель контента): таблица + Добавить/Редактировать/Удалить
const GenericList = ({ resourceName }: { resourceName: string }) => {
    const apiUrl = useApiUrl();
    const { tableQuery, current, setCurrent, pageSize, setPageSize } = useTable({
        resource: resourceName,
    });
    const data = tableQuery?.data?.data ?? [];
    const total = tableQuery?.data?.total ?? 0;

    const { data: metaResponse, isLoading: metaLoading } = useCustom<{
        fields: FieldMeta[];
    }>({
        url: `${apiUrl}/meta/${resourceName}`,
        method: "get",
    });
    const fields = metaResponse?.data?.fields ?? [];

    const { mutate: createRecord, isLoading: creating } = useCreate();
    const { mutate: updateRecord, isLoading: updating } = useUpdate();
    const { mutate: deleteRecord } = useDelete();

    const [modalState, setModalState] = useState<ModalState | null>(null);
    const [bulkModalOpen, setBulkModalOpen] = useState(false);
    const [accrualsModalOpen, setAccrualsModalOpen] = useState(false);

    const isAccrualsRegister = resourceName === "accruals_register";

    // --- ЗАПРЕТ НА УДАЛЕНИЕ И РЕДАКТИРОВАНИЕ ---
    const isReadOnly = resourceName === "accounts_register";

    const columns = columnsConfig[resourceName] ?? defaultColumns;
    const meta = allResources.find((r) => r.key === resourceName);

    const handleSubmit = (values: Record<string, any>) => {
        if (modalState?.mode === "create") {
            createRecord(
                { resource: resourceName, values },
                {
                    onSuccess: () => {
                        message.success("Запись добавлена");
                        setModalState(null);
                    },
                    onError: (err: any) =>
                        message.error(
                            err?.response?.data?.detail ?? "Не удалось создать запись",
                        ),
                },
            );
        } else if (modalState?.mode === "edit" && modalState.record) {
            updateRecord(
                { resource: resourceName, id: modalState.record.id, values },
                {
                    onSuccess: () => {
                        message.success("Запись обновлена");
                        setModalState(null);
                    },
                    onError: (err: any) =>
                        message.error(
                            err?.response?.data?.detail ?? "Не удалось обновить запись",
                        ),
                },
            );
        }
    };

    const tableColumns = [
        { title: "ID", dataIndex: "id", key: "id", width: 70 },
        ...columns.map((col) => ({
            title: col.label,
            dataIndex: col.key,
            key: col.key,
            render: (value: any) => (col.format ? col.format(value) : value ?? "—"),
        })),
        {
            title: "Действия",
            key: "actions",
            width: 200,
            render: (_: unknown, record: any) =>
                !isReadOnly ? (
                    <Space>
                        <Button
                            size="small"
                            onClick={() => setModalState({ mode: "edit", record })}
                        >
                            Редактировать
                        </Button>
                        <Popconfirm
                            title="Удалить запись?"
                            okText="Удалить"
                            cancelText="Отмена"
                            onConfirm={() =>
                                deleteRecord(
                                    { resource: resourceName, id: record.id },
                                    {
                                        onSuccess: () => message.success("Запись удалена"),
                                        onError: (err: any) =>
                                            message.error(
                                                err?.response?.data?.detail ??
                                                    "Не удалось удалить запись",
                                            ),
                                    },
                                )
                            }
                        >
                            <Button size="small" danger>
                                Удалить
                            </Button>
                        </Popconfirm>
                    </Space>
                ) : (
                    <span style={{ color: "#999", fontSize: "12px" }}>Только чтение</span>
                ),
        },
    ];

    return (
        <div
            style={{
                background: "#fff",
                padding: "30px",
                borderRadius: "12px",
                width: "100%",
                boxSizing: "border-box",
            }}
        >
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 20,
                }}
            >
                <h1 style={{ color: "#1f1f1f", margin: 0 }}>
                    {meta?.label ?? resourceName}
                </h1>
                <Space>
                    {resourceName === "meter_readings" && (
                        <Button onClick={() => setBulkModalOpen(true)}>
                            Массовый ввод показаний
                        </Button>
                    )}
                    {!isReadOnly && isAccrualsRegister && (
                        <Button
                            type="primary"
                            onClick={() => setAccrualsModalOpen(true)}
                        >
                            Добавить
                        </Button>
                    )}
                    {!isReadOnly && !isAccrualsRegister && (
                        <Button
                            type="primary"
                            disabled={metaLoading}
                            onClick={() => setModalState({ mode: "create" })}
                        >
                            Добавить
                        </Button>
                    )}
                </Space>
            </div>

            <Table
                rowKey="id"
                dataSource={data}
                columns={tableColumns}
                loading={tableQuery.isLoading}
                pagination={{
                    current,
                    pageSize,
                    total,
                    showSizeChanger: true,
                    onChange: (page, size) => {
                        setCurrent(page);
                        if (size) setPageSize(size);
                    },
                }}
            />

            {modalState && (
                <RecordFormModal
                    open={!!modalState}
                    title={
                        modalState.mode === "create" ? "Новая запись" : "Редактирование записи"
                    }
                    fields={fields}
                    initialValues={modalState.record}
                    confirmLoading={creating || updating}
                    onCancel={() => setModalState(null)}
                    onSubmit={handleSubmit}
                />
            )}

            {resourceName === "meter_readings" && (
                <BulkReadingsModal
                    open={bulkModalOpen}
                    onClose={() => setBulkModalOpen(false)}
                    onSaved={() => tableQuery.refetch()}
                />
            )}

            {isAccrualsRegister && (
                <AccrualsCalculationModal
                    open={accrualsModalOpen}
                    onClose={() => setAccrualsModalOpen(false)}
                    onSaved={() => tableQuery.refetch()}
                />
            )}
        </div>
    );
};

const App = () => {
    return (
        <ConfigProvider locale={ruRU}>
            <BrowserRouter>
                <Refine
                    dataProvider={dataProvider("/api")}
                    routerProvider={routerBindings}
                    resources={allResources.map((r) => ({
                        name: r.key,
                        list: `/${r.key}`,
                    }))}
                >
                    <Routes>
                        <Route
                            element={
                                <div style={{ display: "flex", minHeight: "100vh" }}>
                                    <Sidebar />
                                    <div
                                        style={{
                                            flex: 1,
                                            padding: "40px",
                                            background: "#f0f2f5",
                                        }}
                                    >
                                        <Outlet />
                                    </div>
                                </div>
                            }
                        >
                            <Route
                                index
                                element={<NavigateToResource resource="owners" />}
                            />
                            {allResources.map((r) => (
                                <Route
                                    key={r.key}
                                    path={`/${r.key}`}
                                    element={<GenericList resourceName={r.key} />}
                                />
                            ))}
                        </Route>
                    </Routes>
                </Refine>
            </BrowserRouter>
        </ConfigProvider>
    );
};

export default App;
