// src/pages/GenericList.tsx

import { useEffect, useState } from "react";
import {
    Table,
    Button,
    Space,
    Popconfirm,
    Popover,
    Input,
    InputNumber,
    Select,
    DatePicker,
    message,
} from "antd";
import {
    useTable,
    useCreate,
    useUpdate,
    useDelete,
    useCustom,
    useCustomMutation,
    useApiUrl,
    useGetIdentity,
} from "@refinedev/core";
import type { FieldMeta, ModalState } from "../types";
import type { CrudFilter } from "@refinedev/core";
import { getColumnsForResource } from "../config/columns";
import { allResources } from "../config/menu";
import {
    getDefaultResourceFilters,
    getFilterKind,
    getReferenceSource,
    getResourceSelectOptions,
    getSelectOptions,
    isReferenceFilter,
    isResourceSelectFilter,
} from "../config/filters";
import { RecordFormModal } from "../components/common/RecordFormModal";
import { ReferenceFilterSelect } from "../components/common/ReferenceFilterSelect";
import {
    ColumnDragTitle,
    SortableColumns,
} from "../components/common/SortableColumns";
import {
    headerResizeProps,
    tableHeaderComponents,
} from "../components/common/ResizableHeader";
import {
    DndContext,
    PointerSensor,
    closestCenter,
    useSensor,
    useSensors,
    type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext } from "@dnd-kit/sortable";
import { BulkReadingsModal } from "../components/meter-readings/BulkReadingsModal";
import { AccrualsCalculationModal } from "../components/accruals/AccrualsCalculationModal";
import { OneOffAccrualsEditModal } from "../components/accruals/OneOffAccrualsEditModal";
import { ReceiptsModal } from "../components/receipts/ReceiptsModal";
import { ReceiptViewModal } from "../components/receipts/ReceiptViewModal";
import { WriteOffsModal } from "../components/writeoffs/WriteOffsModal";
import { WriteoffViewModal } from "../components/writeoffs/WriteoffViewModal";
import type { SortOrder } from "antd/es/table/interface";
import { BRAND } from "../config/colors";
import { canCreate, canEdit, canDelete } from "../auth/can";
import { useColumnSettings } from "../hooks/useColumnSettings";
import { openAuthorizedPdf } from "../auth/http";

interface GenericListProps {
    resourceName: string;
}

// Конфигурация сортировки для всех полей
const sortMapping: Record<string, string> = {
    'id': 'id',
    'apartment_number': 'apartment_number',
    'address': 'address',
    'square': 'square',
    'account_number': 'account_number',
    'account_name': 'account_name',
    'is_active': 'is_active',
    'name': 'name',
    'transaction_date': 'transaction_date',
    'amount': 'amount',
    'transaction_type': 'transaction_type',
    'notes': 'notes',
    'past_reading_value': 'past_reading_value',
    'current_reading_value': 'current_reading_value',
    'consumption': 'consumption',
    'operation_date': 'operation_date',
    'income': 'income',
    'expense': 'expense',
    'balance_after': 'balance_after',
    'price': 'price',
    'unit': 'unit',
    'valid_from': 'valid_from',
    'is_oneoff': 'is_oneoff',
    'serial_number': 'serial_number',
    'installed_at': 'installed_at',
    'full_name': 'full_name',
    'phone': 'phone',
    'title': 'title',
    'reading_date': 'reading_date',
    'readings_count': 'readings_count',

    // Вложенные поля
    'owner.full_name': 'owner.full_name',
    'owner_id_label': 'owner.full_name',
    'apartment.apartment_number': 'apartment.apartment_number',
    'apartment_id_label': 'apartment.apartment_number',
    'services_type.services_type': 'services_type.services_type',
    'services_type_id_label': 'services_type.services_type',
    'meter.serial_number': 'meter.serial_number',
    'meter_label': 'meter.serial_number',
    'account.account_number': 'account.account_number',
    'account_label': 'account.account_number',
    'account_id_label': 'account.account_number',
    'cash_point.name': 'cash_point.name',
    'cash_point_id_label': 'cash_point.name',
    'tariff_type.name': 'tariff_type.name',
    'tariff_type_id_label': 'tariff_type.name',
    'document.title': 'document.title',
    'document_id_label': 'document.title',
    'document_title': 'document_title',

    // Поля начислений и документов
    'accrual_date': 'accrual_date',
    'accrual_document_id': 'accrual_document_id',
    'created_at': 'created_at',
    'accruals_count': 'accruals_count',
    'total_amount': 'total_amount',
    // Документ начислений: тип (doc_kind) и примечание (comment) — прямые столбцы.
    'doc_kind': 'doc_kind',
    'comment': 'comment',

    // Поля квитанций
    'owner_name': 'owner_name',
    'period_month': 'period_month',
    'period_year': 'period_year',
    'debt': 'debt',
    'overpayment': 'overpayment',
    'payable_amount': 'payable_amount',

    // Дополнение (2.11 «Сортировка»): аналитика, автор, справочные/вложенные поля,
    // статусы и количества записей.
    'article.name': 'article.name',
    'created_by_name': 'created_by_name',
    'kind': 'kind',
    'reading': 'reading',
    'priority': 'priority',
    'services_type': 'services_type',
    'writeoff_date': 'writeoff_date',
    'status': 'status',
    'items_count': 'items_count',
    'total_allocated': 'total_allocated',
    'owner.phone': 'owner.phone',
    'apartment.owner.full_name': 'apartment.owner.full_name',
};

