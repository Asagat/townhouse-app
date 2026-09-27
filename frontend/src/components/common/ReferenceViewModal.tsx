// src/components/common/ReferenceViewModal.tsx
// Read-only просмотр записи связанного ресурса («проваливание» по ссылке, 2.21).
// Загружает метаданные полей (`/api/meta/{resource}`) и саму запись
// (`/api/{resource}/{id}`) и показывает их в RecordFormModal в режиме просмотра.

import { useEffect, useState } from "react";
import { Modal, Spin, message } from "antd";

import { authedFetch, apiUrl } from "../../auth/http";
import { allResources } from "../../config/menu";
import { RESOURCE_LABELS } from "../../config/referenceDrill";
import type { FieldMeta } from "../../types";
import { RecordFormModal } from "./RecordFormModal";

interface ReferenceViewModalProps {
    resource: string;
    id: number;
    onClose: () => void;
}

const resourceLabel = (resource: string): string =>
    RESOURCE_LABELS[resource] ?? allResources.find((r) => r.key === resource)?.label ?? resource;

export const ReferenceViewModal = ({ resource, id, onClose }: ReferenceViewModalProps) => {
    const [fields, setFields] = useState<FieldMeta[] | null>(null);
    const [record, setRecord] = useState<Record<string, any> | null>(null);
    const [loading, setLoading] = useState(true);

    const title = `Просмотр: ${resourceLabel(resource)}`;

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setFields(null);
        setRecord(null);

        const load = async () => {
            const readJson = async (url: string) => {
                const resp = await authedFetch(url);
                if (!resp.ok) {
                    let detail = `Не удалось загрузить запись (${resp.status})`;
                    try {
                        const body = await resp.json();
                        if (body?.detail) detail = String(body.detail);
                    } catch {
                        /* тело не JSON */
                    }
                    throw new Error(detail);
                }
                return resp.json();
            };
            const [meta, item] = await Promise.all([
                readJson(`${apiUrl}/meta/${resource}`),
                readJson(`${apiUrl}/${resource}/${id}`),
            ]);
            return { meta, item };
        };

        load()
            .then(({ meta, item }) => {
                if (cancelled) return;
                setFields(meta?.fields ?? []);
                setRecord(item ?? {});
            })
            .catch((e: any) => {
                if (cancelled) return;
                message.error(e?.message ?? "Не удалось загрузить запись");
                onClose();
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });

        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [resource, id]);

    // Пока данные не загружены — лёгкая оболочка окна (RecordFormModal монтируем уже
    // с готовыми полями/записью: его начальные значения проставляются на montage).
    if (loading || !fields || !record) {
        return (
            <Modal open title={title} footer={null} onCancel={onClose} width={800} destroyOnClose>
                <div style={{ textAlign: "center", padding: 40 }}>
                    <Spin />
                </div>
            </Modal>
        );
    }

    return (
        <RecordFormModal
            open
            title={title}
            fields={fields}
            initialValues={record}
            confirmLoading={false}
            readonly
            resourceName={resource}
            onCancel={onClose}
            onSubmit={() => {}}
        />
    );
};
