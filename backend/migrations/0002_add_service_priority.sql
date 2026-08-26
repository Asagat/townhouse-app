-- 0002_add_service_priority.sql
-- Фаза 2 (Шаг 2.1): поле «Приоритет списания» в справочнике «Виды услуг».
-- Меньший номер списывается раньше; 0/NULL — в последнюю очередь.
-- Ниже задаются разумные стартовые приоритеты для существующих услуг.

ALTER TABLE services_type ADD COLUMN IF NOT EXISTS priority integer DEFAULT 0;

-- Стартовые приоритеты (настраиваются из интерфейса в справочнике «Виды услуг»):
-- «Фонд развития» оставляем самым последним (приоритет 0) — долги по нему
-- списываются в последнюю очередь.
UPDATE services_type SET priority = 1 WHERE services_type = 'Электричество';
UPDATE services_type SET priority = 2 WHERE services_type = 'Холодная вода';
UPDATE services_type SET priority = 3 WHERE services_type = 'Охрана';
UPDATE services_type SET priority = 4 WHERE services_type = 'Обслуживание ТП';
UPDATE services_type SET priority = 0 WHERE services_type = 'Фонд развития';
