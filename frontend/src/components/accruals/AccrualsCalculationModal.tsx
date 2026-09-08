// AccrualsCalculationModal.tsx

import { useEffect, useState } from "react";
import { Modal, Button, Space, Select, InputNumber, Table, Checkbox, Input, message, Tag } from "antd";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";
import { useApiUrl, useCustom, useCustomMutation } from "@refinedev/core";
import type { AccrualPreviewRow } from "../../types";
import { formatMoney, formatNumber } from "../../config/formatters";

interface AccrualsCalculationModalProps {
    open: boolean;
    onClose: () => void;
    onSaved: () => void;
    /** Если передан, модалка работает в режиме редактирования существующего документа */
    documentId?: number;
    /** Режим «только просмотр»: изменение документа недоступно. */
    readonly?: boolean;
}

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

const monthLabelByValue: Record<number, string> = Object.fromEntries(
    monthOptions.map((m) => [m.value, m.label]),
);

const getDefaultTitle = (year: number, month: number): string =>
    `Начисление за ${monthLabelByValue[month] ?? month} ${year}`;

interface ServiceTariffRow {
    services_type_id: number;
    service_label: string;
    tariff_label: string;
}

/**
 * Сводит строки превью (аккаунт × услуга) к уникальным услугам с применяемым
 * за месяц тарифом. В одном месяце по услуге начисляется один тариф (2.18),
 * поэтому он одинаков у всех аккаунтов этой услуги в превью.
 */
const aggregateServiceTariffs = (rows: AccrualPreviewRow[]): ServiceTariffRow[] => {
    const seen = new Map<number, AccrualPreviewRow>();
    for (const row of rows) {
        if (!seen.has(row.services_type_id)) {
            seen.set(row.services_type_id, row);
        }
    }
    return Array.from(seen.values()).map((row) => ({
        services_type_id: row.services_type_id,
        service_label: row.services_type_id_label,
        tariff_label: row.tariff_id_label,
    }));
};

/**
 * Модальное окно для расчета и начисления коммунальных услуг.
 * Без documentId — режим создания: оператор выбирает месяц/год, система рассчитывает
 * предварительные строки, оператор выбирает строки для сохранения в новый документ.
 * С documentId — режим редактирования: подгружаются месяц/год и ранее выбранные строки
 * существующего документа, при сохранении строки документа полностью пересоздаются.
 */
