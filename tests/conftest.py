"""Shared pytest fixtures. Guard: TEST_DATABASE_URL database name must contain 'test'."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_TEST_URL = "postgresql+psycopg://tester@127.0.0.1:55427/intel_approval_test"

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _DEFAULT_TEST_URL
_database_name = make_url(TEST_DATABASE_URL).database or ""
if "test" not in _database_name.lower():
    raise RuntimeError(
        "TEST_DATABASE_URL must point at a database whose name contains 'test'; "
        f"got {_database_name!r}"
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("APP_TIMEZONE", "Asia/Shanghai")


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def clean_database(migrated_database: None) -> None:
    from app.db import get_engine

    with get_engine().begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE intel_items, intel_approvals, intel_audit_logs, "
                "intel_briefing_candidates, intel_reminder_outbox"
            )
        )


@pytest.fixture
def session():
    from app.db import get_session_factory

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def link_stub():
    from app.services.link_checker import StubLinkChecker

    return StubLinkChecker(ok=True)


@pytest.fixture
def matcher_stub():
    from app.services.matcher import StubMemberMatcher

    return StubMemberMatcher()


@pytest.fixture
def reminder_stub():
    from app.services.reminder import StubReminderService

    return StubReminderService()


@pytest.fixture
def client(link_stub, matcher_stub, reminder_stub):
    from fastapi.testclient import TestClient

    from app.api import deps
    from app.main import app

    app.dependency_overrides[deps.get_link_checker] = lambda: link_stub
    app.dependency_overrides[deps.get_matcher] = lambda: matcher_stub
    app.dependency_overrides[deps.get_reminder] = lambda: reminder_stub
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()