const isSortableField = (dataIndex: string): boolean => {
    if (dataIndex === 'id') return true;
    return !!sortMapping[dataIndex];
};

const getSortField = (dataIndex: string): string => {
    if (sortMapping[dataIndex]) {
        return sortMapping[dataIndex];
    }
    return dataIndex;
};

const getValueByPath = (obj: any, path: string): any => {
    if (!obj || !path) return undefined;
    const keys = path.split('.');
    let result = obj;
    for (const key of keys) {
        if (result === null || result === undefined) return undefined;
        result = result[key];
    }
    return result;
};

export const GenericList = ({ resourceName }: GenericListProps) => {
    const apiUrl = useApiUrl();

    const { data: identity } = useGetIdentity<any>();

    // Регистр начислений: свежие периоды сверху (иначе первыми идут «входящие остатки»
    // стартовых долгов — они добавлены позже всех и стоят в конце по id).
    const defaultSortDescPeriod = resourceName === "accruals_register";
    const initialSortField = defaultSortDescPeriod ? "accrual_date" : "id";

    // Фильтры по умолчанию для раздела (например «Тарифы» — только «Действующие»).
    const resourceDefaults = getDefaultResourceFilters(resourceName);
    const initialCrudFilters = (resourceDefaults?.applied ?? []) as CrudFilter[];

    const {
        tableQuery,
        current,
        setCurrent,
        pageSize,
        setPageSize,
        sorters,
        setSorters,
        setFilters,
    } = useTable({
        resource: resourceName,
        pagination: {
            current: 1,
            pageSize: 10,
        },
        sorters: {
            initial: [
                {
                    field: initialSortField,
                    order: "desc",
                },
            ],
        },
        filters: {
            initial: initialCrudFilters,
        },
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

    // Защита от «протёкших» фильтров: если компонент всё же переиспользован для другого
    // ресурса (роуты обычно дают key, но страхуемся), сбрасываем локальное состояние
    // и возвращаем фильтры по умолчанию для раздела (если они есть).
    useEffect(() => {
        const def = getDefaultResourceFilters(resourceName);
        setDraftFilters(def?.draft ?? {});
        setAppliedCount(def ? def.applied.length : 0);
        setFilters(def ? (def.applied as CrudFilter[]) : [], "replace");
    }, [resourceName]);

    // --- Общий механизм фильтрации (Б10) ---
    // Черновик фильтров по колонкам списка; применяется серверно через setFilters.
    const [filtersOpen, setFiltersOpen] = useState(false);
    const [draftFilters, setDraftFilters] = useState<Record<string, any>>(
        () => getDefaultResourceFilters(resourceName)?.draft ?? {},
    );
    const [appliedCount, setAppliedCount] = useState(
        () => getDefaultResourceFilters(resourceName)?.applied.length ?? 0,
    );
    const [bulkModalOpen, setBulkModalOpen] = useState(false);
    const [editingMeterReadingDocumentId, setEditingMeterReadingDocumentId] = useState<number | undefined>(undefined);
    const [accrualsModalOpen, setAccrualsModalOpen] = useState(false);
    const [editingAccrualDocumentId, setEditingAccrualDocumentId] = useState<number | undefined>(undefined);
    const [oneOffAccrualsOpen, setOneOffAccrualsOpen] = useState(false);
    const [receiptsModalOpen, setReceiptsModalOpen] = useState(false);
    const [receiptViewId, setReceiptViewId] = useState<number | undefined>(undefined);
    const [writeOffsModalOpen, setWriteOffsModalOpen] = useState(false);
    const [writeoffViewId, setWriteoffViewId] = useState<number | undefined>(undefined);

    const isAccrualsRegister = resourceName === "accruals_register";
    const isAccrualDocuments = resourceName === "accrual_documents";
    const isMeterReadingDocuments = resourceName === "meter_reading_documents";
    const isMeterReadings = resourceName === "meter_readings";
    const isReadOnly = resourceName === "accounts_register" || resourceName === "cash_register";
    const isReceiptDocuments = resourceName === "receipt_documents";
    const isWriteoffDocuments = resourceName === "writeoff_documents";
    const { mutate: cancelWriteoff } = useCustomMutation();
    const apiUrlForCancel = useApiUrl();
    const cancelWriteoffDoc = (documentId: number) => {
        cancelWriteoff(
            {
                url: `${apiUrlForCancel}/writeoff_documents/${documentId}/cancel`,
                method: "post",
                values: {},
            },
            {
                onSuccess: () => {
                    message.success("Документ списания отменён");
                    tableQuery.refetch();
                },
                onError: (err: any) =>
                    message.error(
                        err?.response?.data?.detail ?? "Не удалось отменить списание",
                    ),
            },
        );
    };
    // Регистры формируются документами и не поддерживают прямое редактирование/удаление
    const isRegister = isAccrualsRegister || isMeterReadings || isReadOnly;
    // Роль «Житель»: только просмотр — кнопки скрываются через canCreate/canEdit/canDelete.
    const role = identity?.role ?? "";
    // Права на действия для текущего раздела.
    const roleCanCreate = canCreate(role, resourceName);
    const roleCanEdit = canEdit(role, resourceName);
    const roleCanDelete = canDelete(role, resourceName);
    // Есть ли у роли хоть какое-то действие записи (иначе столбец «Действия» не показываем).
    const roleCanWrite = roleCanCreate || roleCanEdit || roleCanDelete;

    const columns = getColumnsForResource(resourceName);
    const meta = allResources.find((r) => r.key === resourceName);

    // Вариант A + C (п. 2.10): видимость и ПОРЯДОК колонок списка, сохранение в
    // localStorage по (ресурс, роль). Перестановка — drag&drop заголовков таблицы
    // или в панели «Колонки».
    const { orderedAll, hiddenKeys, widths, toggle, move, moveKey, setWidth } =
        useColumnSettings(
            resourceName,
            role,
            columns.map((c) => c.key),
        );
    const columnByKey = new Map(columns.map((c) => [c.key, c]));
    const displayColumns = orderedAll
        .filter((k) => !hiddenKeys.has(k))
        .map((k) => columnByKey.get(k))
        .filter((c): c is NonNullable<typeof c> => !!c);

    // Drag&drop самих заголовков колонок (короткий клик без сдвига — сортировка,
    // сдвиг от 5px — перетаскивание).
    const headerSensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    );
    const handleHeaderDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (!over || active.id === over.id) return;
        moveKey(String(active.id), String(over.id));
    };

    const getColumnSortOrder = (dataIndex: string): SortOrder | undefined => {
        if (!isSortableField(dataIndex)) return undefined;
        const sortField = getSortField(dataIndex);
        const sorter = sorters?.find(s => s.field === sortField || s.field === dataIndex);
        if (!sorter) return undefined;
        return sorter.order === 'asc' ? 'ascend' : 'descend';
    };

    const handleTableChange = (_pagination: any, _filters: any, sorter: any) => {
        if (!sorter || !sorter.field) {
            setSorters([]);
            return;
        }
        if (!isSortableField(sorter.field)) {
            setSorters([]);
            return;
        }
        const order = sorter.order === 'ascend' ? 'asc' : 'desc';
        const sortField = getSortField(sorter.field);
        setSorters([{
            field: sortField,
            order: order,
        }]);
    };

    // --- Фильтрация (Б10): черновик -> серверные фильтры (формат simple-rest) ---
    const setDraft = (key: string, patch: any) =>
        setDraftFilters((prev) => ({ ...prev, [key]: { ...(prev[key] ?? {}), ...patch } }));

    // Вид фильтра по колонке: глобальная карта + ресурсо-зависимые select-поля
    // (например «Статус» у тарифов — Действующий/Архивный).
    const getColumnKind = (key: string) =>
        isResourceSelectFilter(resourceName, key) ? "select" : getFilterKind(key);

    const buildCrudFilters = (): CrudFilter[] => {
        const list: CrudFilter[] = [];
        for (const col of displayColumns) {
            if (!isSortableField(col.key)) continue;
            const d = draftFilters[col.key];
            if (!d) continue;
            const kind = getColumnKind(col.key);
            if (kind === "text") {
                const v = (d.text ?? "").toString().trim();
                if (v) list.push({ field: col.key, operator: "contains", value: v });
            } else if (kind === "number") {
                if (d.from !== undefined && d.from !== null && d.from !== "") {
                    list.push({ field: col.key, operator: "gte", value: Number(d.from) });
                }
                if (d.to !== undefined && d.to !== null && d.to !== "") {
                    list.push({ field: col.key, operator: "lte", value: Number(d.to) });
                }
            } else if (kind === "date" || kind === "datetime") {
                const range = d.range;
                if (range && range[0]) {
                    list.push({ field: col.key, operator: "gte", value: range[0].format("YYYY-MM-DD") });
                }
                if (range && range[1]) {
                    list.push({ field: col.key, operator: "lte", value: range[1].format("YYYY-MM-DD") });
                }
            } else if (kind === "bool") {
                if (d.bool !== undefined && d.bool !== null) {
                    list.push({ field: col.key, operator: "eq", value: d.bool });
                }
            } else if (kind === "select") {
                if (d.sel !== undefined && d.sel !== null && d.sel !== "") {
                    list.push({ field: col.key, operator: "eq", value: d.sel });
                }
            }
        }
        return list;
    };

    const applyFilters = () => {
        const list = buildCrudFilters();
        setFilters(list, "replace");
        setAppliedCount(list.length);
        setCurrent(1);
        setFiltersOpen(false);
    };

    const resetFilters = () => {
        setDraftFilters({});
        setFilters([], "replace");
        setAppliedCount(0);
        setCurrent(1);
        setFiltersOpen(false);
    };

    const renderFilterControl = (col: { key: string; label: string }) => {
        const kind = getColumnKind(col.key);
        const d = draftFilters[col.key] ?? {};
        if (kind === "text") {
            return (
                <Input
                    allowClear
                    placeholder="Содержит…"
                    value={d.text}
                    onChange={(e) => setDraft(col.key, { text: e.target.value })}
                    onPressEnter={applyFilters}
                />
            );
        }
        if (kind === "number") {
            return (
                <Space.Compact style={{ width: "100%" }}>
                    <InputNumber
                        style={{ width: "50%" }}
                        placeholder="от"
                        value={d.from}
                        onChange={(v) => setDraft(col.key, { from: v })}
                    />
                    <InputNumber
                        style={{ width: "50%" }}
                        placeholder="до"
                        value={d.to}
                        onChange={(v) => setDraft(col.key, { to: v })}
                    />
                </Space.Compact>
            );
        }
        if (kind === "date" || kind === "datetime") {
            return (
                <DatePicker.RangePicker
                    style={{ width: "100%" }}
                    format="DD.MM.YYYY"
                    value={d.range}
                    onChange={(range: any) => setDraft(col.key, { range })}
                />
            );
        }
        if (kind === "bool") {
            return (
                <Select
                    allowClear
                    placeholder="Все"
                    style={{ width: "100%" }}
                    value={d.bool}
                    onChange={(v) => setDraft(col.key, { bool: v })}
                    options={[
                        { value: true, label: "Да" },
                        { value: false, label: "Нет" },
                    ]}
                />
            );
        }
        if (kind === "select") {
            const resourceOptions = getResourceSelectOptions(resourceName, col.key);
            const options =
                resourceOptions.length > 0
                    ? resourceOptions
                    : isReferenceFilter(col.key)
                      ? []
                      : getSelectOptions(col.key).map((o) => ({
                            value: o.value,
                            label: o.label,
                        }));
            if (isReferenceFilter(col.key)) {
                const refSource = getReferenceSource(col.key);
                if (refSource) {
                    return (
                        <ReferenceFilterSelect
                            source={refSource}
                            value={d.sel}
                            onChange={(v: any) => setDraft(col.key, { sel: v })}
                        />
                    );
                }
            }
            return (
                <Select
                    allowClear
                    placeholder="Выбрать…"
                    style={{ width: "100%" }}
                    value={d.sel}
                    onChange={(v) => setDraft(col.key, { sel: v })}
                    options={options}
                />
            );
        }
        return null;
    };

    const handleSubmit = (values: Record<string, any>) => {
        if (modalState?.mode === "create") {
            createRecord(
                { resource: resourceName, values },
                {
                    onSuccess: () => {
                        message.success("Запись добавлена");
                        setModalState(null);
                        tableQuery.refetch();
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
                        tableQuery.refetch();
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
        {
            title: "ID",
            dataIndex: "id",
            key: "id",
            width: widths["id"] ?? 70,
            sorter: true,
            sortOrder: getColumnSortOrder('id'),
            onHeaderCell: () => headerResizeProps("id", setWidth),
            // Сортировка по умолчанию — на «Периоде» (см. выше); стрелку на ID не ставим.
            ...(defaultSortDescPeriod ? {} : { defaultSortOrder: 'descend' as const }),
        },
        ...displayColumns.map((col) => {
            const sortable = isSortableField(col.key);
            const isNested = col.key.includes('.');
            return {
                title: <ColumnDragTitle columnKey={col.key}>{col.label}</ColumnDragTitle>,
                dataIndex: col.key,
                key: col.key,
                width: widths[col.key],
                render: (value: any, record: any) => {
                    try {
                        const val = isNested ? getValueByPath(record, col.key) : value;
                        return col.format ? col.format(val) : val ?? "—";
                    } catch {
                        return "—";
                    }
                },
                sorter: sortable,
                sortOrder: getColumnSortOrder(col.key),
                onHeaderCell: () => ({
                    ...headerResizeProps(col.key, setWidth),
                    ...(sortable
                        ? { style: { cursor: 'pointer' }, title: 'Кликните для сортировки' }
                        : {}),
                }),
                // Подсветка сортировки по умолчанию для регистра начислений.
                ...(defaultSortDescPeriod && col.key === 'accrual_date'
                    ? { defaultSortOrder: 'descend' as const }
                    : {}),
            };
        }),
        ...(isRegister || !roleCanWrite
            ? []
            : [
                  {
                      title: "Действия",
                      key: "actions",
                      width: 200,
                      fixed: 'right' as const,
                      render: (_: unknown, record: any) => {
                          if (isWriteoffDocuments) {
                              return (
                                  <Space>
                                      <Button
                                          size="small"
                                          onClick={() => setWriteoffViewId(record.id)}
                                      >
                                          Просмотр
                                      </Button>
                                      {roleCanEdit && record.status === "new" && (
                                          <Popconfirm
                                              title="Отменить документ списания? Записи регистра будут удалены, балансы пересчитаны."
                                              okText="Отменить"
                                              cancelText="Закрыть"
                                              onConfirm={() => cancelWriteoffDoc(record.id)}
                                          >
                                              <Button size="small" danger>
                                                  Отменить
                                              </Button>
                                          </Popconfirm>
                                      )}
                                  </Space>
                              );
                          }

                          if (isReceiptDocuments) {
                              return (
                                  <Space>
                                      <Button
                                          size="small"
                                          onClick={() => setReceiptViewId(record.id)}
                                      >
                                          Просмотр
                                      </Button>
                                      <Button
                                          size="small"
                                          onClick={() =>
                                              openAuthorizedPdf(
                                                  `${apiUrl}/receipt_documents/${record.id}/pdf`,
                                                  `receipt_${record.id}.pdf`,
                                              )
                                          }
                                      >
                                          PDF
                                      </Button>
                                      {roleCanDelete && (
                                      <Popconfirm
                                          title="Удалить квитанцию?"
                                          okText="Удалить"
                                          cancelText="Отмена"
                                          onConfirm={() =>
                                              deleteRecord(
                                                  { resource: resourceName, id: record.id },
                                                  {
                                                      onSuccess: () => message.success("Квитанция удалена"),
                                                      onError: (err: any) =>
                                                          message.error(
                                                              err?.response?.data?.detail ??
                                                              "Не удалось удалить квитанцию",
                                                          ),
                                                  },
                                              )
                                          }
                                      >
                                          <Button size="small" danger>
                                              Удалить
                                          </Button>
                                      </Popconfirm>
                                      )}
                                  </Space>
                              );
                          }

                          if (isAccrualDocuments) {
                              const isOneOff = record.doc_kind === 'oneoff';
                              return (
                                  <Space>
                                      {roleCanEdit && (
                                      <Button
                                          size="small"
                                          onClick={() => {
                                              setEditingAccrualDocumentId(record.id);
                                              if (isOneOff) {
                                                  setOneOffAccrualsOpen(true);
                                              } else {
                                                  setAccrualsModalOpen(true);
                                              }
                                          }}
                                      >
                                          Редактировать
                                      </Button>
                                      )}
                                      {roleCanDelete && (
                                      <Popconfirm
                                          title="Удалить документ начислений? Все связанные записи в регистре начислений также будут удалены."
                                          okText="Удалить"
                                          cancelText="Отмена"
                                          onConfirm={() =>
                                              deleteRecord(
                                                  { resource: resourceName, id: record.id },
                                                  {
                                                      onSuccess: () => {
                                                          message.success("Документ начислений удален");
                                                          tableQuery.refetch();
                                                      },
                                                      onError: (err: any) =>
                                                          message.error(
                                                              err?.response?.data?.detail ??
                                                              "Не удалось удалить документ",
                                                          ),
                                                  },
                                              )
                                          }
                                      >
                                          <Button size="small" danger>
                                              Удалить
                                          </Button>
                                      </Popconfirm>
                                      )}
                                  </Space>
                              );
                          }

                          if (isMeterReadingDocuments) {
                              return (
                                  <Space>
                                      {roleCanEdit && (
                                      <Button
                                          size="small"
                                          onClick={() => {
                                              setEditingMeterReadingDocumentId(record.id);
                                              setBulkModalOpen(true);
                                          }}
                                      >
                                          Редактировать
                                      </Button>
                                      )}
                                      {roleCanDelete && (
                                      <Popconfirm
                                          title="Удалить документ показаний? Все связанные показания также будут удалены."
                                          okText="Удалить"
                                          cancelText="Отмена"
                                          onConfirm={() =>
                                              deleteRecord(
                                                  { resource: resourceName, id: record.id },
                                                  {
                                                      onSuccess: () => {
                                                          message.success("Документ показаний удален");
                                                          tableQuery.refetch();
                                                      },
                                                      onError: (err: any) =>
                                                          message.error(
                                                              err?.response?.data?.detail ??
                                                              "Не удалось удалить документ",
                                                          ),
                                                  },
                                              )
                                          }
                                      >
                                          <Button size="small" danger>
                                              Удалить
                                          </Button>
                                      </Popconfirm>
                                      )}
                                  </Space>
                              );
                          }

                          if (!isReadOnly) {
                              return (
                                  <Space>
                                      {roleCanEdit && (
                                      <Button
                                          size="small"
                                          onClick={() => setModalState({ mode: "edit", record })}
                                      >
                                          Редактировать
                                      </Button>
                                      )}
                                      {roleCanDelete && (
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
                                      )}
                                  </Space>
                              );
                          }
                      },
                  },
              ]),
    ];

    return (
        <div
            style={{
                background: "#ffffff",
                border: `1px solid ${BRAND.fade}`,
                boxShadow: "0 1px 3px rgba(34,174,46,0.06)",
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
                <h1 style={{ color: "#14501d", margin: 0 }}>
                    {meta?.label ?? resourceName}
                </h1>
                <Space>
                    <Popover
                        trigger="click"
                        open={filtersOpen}
                        onOpenChange={(open) => setFiltersOpen(open)}
                        placement="bottomRight"
                        content={
                            <div style={{ width: 540 }}>
                                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: "#666" }}>
                                    Фильтры
                                </div>
                                <div style={{ maxHeight: 360, overflow: "auto" }}>
                                    {displayColumns
                                        .filter((col) => isSortableField(col.key))
                                        .map((col) => (
                                            <div
                                                key={col.key}
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: 8,
                                                    marginBottom: 8,
                                                }}
                                            >
                                                <div style={{ width: 170, flexShrink: 0, fontSize: 13 }}>
                                                    {col.label}
                                                </div>
                                                <div style={{ flex: 1 }}>
                                                    {renderFilterControl(col)}
                                                </div>
                                            </div>
                                        ))}
                                </div>
                                <Space style={{ marginTop: 8, width: "100%", justifyContent: "flex-end" }}>
                                    <Button size="small" onClick={resetFilters}>
                                        Сбросить
                                    </Button>
                                    <Button size="small" type="primary" onClick={applyFilters}>
                                        Применить
                                    </Button>
                                </Space>
                            </div>
                        }
                    >
                        <Button>
                            Фильтры{appliedCount > 0 ? ` (${appliedCount})` : ""}
                        </Button>
                    </Popover>
                    {columns.length > 0 && (
                        <Popover
                            trigger="click"
                            placement="bottomRight"
                            content={
                                <div style={{ width: 300, maxHeight: 360, overflow: "auto" }}>
                                    <div
                                        style={{
                                            fontSize: 13,
                                            fontWeight: 600,
                                            marginBottom: 8,
                                            color: "#666",
                                        }}
                                    >
                                        Отображаемые колонки (перетащите для порядка)
                                    </div>
                                    <SortableColumns
                                        items={orderedAll.map((k) => ({
                                            key: k,
                                            label: columnByKey.get(k)?.label ?? k,
                                            checked: !hiddenKeys.has(k),
                                        }))}
                                        onToggle={toggle}
                                        onMove={move}
                                    />
                                </div>
                            }
                        >
                            <Button>Колонки</Button>
                        </Popover>
                    )}

                    {isMeterReadingDocuments && roleCanCreate && (
                        <Button
                            type="primary"
                            onClick={() => {
                                setEditingMeterReadingDocumentId(undefined);
                                setBulkModalOpen(true);
                            }}
                        >
                            Добавить
                        </Button>
                    )}

                    {isReceiptDocuments && (
                        <Button
                            type="primary"
                            onClick={() => setReceiptsModalOpen(true)}
                        >
                            Сформировать квитанции
                        </Button>
                    )}

                    {isAccrualDocuments && (
                        <Button
                            type="primary"
                            onClick={() => {
                                setEditingAccrualDocumentId(undefined);
                                setAccrualsModalOpen(true);
                            }}
                        >
                            Добавить
                        </Button>
                    )}

                    {isWriteoffDocuments && (role === "admin" || role === "operator") && (
                        <Button
                            type="primary"
                            onClick={() => setWriteOffsModalOpen(true)}
                        >
                            Выполнить списание
                        </Button>
                    )}

                    {roleCanCreate && !isReadOnly && !isAccrualsRegister && !isAccrualDocuments && !isMeterReadingDocuments && !isMeterReadings && !isReceiptDocuments && !isWriteoffDocuments && (
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

            <DndContext
                sensors={headerSensors}
                collisionDetection={closestCenter}
                onDragEnd={handleHeaderDragEnd}
            >
                <SortableContext
                    items={displayColumns.map((c) => c.key)}
                >
                    <Table
                        rowKey="id"
                        dataSource={data}
                        columns={tableColumns}
                        components={tableHeaderComponents}
                        loading={tableQuery.isLoading}
                        onChange={handleTableChange}
                        pagination={{
                            current,
                            pageSize,
                            total,
                            showSizeChanger: true,
                            showTotal: (total) => `Всего ${total} записей`,
                            onChange: (page, size) => {
                                setCurrent(page);
                                if (size) setPageSize(size);
                            },
                        }}
                        scroll={{ x: 'max-content' }}
                    />
                </SortableContext>
            </DndContext>

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
                    resourceName={resourceName}
                />
            )}

            {isMeterReadingDocuments && (
                <BulkReadingsModal
                    open={bulkModalOpen}
                    documentId={editingMeterReadingDocumentId}
                    onClose={() => {
                        setBulkModalOpen(false);
                        setEditingMeterReadingDocumentId(undefined);
                    }}
                    onSaved={() => tableQuery.refetch()}
                />
            )}

            {isAccrualDocuments && (
                <>
                    <AccrualsCalculationModal
                        open={accrualsModalOpen}
                        documentId={editingAccrualDocumentId}
                        onClose={() => {
                            setAccrualsModalOpen(false);
                            setEditingAccrualDocumentId(undefined);
                        }}
                        onSaved={() => tableQuery.refetch()}
                    />
                    <OneOffAccrualsEditModal
                        open={oneOffAccrualsOpen}
                        documentId={editingAccrualDocumentId}
                        onClose={() => {
                            setOneOffAccrualsOpen(false);
                            setEditingAccrualDocumentId(undefined);
                        }}
                        onSaved={() => tableQuery.refetch()}
                    />
                </>
            )}

            {isReceiptDocuments && (
                <ReceiptViewModal
                    open={receiptViewId !== undefined}
                    receiptId={receiptViewId}
                    onClose={() => setReceiptViewId(undefined)}
                />
            )}

            {isReceiptDocuments && (
                <ReceiptsModal
                    open={receiptsModalOpen}
                    onClose={() => setReceiptsModalOpen(false)}
                    onSaved={() => tableQuery.refetch()}
                />
            )}

            {isWriteoffDocuments && (
                <WriteoffViewModal
                    open={writeoffViewId !== undefined}
                    documentId={writeoffViewId}
                    onClose={() => setWriteoffViewId(undefined)}
                />
            )}

            {isWriteoffDocuments && (
                <WriteOffsModal
                    open={writeOffsModalOpen}
                    onClose={() => setWriteOffsModalOpen(false)}
                    onSaved={() => tableQuery.refetch()}
                />
            )}
        </div>
    );
};
