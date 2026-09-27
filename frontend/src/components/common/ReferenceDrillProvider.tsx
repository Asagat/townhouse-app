// src/components/common/ReferenceDrillProvider.tsx
// Провайдер стека «проваливаний» (2.21): хранит открытые связанные записи и рисует
// по одной read-only модалке на каждую; закрытие — LIFO (или закрытие конкретного слоя
// вместе с более глубокими).

import { useCallback, useMemo, useState, type ReactNode } from "react";

import { canRead } from "../../auth/can";
import { getIdentity } from "../../auth/token";
import { ReferenceDrillContext, type ReferenceDrillApi } from "./referenceDrillContext";
import { ReferenceViewModal } from "./ReferenceViewModal";

interface DrillEntry {
    resource: string;
    id: number;
}

export const ReferenceDrillProvider = ({ children }: { children: ReactNode }) => {
    const [stack, setStack] = useState<DrillEntry[]>([]);

    const canDrill = useCallback(
        (resource: string): boolean => canRead(getIdentity()?.role ?? "", resource),
        [],
    );

    const drill = useCallback((resource: string, id: number) => {
        setStack((prev) => {
            const top = prev[prev.length - 1];
            // Повторный клик по той же ссылке не плодит дубликат слоя.
            if (top && top.resource === resource && top.id === id) return prev;
            return [...prev, { resource, id }];
        });
    }, []);

    // Закрыть слой `index` и все более глубокие (в обычном сценарии — верхний).
    const closeAt = useCallback((index: number) => {
        setStack((prev) => prev.slice(0, index));
    }, []);

    const api = useMemo<ReferenceDrillApi>(() => ({ drill, canDrill }), [drill, canDrill]);

    return (
        <ReferenceDrillContext.Provider value={api}>
            {children}
            {stack.map((entry, index) => (
                <ReferenceViewModal
                    key={`${entry.resource}-${entry.id}-${index}`}
                    resource={entry.resource}
                    id={entry.id}
                    onClose={() => closeAt(index)}
                />
            ))}
        </ReferenceDrillContext.Provider>
    );
};
