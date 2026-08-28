# backend/tests/test_migrations.py
"""Регрессионный тест: цепочка Alembic-миграций должна проходить на пустой БД.

Сценарий: `alembic upgrade head` от нуля на только что созданной временной БД.
Такой тест поймал бы баг 0005_drop_analytic_code: миграция безусловно добавляла
unique-constraint `uq_analytic_articles_name_kind`, имя которого на свежей БД уже
занимал unique-индекс из 0002_schema_squash (create_all по актуальным моделям).
Из-за DuplicateTable вся цепочка откатывалась, и приложение оставалось без таблиц.

Требования:
- доступный PostgreSQL (те же учётные данные, что у приложения);
- роль БД должна уметь создавать БД (CREATEDB). В официальном docker-образе
  postgres пользователь POSTGRES_USER создаётся суперпользователем, поэтому в
  штатной docker-compose-установке тест проходит. Иначе — skip.
"""

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic.config import Config
from alembic.script import ScriptDirectory

from database import SQLALCHEMY_DATABASE_URL

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALEMBIC_INI = os.path.join(BACKEND_DIR, "alembic.ini")


def _head_revision() -> str:
    """Актуальная head-ревизия из alembic/versions (без обращения к БД)."""
    script = ScriptDirectory.from_config(Config(_ALEMBIC_INI))
    return script.get_current_head()


def _url_with_db(dbname: str) -> str:
    """URL подключения с заменённым именем БД (пароль не прячем — нужен subprocess)."""
    return make_url(SQLALCHEMY_DATABASE_URL).set(database=dbname).render_as_string(hide_password=False)


def _run_admin_sql(statement: str) -> None:
    """Выполняет SQL в служебной БД `postgres` (CREATE/DROP DATABASE вне транзакции)."""
    engine = create_engine(_url_with_db("postgres"), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(statement))
    finally:
        engine.dispose()


def test_alembic_upgrade_head_on_fresh_db():
    """alembic upgrade head проходит с нуля и создаёт полную схему."""
    dbname = f"townhouse_migr_test_{uuid.uuid4().hex[:10]}"
    try:
        _run_admin_sql(f'CREATE DATABASE "{dbname}"')
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Не удалось создать временную БД (нужны права CREATEDB): {exc}")

    try:
        env = os.environ.copy()
        env["DATABASE_URL"] = _url_with_db(dbname)
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"alembic upgrade head упал на свежей БД:\n{result.stdout}\n{result.stderr}"
        )

        # Проверяем, что схема реально создана и цепочка дошла до head.
        engine = create_engine(_url_with_db(dbname))
        try:
            with engine.connect() as conn:
                for table in ("users", "tariff_types", "analytic_articles", "transactions"):
                    exists = conn.execute(
                        text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{table}"}
                    ).scalar()
                    assert exists, f"После миграций отсутствует таблица {table}"
                version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                assert version == _head_revision(), (
                    f"alembic_version={version!r}, ожидался head={_head_revision()!r}"
                )
        finally:
            engine.dispose()
    finally:
        # Очистка временной БД — best effort, чтобы не маскировать результат теста.
        try:
            _run_admin_sql(f'DROP DATABASE IF EXISTS "{dbname}"')
        except Exception:  # noqa: BLE001
            pass
