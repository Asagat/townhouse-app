// src/components/permissions/RolePermissions.tsx
// Вкладка «Права доступа» (задача 2.6): матрица «ресурс × роль».
// Столбцы-действия: Р = раздел в меню, Ч = чтение, С = создание, И = изменение, У = удаление.
// Источник — /api/auth/permissions (только admin). Роли admin/resident фиксированы,
// «запертые» действия (регистры, типы тарифов) недоступны.

import { useEffect, useState } from "react";
import { Button, Checkbox, Space, Table, Tooltip, Typography, message } from "antd";

import { apiUrl, http } from "../../auth/http";
import { ROLE_OPTIONS_LABELS } from "../../auth/menuAccess";

interface CatalogEntry {
    key: string;
    label: string;
    group: string;
    kind: "resource" | "section";
    read_enforced: boolean;
}

type PermKey = "menu" | "read" | "create" | "edit" | "delete";
type Perm = Record<PermKey, boolean>;
type Matrix = Record<string, Record<string, Perm>>;

const ACTIONS: PermKey[] = ["menu", "read", "create", "edit", "delete"];
const ACTION_LETTER: Record<PermKey, string> = {
    menu: "Р", read: "Ч", create: "С", edit: "И", delete: "У",
};
const ACTION_TITLE: Record<PermKey, string> = {
    menu: "Раздел в меню", read: "Чтение", create: "Создание", edit: "Изменение", delete: "Удаление",
};

export const RolePermissions = () => {
    const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
    const [roles, setRoles] = useState<string[]>([]);
    const [fixedRoles, setFixedRoles] = useState<string[]>([]);
    const [lockedActions, setLockedActions] = useState<Record<string, string[]>>({});
    const [matrix, setMatrix] = useState<Matrix>({});
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const res = await http.get(`${apiUrl}/auth/permissions`);
            setCatalog(res.data.catalog ?? []);
            setRoles(res.data.roles ?? []);
            setFixedRoles(res.data.fixed_roles ?? []);
            setLockedActions(res.data.locked_actions ?? {});
            setMatrix(res.data.matrix ?? {});
        } catch (e: any) {
            message.error(e?.response?.data?.detail ?? "Не удалось загрузить права");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, []);

    // Применимо ли действие к разделу (у section — только «Раздел» и «Чтение»).
    const applicable = (entry: CatalogEntry, action: PermKey): boolean => {
        if (action === "menu") return true;
        if (entry.kind === "section") return action === "read" && entry.read_enforced;
        return true;
    };

    const isDisabled = (role: string, entry: CatalogEntry, action: PermKey): boolean => {
        if (fixedRoles.includes(role)) return true;
        if ((lockedActions[entry.key] ?? []).includes(action)) return true;
        return false;
    };

    const toggle = (role: string, key: string, action: PermKey, value: boolean) => {
        setMatrix((prev) => ({
            ...prev,
            [role]: {
                ...(prev[role] ?? {}),
                [key]: { ...(prev[role]?.[key] as Perm), [action]: value },
            },
        }));
    };

    const save = async () => {
        const items: Array<Record<string, unknown>> = [];
        for (const role of roles) {
            if (fixedRoles.includes(role)) continue;
            for (const entry of catalog) {
                const p = matrix[role]?.[entry.key];
                if (!p) continue;
                items.push({ role, resource: entry.key, ...p });
            }
        }
        setSaving(true);
        try {
            await http.put(`${apiUrl}/auth/permissions`, { items });
            message.success("Права сохранены");
        } catch (e: any) {
            message.error(e?.response?.data?.detail ?? "Не удалось сохранить права");
        } finally {
            setSaving(false);
        }
    };

    const reset = async () => {
        setSaving(true);
        try {
            await http.post(`${apiUrl}/auth/permissions/reset`);
            message.success("Восстановлены умолчания");
            await load();
        } catch (e: any) {
            message.error(e?.response?.data?.detail ?? "Не удалось сбросить права");
        } finally {
            setSaving(false);
        }
    };

    const renderCell = (role: string, entry: CatalogEntry) => (
        <Space size={6} wrap>
            {ACTIONS.filter((a) => applicable(entry, a)).map((a) => {
                const disabled = isDisabled(role, entry, a);
                return (
                    <Tooltip key={a} title={disabled ? `${ACTION_TITLE[a]} (недоступно)` : ACTION_TITLE[a]}>
                        <Checkbox
                            checked={Boolean(matrix[role]?.[entry.key]?.[a])}
                            disabled={disabled}
                            onChange={(e) => toggle(role, entry.key, a, e.target.checked)}
                        >
                            {ACTION_LETTER[a]}
                        </Checkbox>
                    </Tooltip>
                );
            })}
        </Space>
    );

    const columns = [
        {
            title: "Группа",
            dataIndex: "group",
            key: "group",
            width: 170,
            render: (group: string, _rec: CatalogEntry, index: number) =>
                index === 0 || catalog[index - 1]?.group !== group ? (
                    <Typography.Text type="secondary">{group}</Typography.Text>
                ) : null,
        },
        { title: "Ресурс / раздел", dataIndex: "label", key: "label", width: 240 },
        ...roles.map((role) => ({
            title: (
                <Tooltip title={fixedRoles.includes(role) ? "Роль фиксирована (не редактируется)" : undefined}>
                    <span>{ROLE_OPTIONS_LABELS[role] ?? role}</span>
                </Tooltip>
            ),
            key: role,
            width: 190,
            render: (_: unknown, entry: CatalogEntry) => renderCell(role, entry),
        })),
    ];

    return (
        <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, marginBottom: 12 }}>
                <Typography.Text type="secondary">
                    Р — раздел в меню (виден ли пункт), Ч/С/И/У — чтение/создание/изменение/удаление.
                    Роли «Администратор» и «Житель» фиксированы.
                </Typography.Text>
                <Space>
                    <Button onClick={reset} loading={saving}>Сбросить к умолчаниям</Button>
                    <Button type="primary" onClick={save} loading={saving}>Сохранить</Button>
                </Space>
            </div>
            <Table<CatalogEntry>
                rowKey="key"
                dataSource={catalog}
                columns={columns as any}
                loading={loading}
                pagination={false}
                size="small"
                scroll={{ x: "max-content" }}
            />
        </div>
    );
};