export const AccrualsCalculationModal = ({
    open,
    onClose,
    onSaved,
    documentId,
    readonly = false,
}: AccrualsCalculationModalProps) => {
    const apiUrl = useApiUrl();
    const isEditMode = documentId !== undefined;
    const now = dayjs();
    const [year, setYear] = useState<number>(now.year());
    const [month, setMonth] = useState<number>(now.month() + 1);
    const [rows, setRows] = useState<AccrualPreviewRow[]>([]);
    const [selectedKeys, setSelectedKeys] = useState<number[]>([]);
    const [isSaving, setIsSaving] = useState(false);
    const [pendingSelection, setPendingSelection] = useState<
        Array<{ account_id: number; services_type_id: number }> | null
    >(null);
    const [comment, setComment] = useState<string>("");
    const [showTariffNotes, setShowTariffNotes] = useState(false);
    const navigate = useNavigate();

    // Единица №3: внесённые «ставки месяца» (другая ставка на выбранный месяц),
    // отправляются как draft_tariffs на сервер при сохранении.
    const [draftTariffs, setDraftTariffs] = useState<
        Array<{ services_type_id: number; price: number; comment: string }>
    >([]);
    const [draftSvc, setDraftSvc] = useState<number | undefined>(undefined);
    const [draftPrice, setDraftPrice] = useState<number | undefined>(undefined);
    const [draftReason, setDraftReason] = useState<string>("");

    const { refetch, isFetching } = useCustom<{ rows: AccrualPreviewRow[] }>({
        url: `${apiUrl}/accruals_register/calculate`,
        method: "get",
        config: { query: { year, month } },
        queryOptions: {
            enabled: false,
            onSuccess: (response) => {
                const data = response.data.rows ?? [];
                setRows(data);
                if (pendingSelection) {
                    // Восстанавливаем выбор строк, ранее сохранённых в редактируемом документе
                    const keys = data
                        .filter((row) =>
                            pendingSelection.some(
                                (sel) =>
                                    sel.account_id === row.account_id &&
                                    sel.services_type_id === row.services_type_id,
                            ),
                        )
                        .map((row) => row.row_number);
                    setSelectedKeys(keys);
                    setPendingSelection(null);
                } else {
                    setSelectedKeys(data.map((row) => row.row_number));
                }
            },
            onError: (err: any) =>
                message.error(
                    err?.response?.data?.detail ?? "Не удалось рассчитать начисления",
                ),
        },
    });

    const { refetch: fetchDocumentDetails, isFetching: isLoadingDocument } = useCustom<{
        year: number;
        month: number;
        selections: Array<{ account_id: number; services_type_id: number }>;
        document?: { id: number; title?: string | null; comment?: string | null };
    }>({
        url: `${apiUrl}/accrual_documents/${documentId}/details`,
        method: "get",
        queryOptions: {
            enabled: false,
            onSuccess: (response) => {
                const { year: docYear, month: docMonth, selections, document } = response.data;
                setPendingSelection(selections ?? []);
                setYear(docYear);
                setMonth(docMonth);
                setComment(document?.comment ?? "");
            },
            onError: (err: any) =>
                message.error(
                    err?.response?.data?.detail ?? "Не удалось загрузить документ начислений",
                ),
        },
    });

    const { mutate: generate, isLoading: saving } = useCustomMutation();

    useEffect(() => {
        if (!open) return;

        if (isEditMode) {
            setRows([]);
            setSelectedKeys([]);
            setComment("");
            setDraftTariffs([]);
            setDraftSvc(undefined);
            setDraftPrice(undefined);
            setDraftReason("");
            fetchDocumentDetails();
        } else {
            const n = dayjs();
            setYear(n.year());
            setMonth(n.month() + 1);
            setRows([]);
            setSelectedKeys([]);
            setPendingSelection(null);
            setDraftTariffs([]);
            setDraftSvc(undefined);
            setDraftPrice(undefined);
            setDraftReason("");
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, isEditMode, documentId]);

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

        setIsSaving(true);

        // Название документа генерируется на сервере автоматически (1.9 роадмапа).
        const selections = selectedRows.map((row) => ({
            account_id: row.account_id,
            services_type_id: row.services_type_id,
        }));

        // 2.18: месячное подтверждение — если оператор внёс другие ставки месяца.
        const draft_tariffs = draftTariffs.map((d) => ({
            services_type_id: d.services_type_id,
            price: d.price,
            comment: d.comment,
        }));

        // Отправляем только идентификаторы выбранных строк — сумма, потребление, тариф и показания
        // будут пересчитаны на сервере на момент сохранения.
        if (isEditMode) {
            generate(
                {
                    url: `${apiUrl}/accrual_documents/${documentId}/full`,
                    method: "put",
                    values: {
                        accrual_date: `${year}-${String(month).padStart(2, "0")}-01`,
                        selections,
                        comment: comment.trim() || null,
                        draft_tariffs,
                    },
                },
                {
                    onSuccess: (response) => {
                        const data = response.data as any;
                        const updated = data.updated?.length ?? 0;
                        message.success(`Документ начислений обновлён, записей: ${updated}`);
                        onSaved();
                        onClose();
                        setIsSaving(false);
                    },
                    onError: (err: any) => {
                        message.error(
                            err?.response?.data?.detail ?? "Не удалось обновить начисления",
                        );
                        setIsSaving(false);
                    },
                },
            );
        } else {
            generate(
                {
                    url: `${apiUrl}/accruals_register/generate`,
                    method: "post",
                    values: { year, month, selections, draft_tariffs },
                },
                {
                    onSuccess: (response) => {
                        const data = response.data as any;
                        const created = data.created?.length ?? 0;
                        const newDocumentId = data.document?.id;
                        message.success(
                            newDocumentId
                                ? `Создан документ начислений №${newDocumentId}, начислено записей: ${created}`
                                : `Начислено записей: ${created}`,
                        );
                        onSaved();
                        onClose();
                        setIsSaving(false);
                    },
                    onError: (err: any) => {
                        message.error(
                            err?.response?.data?.detail ?? "Не удалось сохранить начисления",
                        );
                        setIsSaving(false);
                    },
                },
            );
        }
    };

    const allSelected = rows.length > 0 && selectedKeys.length === rows.length;
    const someSelected = selectedKeys.length > 0 && !allSelected;

    const columns = [
        ...(!readonly
            ? [
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
              ]
            : []),
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
            render: formatMoney,
        },
    ];

    // 2.18: блок «Проверить тарифы» — какие тарифы реально применяются за месяц
    // (по услугам). Ставки месяца — обычный механизм (единая лента тарифов),
    // поэтому дополнительного предупреждения «разовый тариф» больше нет.
    const serviceTariffs = aggregateServiceTariffs(rows);

    const tariffNotesColumns = [
        { title: "Вид услуги", dataIndex: "service_label", key: "service_label" },
        { title: "Применяется тариф", dataIndex: "tariff_label", key: "tariff_label" },
    ];

    return (
        <Modal
            title={
                readonly
                    ? "Просмотр документа начислений"
                    : isEditMode
                      ? "Редактирование документа начислений"
                      : "Начисление сумм по коммунальным услугам"
            }
            open={open}
            onCancel={onClose}
            width={1100}
            destroyOnClose
            footer={
                readonly
                    ? [
                          <Button key="close" type="primary" onClick={onClose}>
                              Закрыть
                          </Button>,
                      ]
                    : [
                          <Button key="cancel" onClick={onClose}>
                              Отмена
                          </Button>,
                          <Button
                              key="save"
                              type="primary"
                              loading={saving || isSaving}
                              disabled={selectedKeys.length === 0}
                              onClick={handleSave}
                          >
                              {isEditMode
                                  ? `Сохранить изменения (${selectedKeys.length})`
                                  : `Начислить выбранные (${selectedKeys.length})`}
                          </Button>,
                      ]
            }
        >
            <Space style={{ marginBottom: 16 }} size="large" wrap>
                <div>
                    <div style={{ marginBottom: 4 }}>Название документа</div>
                    <Input
                        style={{ width: 280 }}
                        value={getDefaultTitle(year, month)}
                        readOnly
                        disabled={readonly}
                    />
                </div>
                <div>
                    <div style={{ marginBottom: 4 }}>Месяц</div>
                    <Select
                        style={{ width: 160 }}
                        value={month}
                        disabled={readonly}
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
                        disabled={readonly}
                        onChange={(value) => value && setYear(Number(value))}
                    />
                </div>
            </Space>

            {!readonly && (
                <div style={{ marginBottom: showTariffNotes ? 8 : 0 }}>
                    <Button
                        size="small"
                        type="text"
                        onClick={() => setShowTariffNotes((v) => !v)}
                    >
                        {showTariffNotes
                            ? "Скрыть проверку тарифов"
                            : "Проверить тарифы"}
                    </Button>
                </div>
            )}

            {!readonly && showTariffNotes && (
                <div style={{ marginBottom: 16, background: "#fafafa", padding: 8, borderRadius: 6 }}>
                    <Table
                        rowKey="services_type_id"
                        size="small"
                        pagination={false}
                        dataSource={serviceTariffs}
                        columns={tariffNotesColumns}
                        scroll={{ y: 200 }}
                    />
                    <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                        <Select
                            placeholder="Услуга"
                            style={{ width: 220 }}
                            value={draftSvc}
                            onChange={(v) => setDraftSvc(v)}
                            options={serviceTariffs.map((t) => ({
                                value: t.services_type_id,
                                label: t.service_label,
                            }))}
                        />
                        <InputNumber
                            placeholder="Новая ставка месяца (₸)"
                            min={0}
                            style={{ width: 170 }}
                            value={draftPrice}
                            onChange={(v) => setDraftPrice(v === null || v === undefined ? undefined : Number(v))}
                        />
                        <Input.TextArea
                            rows={1}
                            style={{ width: 280 }}
                            placeholder="Примечание (причина изменения)"
                            value={draftReason}
                            onChange={(e) => setDraftReason(e.target.value)}
                        />
                        <Button
                            size="small"
                            type="primary"
                            disabled={!(draftSvc && draftPrice)}
                            onClick={() => {
                                if (!draftSvc || !draftReason.trim()) {
                                    message.error(
                                        draftSvc && draftPrice
                                            ? "Укажите Примечание (причину изменения ставки)"
                                            : "Выберите услугу и введите ставку месяца",
                                    );
                                    return;
                                }
                                setDraftTariffs((prev) => {
                                    const rest = prev.filter((d) => d.services_type_id !== draftSvc);
                                    return [
                                        ...rest,
                                        {
                                            services_type_id: draftSvc,
                                            price: Number(draftPrice),
                                            comment: draftReason.trim(),
                                        },
                                    ];
                                });
                                setDraftPrice(undefined);
                                setDraftReason("");
                                setDraftSvc(undefined);
                            }}
                        >
                            Ввести как ставку месяца
                        </Button>
                    </div>
                    {draftTariffs.length > 0 && (
                        <div style={{ marginTop: 8 }}>
                            <Space wrap>
                                {draftTariffs.map((d) => {
                                    const lbl =
                                        serviceTariffs.find((t) => t.services_type_id === d.services_type_id)?.service_label ??
                                        `услуга #${d.services_type_id}`;
                                    return (
                                        <Tag
                                            key={d.services_type_id}
                                            closable
                                            color="geekblue"
                                            onClose={(e) => {
                                                e.preventDefault();
                                                setDraftTariffs((prev) =>
                                                    prev.filter((x) => x.services_type_id !== d.services_type_id),
                                                );
                                            }}
                                        >
                                            {lbl}: {formatMoney(d.price)} — {d.comment.slice(0, 30)}
                                        </Tag>
                                    );
                                })}
                            </Space>
                        </div>
                    )}
                    <div style={{ marginTop: 8, textAlign: "right" }}>
                        <Button
                            size="small"
                            onClick={() => navigate("/tariffs")}
                        >
                            Открыть раздел «Тарифы»
                        </Button>
                    </div>
                </div>
            )}

            {isEditMode && (
                <div style={{ marginBottom: 12 }}>
                    <div style={{ marginBottom: 4 }}>Примечание</div>
                    <Input.TextArea
                        rows={2}
                        value={comment}
                        disabled={readonly}
                        onChange={(e) => setComment(e.target.value)}
                        placeholder="Комментарий бухгалтера (необязательно)"
                    />
                </div>
            )}

            <Table
                rowKey="row_number"
                dataSource={rows}
                columns={columns}
                loading={isFetching || isLoadingDocument}
                pagination={false}
                size="small"
                scroll={{ y: 450 }}
            />
        </Modal>
    );
};
