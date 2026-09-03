// src/pages/GenericList.tsx

import { useState } from "react";
import {
    Table,
    Button,
    Space,
    Popconfirm,
    Popover,
    Checkbox,
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
import { getColumnsForResource } from "../config/columns";
import { allResources } from "../config/menu";
import { RecordFormModal } from "../components/common/RecordFormModal";
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
import { useVisibleColumns, filterVisibleColumns } from "../hooks/useVisibleColumns";

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

    const {
        tableQuery,
        current,
        setCurrent,
        pageSize,
        setPageSize,
        sorters,
        setSorters,
    } = useTable({
        resource: resourceName,
        pagination: {
            current: 1,
            pageSize: 10,
        },
        sorters: {
            initial: [
                {
                    field: "id",
                    order: "desc",
                },
            ],
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

    // Вариант A (п. 2.10): настройка видимых колонок списка, сохранение в localStorage.
    const { visibleKeys, toggle } = useVisibleColumns(resourceName, role, columns.map((c) => c.key));
    const displayColumns = filterVisibleColumns(columns, visibleKeys);

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
            width: 70,
            sorter: true,
            sortOrder: getColumnSortOrder('id'),
            defaultSortOrder: 'descend' as const,
        },
        ...displayColumns.map((col) => {
            const sortable = isSortableField(col.key);
            const isNested = col.key.includes('.');
            return {
                title: col.label,
                dataIndex: col.key,
                key: col.key,
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
                ...(sortable && {
                    onHeaderCell: () => ({
                        style: { cursor: 'pointer' },
                        title: 'Кликните для сортировки',
                    }),
                }),
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
                                              window.open(
                                                  `${apiUrl}/receipt_documents/${record.id}/pdf`,
                                                  "_blank",
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
                    {columns.length > 0 && (
                        <Popover
                            trigger="click"
                            placement="bottomRight"
                            content={
                                <div style={{ maxWidth: 280, maxHeight: 360, overflow: "auto" }}>
                                    <div
                                        style={{
                                            fontSize: 13,
                                            fontWeight: 600,
                                            marginBottom: 8,
                                            color: "#666",
                                        }}
                                    >
                                        Отображаемые колонки
                                    </div>
                                    {columns.map((col) => {
                                        const checked = !visibleKeys ? true : visibleKeys.has(col.key);
                                        return (
                                            <div key={col.key} style={{ marginBottom: 4 }}>
                                                <Checkbox
                                                    checked={checked}
                                                    onChange={(e) => toggle(col.key, e.target.checked)}
                                                >
                                                    {col.label}
                                                </Checkbox>
                                            </div>
                                        );
                                    })}
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

            <Table
                rowKey="id"
                dataSource={data}
                columns={tableColumns}
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
