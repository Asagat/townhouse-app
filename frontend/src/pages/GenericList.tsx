// src/pages/GenericList.tsx

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dayjs from "dayjs";
import {
    Table,
    Button,
    Space,
    Popconfirm,
    Popover,
    Tooltip,
    Badge,
    Input,
    InputNumber,
    Select,
    DatePicker,
    message,
} from "antd";
import {
    AccountBookOutlined,
    DeleteOutlined,
    EditOutlined,
    EyeOutlined,
    FileAddOutlined,
    FilePdfOutlined,
    FilterOutlined,
    PlusOutlined,
    TableOutlined,
    UndoOutlined,
} from "@ant-design/icons";
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
import type { CrudFilter, CrudSort } from "@refinedev/core";
import {
    fetchServerPrefs,
    pushServerPref,
    readPrefsCache,
    writePrefsCache,
    type ListSettings,
    type PrefsMap,
    type StoredColumnSettings,
} from "../auth/preferences";
import { getColumnsForResource } from "../config/columns";
import { allResources } from "../config/menu";
import {
    getDefaultResourceFilters,
    getFilterKind,
    getReferenceSource,
    getResourceSelectOptions,
    getSelectOptions,
    isResourceDynamicSelect,
    isResourceReferenceFilter,
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
import { openAuthorizedPdf, authedFetch } from "../auth/http";

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

/** Вид фильтра по колонке (глобальная карта + ресурсо-зависимые select-поля). */
const kindForColumn = (resourceName: string, key: string) =>
    isResourceSelectFilter(resourceName, key) ||
    isResourceDynamicSelect(resourceName, key) ||
    isResourceReferenceFilter(resourceName, key)
        ? "select"
        : getFilterKind(key);

/**
 * Восстанавливает черновик панели «Фильтры» из применённого CrudFilter-списка
 * (для показа активных фильтров после перезагрузки/сохранённых настроек).
 */
const draftFromCrudFilters = (resourceName: string, filters: CrudFilter[]) => {
    const draft: Record<string, any> = {};
    for (const f of filters) {
        if (!f.field) continue;
        const kind = kindForColumn(resourceName, String(f.field));
        const prev = draft[f.field] ?? {};
        if (f.operator === "contains") {
            draft[f.field] = { ...prev, text: String(f.value ?? "") };
        } else if (f.operator === "eq") {
            if (kind === "bool") {
                draft[f.field] = { ...prev, bool: !!f.value };
            } else {
                draft[f.field] = { ...prev, sel: f.value };
            }
        } else if (f.operator === "gte" || f.operator === "lte") {
            if (kind === "date" || kind === "datetime") {
                const d = dayjs(String(f.value));
                const range = [...(prev.range ?? [null, null])] as [any, any];
                if (f.operator === "gte") range[0] = d;
                else range[1] = d;
                draft[f.field] = { ...prev, range };
            } else {
                const num = Number(f.value);
                if (f.operator === "gte") draft[f.field] = { ...prev, from: num };
                else draft[f.field] = { ...prev, to: num };
            }
        }
    }
    return draft;
};

export const GenericList = ({ resourceName }: GenericListProps) => {
    const apiUrl = useApiUrl();

    const { data: identity } = useGetIdentity<any>();

    // --- Настройки пользователя (2.13): сервер + локальный кэш по (пользователь, ресурс) ---
    const username = identity?.username ?? "";
    const [prefs, setPrefs] = useState<PrefsMap>(() => readPrefsCache(username));
    const savedPrefs = prefs[resourceName];
    const pushTimerRef = useRef<number | null>(null);

    const prefsFingerprint = (b: ListSettings | undefined) =>
        JSON.stringify([b?.sorters ?? null, b?.filters ?? null, b?.pageSize ?? null]);
    const appliedFpRef = useRef<string>(prefsFingerprint(savedPrefs));

    const schedulePrefPush = useCallback((resource: string, data: ListSettings) => {
        if (pushTimerRef.current !== null) window.clearTimeout(pushTimerRef.current);
        pushTimerRef.current = window.setTimeout(() => {
            pushTimerRef.current = null;
            void pushServerPref(resource, data);
        }, 1200);
    }, []);

    const patchPrefs = useCallback(
        (partial: Partial<ListSettings>) => {
            setPrefs((prev) => {
                const bundle = { ...(prev[resourceName] ?? {}), ...partial };
                const next = { ...prev, [resourceName]: bundle };
                writePrefsCache(username, next);
                schedulePrefPush(resourceName, bundle);
                return next;
            });
        },
        [username, resourceName, schedulePrefPush],
    );

    // Регистр начислений: свежие периоды сверху (иначе первыми идут «входящие остатки»
    // стартовых долгов — они добавлены позже всех и стоят в конце по id).
    const defaultSortDescPeriod = resourceName === "accruals_register";
    const initialSortField = defaultSortDescPeriod ? "accrual_date" : "id";

    // Фильтры по умолчанию для раздела (например «Тарифы» — только «Действующие»),
    // если у пользователя нет сохранённых настроек этого раздела.
    const resourceDefaults = getDefaultResourceFilters(resourceName);
    const defaultCrudFilters = (resourceDefaults?.applied ?? []) as CrudFilter[];

    const initialSorters = (savedPrefs?.sorters?.length
        ? savedPrefs.sorters
        : [{ field: initialSortField, order: "desc" }]) as CrudSort[];
    const initialFilters =
        savedPrefs?.filters !== undefined
            ? (savedPrefs.filters as CrudFilter[])
            : defaultCrudFilters;
    const initialPageSize = savedPrefs?.pageSize ?? 10;

    const {
        tableQuery,
        current,
        setCurrent,
        pageSize,
        setPageSize,
        sorters,
        setSorters,
        filters,
        setFilters,
    } = useTable({
        resource: resourceName,
        pagination: {
            current: 1,
            pageSize: initialPageSize,
        },
        sorters: {
            initial: initialSorters,
        },
        filters: {
            initial: initialFilters,
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
    // ресурса (роуты обычно дают key, но страхуемся), сбрасываем локальное состояние.
    // Применение сохранённых настроек нового раздела выполняет fingerprint-эффект.
    useEffect(() => {
        appliedFpRef.current = "";
        setDraftFilters({});
        setAppliedCount(0);
        setFilters([], "replace");
    }, [resourceName]);

    // --- Общий механизм фильтрации (Б10) ---
    // Черновик фильтров по колонкам списка; применяется серверно через setFilters.
    const [filtersOpen, setFiltersOpen] = useState(false);
    const [draftFilters, setDraftFilters] = useState<Record<string, any>>(() => {
        const saved = prefs[resourceName];
        if (saved?.filters !== undefined) {
            return draftFromCrudFilters(resourceName, saved.filters as CrudFilter[]);
        }
        return getDefaultResourceFilters(resourceName)?.draft ?? {};
    });
    const [appliedCount, setAppliedCount] = useState(() => {
        const saved = prefs[resourceName];
        const def = getDefaultResourceFilters(resourceName);
        const crud = saved?.filters !== undefined ? saved.filters : def?.applied ?? [];
        return crud.length;
    });
    const [bulkModalOpen, setBulkModalOpen] = useState(false);
    const [editingMeterReadingDocumentId, setEditingMeterReadingDocumentId] = useState<number | undefined>(undefined);
    const [accrualsModalOpen, setAccrualsModalOpen] = useState(false);
    const [editingAccrualDocumentId, setEditingAccrualDocumentId] = useState<number | undefined>(undefined);
    // true — модалки документов открыты в режиме «просмотр» (read-only).
    const [docReadOnly, setDocReadOnly] = useState(false);
    const [oneOffAccrualsOpen, setOneOffAccrualsOpen] = useState(false);
    const [receiptsModalOpen, setReceiptsModalOpen] = useState(false);
    const [receiptViewId, setReceiptViewId] = useState<number | undefined>(undefined);
    const [writeOffsModalOpen, setWriteOffsModalOpen] = useState(false);
    const [writeoffViewId, setWriteoffViewId] = useState<number | undefined>(undefined);

    // Границы годов фильтра «Год» списка квитанций (сервер: /receipt_documents/periods):
    // от самого раннего года записей (квитанции или входящие остатки начислений)
    // до текущего года. Пока не пришли — доступен только текущий год.
    const [receiptYearRange, setReceiptYearRange] = useState<{
        min_year: number;
        max_year: number;
    } | null>(null);
    useEffect(() => {
        if (resourceName !== "receipt_documents") return;
        let cancelled = false;
        authedFetch(`${apiUrl}/receipt_documents/periods`)
            .then((resp) => (resp.ok ? resp.json() : null))
            .then((data) => {
                if (!cancelled && data && Number.isFinite(data.min_year) && Number.isFinite(data.max_year)) {
                    setReceiptYearRange(data);
                }
            })
            .catch(() => {
                // Некритично: остаётся диапазон по умолчанию (текущий год).
            });
        return () => {
            cancelled = true;
        };
    }, [resourceName, apiUrl]);

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
    // Есть ли у роли хоть какое-то действие записи (иначе выбор строки/панель действий скрыты).
    const roleCanWrite = roleCanCreate || roleCanEdit || roleCanDelete;

    // --- Выделенная запись (2.12): действия записи — из панели над списком ---
    const [selectedRowKey, setSelectedRowKey] = useState<string | number | null>(null);
    const selectedRecord = data.find((r) => r.id === selectedRowKey) ?? null;

    // Если выделенная запись исчезла из данных (удалена/другая страница) — снимаем выбор.
    useEffect(() => {
        if (selectedRowKey != null && !data.some((r) => r.id === selectedRowKey)) {
            setSelectedRowKey(null);
        }
    }, [data, selectedRowKey]);

    const columns = getColumnsForResource(resourceName);
    const meta = allResources.find((r) => r.key === resourceName);

    // Вариант A + C (п. 2.10) + ширины (2.1): видимость/порядок/ширины колонок.
    // Настройки хранятся на сервере + в локальном кэше (2.13), применяются сразу.
    const { orderedAll, hiddenKeys, widths, toggle, move, moveKey, setWidth } =
        useColumnSettings(
            columns.map((c) => c.key),
            savedPrefs?.columns ?? null,
            (next: StoredColumnSettings) => patchPrefs({ columns: next }),
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

    // --- Синхронизация настроек пользователя (2.13) ---
    // При появлении пользователя читаем локальный кэш и тянем настройки с сервера
    // (сервер — источник правды: настройки переживают смену устройства).
    const prefsReadyRef = useRef(false);
    useEffect(() => {
        if (!username) return;
        prefsReadyRef.current = false;
        setPrefs(readPrefsCache(username));
        let cancelled = false;
        fetchServerPrefs().then((server) => {
            if (cancelled) return;
            setPrefs((prev) => {
                const next = { ...prev, ...server };
                writePrefsCache(username, next);
                return next;
            });
            prefsReadyRef.current = true;
        });
        return () => {
            cancelled = true;
        };
    }, [username]);

    // Применяем сохранённые настройки раздела к таблице (если они изменились,
    // например пришли с сервера или сменился пользователь/раздел).
    useEffect(() => {
        const bundle = prefs[resourceName];
        const fp = prefsFingerprint(bundle);
        if (appliedFpRef.current === fp) return;
        appliedFpRef.current = fp;
        if (!bundle) return;
        if (bundle.sorters !== undefined) {
            setSorters(bundle.sorters as CrudSort[]);
        }
        if (bundle.filters !== undefined) {
            setFilters(bundle.filters as CrudFilter[], "replace");
            setAppliedCount(bundle.filters.length);
            setDraftFilters(draftFromCrudFilters(resourceName, bundle.filters as CrudFilter[]));
        }
        if (bundle.pageSize) setPageSize(bundle.pageSize);
    }, [prefs, resourceName]);

    // Персистим изменения сортировки/фильтров/размера страницы (на сервер — с debounce).
    useEffect(() => {
        if (!username || !prefsReadyRef.current) return;
        patchPrefs({
            sorters: (sorters ?? []) as ListSettings["sorters"],
            filters: (filters ?? []) as ListSettings["filters"],
            pageSize,
        });
        // patchPrefs намеренно не в зависимостях — он стабилен для (username, resourceName)
        // и пересоздаётся только при их смене (тогда сработает эффект [username]/сброс).
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [sorters, filters, pageSize]);

    // «По умолчанию — последняя страница»: при сортировке по возрастанию (дата/любое
    // поле) список открывается в конце, где последние записи (один раз за открытие).
    const autoLastPageRef = useRef(false);
    useEffect(() => {
        if (autoLastPageRef.current) return;
        const total = tableQuery?.data?.total;
        if (!total || total <= 0) return;
        autoLastPageRef.current = true;
        const sorter = sorters?.[0];
        if (sorter?.order !== "asc") return;
        const lastPage = Math.ceil(total / pageSize);
        if (lastPage > 1 && current === 1) {
            setCurrent(lastPage);
        }
        // Реагируем на появление данных и применение сохранённой сортировки (prefs).
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [tableQuery?.data?.total, sorters]);

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
    // (например «Статус» у тарифов — Действующий/Архивный, «Год» квитанций —
    // динамический select от первого года записей до текущего, «Автор» и «Лицевой
    // счёт» квитанций — справочные select).
    const getColumnKind = (key: string) =>
        isResourceSelectFilter(resourceName, key) ||
        isResourceDynamicSelect(resourceName, key) ||
        isResourceReferenceFilter(resourceName, key)
            ? "select"
            : getFilterKind(key);

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

    // Варианты фильтра «Год»: от первого года с записями до текущего (свежие сверху).
    const yearOptions = useMemo(() => {
        const nowYear = new Date().getFullYear();
        const minY = receiptYearRange?.min_year ?? nowYear;
        const maxY = Math.max(receiptYearRange?.max_year ?? nowYear, nowYear);
        const opts: Array<{ value: number; label: string }> = [];
        for (let y = maxY; y >= minY; y -= 1) opts.push({ value: y, label: String(y) });
        return opts;
    }, [receiptYearRange]);

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
            // Справочный фильтр (значения из того же справочника, что и колонка):
            // «Автор» — из пользователей, «Лицевой счёт» квитанций — из счетов и т.п.
            const refSource = getReferenceSource(resourceName, col.key);
            if (refSource) {
                return (
                    <ReferenceFilterSelect
                        source={refSource}
                        value={d.sel}
                        onChange={(v: any) => setDraft(col.key, { sel: v })}
                    />
                );
            }
            // «Год» квитанций: динамический диапазон (первый год записей … текущий).
            const dynamicOptions =
                isResourceDynamicSelect(resourceName, col.key) && col.key === "period_year"
                    ? yearOptions
                    : [];
            const resourceOptions = getResourceSelectOptions(resourceName, col.key);
            const options =
                dynamicOptions.length > 0
                    ? dynamicOptions
                    : resourceOptions.length > 0
                      ? resourceOptions
                      : getSelectOptions(col.key).map((o) => ({
                            value: o.value,
                            label: o.label,
                        }));
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

    // --- Панель действий выбранной записи (2.12): кнопки-иконки с tooltip (Б7) ---
    // Стиль как у «Удалить»: белый фон + цветной акцент. «Просмотр» и «Редактировать»
    // — в одном цвете (зелёный акцент, по решению владельца), «Удалить» — красный.
    const iconButton = (
        key: string,
        label: string,
        icon: React.ReactNode,
        onClick?: () => void,
        accentColor?: string,
    ) => (
        <Tooltip key={key} title={label}>
            <Button
                icon={icon}
                onClick={onClick}
                style={
                    accentColor
                        ? { color: accentColor, borderColor: accentColor }
                        : undefined
                }
            />
        </Tooltip>
    );

    const deleteButton = (key: string, label: string, confirmTitle: string, onOk: () => void) => (
        <Tooltip key={key} title={label}>
            <Popconfirm title={confirmTitle} okText="Удалить" cancelText="Отмена" onConfirm={onOk}>
                <Button danger icon={<DeleteOutlined />} />
            </Popconfirm>
        </Tooltip>
    );

    const errMsg = (err: any, fallback: string) => err?.response?.data?.detail ?? fallback;

    const renderRecordActions = (record: any): React.ReactNode => {
        if (isWriteoffDocuments) {
            return (
                <Space>
                    {iconButton("view", "Просмотр", <EyeOutlined />, () => setWriteoffViewId(record.id), "#22ae2e")}
                    {roleCanEdit && record.status === "new" && (
                        <Tooltip key="cancel" title="Отменить документ">
                            <Popconfirm
                                title="Отменить документ списания? Записи регистра будут удалены, балансы пересчитаны."
                                okText="Отменить"
                                cancelText="Закрыть"
                                onConfirm={() => cancelWriteoffDoc(record.id)}
                            >
                                <Button danger icon={<UndoOutlined />} />
                            </Popconfirm>
                        </Tooltip>
                    )}
                </Space>
            );
        }
        if (isReceiptDocuments) {
            return (
                <Space>
                    {iconButton("view", "Просмотр", <EyeOutlined />, () => setReceiptViewId(record.id), "#22ae2e")}
                    {iconButton("pdf", "PDF", <FilePdfOutlined />, () =>
                        openAuthorizedPdf(
                            `${apiUrl}/receipt_documents/${record.id}/pdf`,
                            `receipt_${record.id}.pdf`,
                        ),
                    )}
                    {roleCanDelete &&
                        deleteButton("del", "Удалить", "Удалить квитанцию?", () =>
                            deleteRecord(
                                { resource: resourceName, id: record.id },
                                {
                                    onSuccess: () => message.success("Квитанция удалена"),
                                    onError: (err: any) => message.error(errMsg(err, "Не удалось удалить квитанцию")),
                                },
                            ),
                        )}
                </Space>
            );
        }
        if (isAccrualDocuments) {
            const isOneOff = record.doc_kind === "oneoff";
            const openDoc = (readOnly: boolean) => {
                setDocReadOnly(readOnly);
                setEditingAccrualDocumentId(record.id);
                if (isOneOff) setOneOffAccrualsOpen(true);
                else setAccrualsModalOpen(true);
            };
            return (
                <Space>
                    {iconButton("view", "Просмотр", <EyeOutlined />, () => openDoc(true), "#22ae2e")}
                    {roleCanEdit &&
                        iconButton("edit", "Редактировать", <EditOutlined />, () => openDoc(false), "#22ae2e")}
                    {roleCanDelete &&
                        deleteButton("del", "Удалить", "Удалить документ начислений? Все связанные записи регистра будут удалены.", () =>
                            deleteRecord(
                                { resource: resourceName, id: record.id },
                                {
                                    onSuccess: () => {
                                        message.success("Документ начислений удален");
                                        tableQuery.refetch();
                                    },
                                    onError: (err: any) => message.error(errMsg(err, "Не удалось удалить документ")),
                                },
                            ),
                        )}
                </Space>
            );
        }
        if (isMeterReadingDocuments) {
            const openDoc = (readOnly: boolean) => {
                setDocReadOnly(readOnly);
                setEditingMeterReadingDocumentId(record.id);
                setBulkModalOpen(true);
            };
            return (
                <Space>
                    {iconButton("view", "Просмотр", <EyeOutlined />, () => openDoc(true), "#22ae2e")}
                    {roleCanEdit &&
                        iconButton("edit", "Редактировать", <EditOutlined />, () => openDoc(false), "#22ae2e")}
                    {roleCanDelete &&
                        deleteButton("del", "Удалить", "Удалить документ показаний? Все связанные показания будут удалены.", () =>
                            deleteRecord(
                                { resource: resourceName, id: record.id },
                                {
                                    onSuccess: () => {
                                        message.success("Документ показаний удален");
                                        tableQuery.refetch();
                                    },
                                    onError: (err: any) => message.error(errMsg(err, "Не удалось удалить документ")),
                                },
                            ),
                        )}
                </Space>
            );
        }
        if (!isReadOnly) {
            return (
                <Space>
                    {iconButton("view", "Просмотр", <EyeOutlined />, () => setModalState({ mode: "view", record }), "#22ae2e")}
                    {roleCanEdit &&
                        iconButton("edit", "Редактировать", <EditOutlined />, () => setModalState({ mode: "edit", record }), "#22ae2e")}
                    {roleCanDelete &&
                        deleteButton("del", "Удалить", "Удалить запись?", () =>
                            deleteRecord(
                                { resource: resourceName, id: record.id },
                                {
                                    onSuccess: () => message.success("Запись удалена"),
                                    onError: (err: any) => message.error(errMsg(err, "Не удалось удалить запись")),
                                },
                            ),
                        )}
                </Space>
            );
        }
        return null;
    };

    // Кнопка создания новой записи выносится в левую панель действий записи.
    const canCreateRecord =
        roleCanCreate &&
        !isReadOnly &&
        !isAccrualsRegister &&
        !isAccrualDocuments &&
        !isMeterReadingDocuments &&
        !isMeterReadings &&
        !isReceiptDocuments &&
        !isWriteoffDocuments;

    // Колонка выбора строки нужна только там, где для записи есть действия.
    const canUseSelection =
        !isRegister &&
        (isWriteoffDocuments ||
            isReceiptDocuments ||
            isAccrualDocuments ||
            isMeterReadingDocuments ||
            roleCanWrite);

    const tableColumns = [
        {
            title: "ID",
            dataIndex: "id",
            key: "id",
            width: widths["id"] ?? 70,
            sorter: true,
            sortOrder: getColumnSortOrder('id'),
            // Без всплывающей подсказки сортировки: оверлей antd над заголовком
            // перекрывает кнопки панели записи (например «Просмотр») над таблицей.
            showSorterTooltip: false,
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
                // Без всплывающей подсказки сортировки: оверлей antd над заголовком
                // перекрывает кнопки панели записи над таблицей.
                showSorterTooltip: false,
                onHeaderCell: () => ({
                    ...headerResizeProps(col.key, setWidth),
                    ...(sortable ? { style: { cursor: 'pointer' } } : {}),
                }),
                // Подсветка сортировки по умолчанию для регистра начислений.
                ...(defaultSortDescPeriod && col.key === 'accrual_date'
                    ? { defaultSortOrder: 'descend' as const }
                    : {}),
            };
        }),
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
                    alignItems: "flex-start",
                    gap: 16,
                    marginBottom: 20,
                }}
            >
                <div style={{ minWidth: 0 }}>
                    <h1 style={{ color: "#14501d", margin: 0 }}>
                        {meta?.label ?? resourceName}
                    </h1>
                    {(canUseSelection ||
                        canCreateRecord ||
                        (isMeterReadingDocuments && roleCanCreate) ||
                        isAccrualDocuments) && (
                        <div
                            style={{
                                marginTop: 10,
                                display: "flex",
                                alignItems: "center",
                                gap: 8,
                                flexWrap: "wrap",
                            }}
                        >
                            {canCreateRecord && (
                                <Tooltip title="Добавить">
                                    <Button
                                        type="primary"
                                        disabled={metaLoading}
                                        icon={<PlusOutlined />}
                                        onClick={() => setModalState({ mode: "create" })}
                                    />
                                </Tooltip>
                            )}
                            {isMeterReadingDocuments && roleCanCreate && (
                                <Tooltip title="Массовый ввод показаний">
                                    <Button
                                        type="primary"
                                        icon={<EditOutlined />}
                                        onClick={() => {
                                            setDocReadOnly(false);
                                            setEditingMeterReadingDocumentId(undefined);
                                            setBulkModalOpen(true);
                                        }}
                                    />
                                </Tooltip>
                            )}
                            {isAccrualDocuments && (
                                <Tooltip title="Новое начисление">
                                    <Button
                                        type="primary"
                                        icon={<PlusOutlined />}
                                        onClick={() => {
                                            setDocReadOnly(false);
                                            setEditingAccrualDocumentId(undefined);
                                            setAccrualsModalOpen(true);
                                        }}
                                    />
                                </Tooltip>
                            )}
                            {canUseSelection &&
                                (selectedRecord ? (
                                    <>
                                        {renderRecordActions(selectedRecord)}
                                        <span style={{ color: "#888", fontSize: 12, marginLeft: 4 }}>
                                            Запись № {selectedRecord?.id ?? ""}
                                        </span>
                                    </>
                                ) : (
                                    <Space>
                                        <Tooltip title="Просмотр">
                                            <Button icon={<EyeOutlined />} disabled />
                                        </Tooltip>
                                        {roleCanEdit && (
                                            <Tooltip title="Редактировать">
                                                <Button icon={<EditOutlined />} disabled />
                                            </Tooltip>
                                        )}
                                        {roleCanDelete && (
                                            <Tooltip title="Удалить">
                                                <Button icon={<DeleteOutlined />} danger disabled />
                                            </Tooltip>
                                        )}
                                    </Space>
                                ))}
                        </div>
                    )}
                </div>
                <Space wrap style={{ flexShrink: 0 }}>
                    {/* Сортировка (2.12): выбор колонки + направление */}
                    <Select
                        allowClear
                        placeholder="Сортировка"
                        style={{ width: 170 }}
                        value={sorters?.[0]?.field}
                        onChange={(field?: string) => {
                            if (!field) {
                                setSorters([]);
                                return;
                            }
                            const cur = sorters?.[0];
                            setSorters([{ field, order: cur?.field === field ? cur.order : "desc" }]);
                        }}
                        options={[
                            { value: "id", label: "ID" },
                            ...displayColumns
                                .filter((c) => isSortableField(c.key))
                                .map((c) => ({ value: c.key, label: c.label })),
                        ]}
                    />
                    <Select
                        style={{ width: 130 }}
                        value={sorters?.[0]?.order ?? "desc"}
                        disabled={!sorters?.length}
                        onChange={(order) => {
                            const cur = sorters?.[0];
                            if (cur) setSorters([{ ...cur, order }]);
                        }}
                        options={[
                            { value: "asc", label: "По возрастанию" },
                            { value: "desc", label: "По убыванию" },
                        ]}
                    />

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
                        <Tooltip title={appliedCount > 0 ? `Фильтры (${appliedCount})` : "Фильтры"}>
                            <Badge size="small" count={appliedCount} offset={[-6, 6]}>
                                <Button icon={<FilterOutlined />} />
                            </Badge>
                        </Tooltip>
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
                            <Tooltip title="Колонки">
                                <Button icon={<TableOutlined />} />
                            </Tooltip>
                        </Popover>
                    )}

                    {isReceiptDocuments && (
                        <Tooltip title="Сформировать квитанции">
                            <Button
                                type="primary"
                                icon={<FileAddOutlined />}
                                onClick={() => setReceiptsModalOpen(true)}
                            />
                        </Tooltip>
                    )}

                    {isWriteoffDocuments && (role === "admin" || role === "operator") && (
                        <Tooltip title="Выполнить списание">
                            <Button
                                type="primary"
                                icon={<AccountBookOutlined />}
                                onClick={() => setWriteOffsModalOpen(true)}
                            />
                        </Tooltip>
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
                        {...(canUseSelection
                            ? {
                                  onRow: (record: any) => ({
                                      onClick: () => setSelectedRowKey(record.id),
                                      style: { cursor: "pointer" },
                                  }),
                                  rowSelection: {
                                      type: "radio",
                                      selectedRowKeys:
                                          selectedRowKey != null ? [selectedRowKey] : [],
                                      onChange: (keys) =>
                                          setSelectedRowKey((keys[0] as string | number) ?? null),
                                  },
                              }
                            : {})}
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
                        modalState.mode === "create"
                            ? "Новая запись"
                            : modalState.mode === "view"
                              ? "Просмотр записи"
                              : "Редактирование записи"
                    }
                    fields={fields}
                    initialValues={modalState.record}
                    confirmLoading={creating || updating}
                    readonly={modalState.mode === "view"}
                    onCancel={() => setModalState(null)}
                    onSubmit={handleSubmit}
                    resourceName={resourceName}
                />
            )}

            {isMeterReadingDocuments && (
                <BulkReadingsModal
                    open={bulkModalOpen}
                    documentId={editingMeterReadingDocumentId}
                    readonly={docReadOnly}
                    onClose={() => {
                        setBulkModalOpen(false);
                        setEditingMeterReadingDocumentId(undefined);
                        setDocReadOnly(false);
                    }}
                    onSaved={() => tableQuery.refetch()}
                />
            )}

            {isAccrualDocuments && (
                <>
                    <AccrualsCalculationModal
                        open={accrualsModalOpen}
                        documentId={editingAccrualDocumentId}
                        readonly={docReadOnly}
                        onClose={() => {
                            setAccrualsModalOpen(false);
                            setEditingAccrualDocumentId(undefined);
                            setDocReadOnly(false);
                        }}
                        onSaved={() => tableQuery.refetch()}
                    />
                    <OneOffAccrualsEditModal
                        open={oneOffAccrualsOpen}
                        documentId={editingAccrualDocumentId}
                        readonly={docReadOnly}
                        onClose={() => {
                            setOneOffAccrualsOpen(false);
                            setEditingAccrualDocumentId(undefined);
                            setDocReadOnly(false);
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
