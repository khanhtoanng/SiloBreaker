import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

TEST_DB = os.environ.get(
    "SB_TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/silobreaker_test"
)
os.environ["SB_DATABASE_URL"] = TEST_DB

BACKEND = Path(__file__).resolve().parents[1]
ORACLE = BACKEND.parent / "fixtures" / "oracle"


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    from app.config import get_settings
    from app.db import reset_engine

    get_settings.cache_clear()
    reset_engine()
    engine = create_engine(TEST_DB)
    with engine.begin() as c:
        c.execute(text("drop schema public cascade; create schema public;"))
    engine.dispose()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(cfg, "head")
    from app.db import get_session
    from app.seed_users import seed_users

    for session in get_session():
        seed_users(session)  # hashed once per run; each test restores the rows below
        session.commit()
    yield


def _restore_demo_users() -> None:
    """Drop accounts and sessions a previous test created and undo edits to the demo users,
    without re-hashing their passwords."""
    from app.seed_users import DEMO_USERS

    engine = create_engine(TEST_DB)
    with engine.begin() as c:
        c.execute(text("truncate user_session"))
        names = [u["username"] for u in DEMO_USERS]
        c.execute(text("delete from app_user where username <> all(:n)"), {"n": names})
        for u in DEMO_USERS:
            c.execute(
                text(
                    "update app_user set role=:role, person_id=:person_id,"
                    " display_name=:display_name, is_active=true where username=:username"
                ),
                {k: u[k] for k in ("username", "role", "person_id", "display_name")},
            )
    engine.dispose()


PASSWORDS = {
    "admin": "Admin@123",
    "alice": "Alice@123",
    "bob": "Bob@123",
    "carol": "Carol@123",
    "minh": "Minh@123",
}


def login_as(client, username: str, password: str | None = None):
    """Switches the client to `username`, reusing that user's session within the test."""
    tokens = client.__dict__.setdefault("_tokens", {})
    client.cookies.clear()
    if username not in tokens:
        r = client.post(
            "/api/auth/login",
            json={"username": username, "password": password or PASSWORDS[username]},
        )
        assert r.status_code == 200, r.text
        tokens[username] = client.cookies.get("sb_session")
        client.cookies.clear()
    client.cookies.set("sb_session", tokens[username])
    return client


def create_member(client, username: str, password: str = "Member@123", **extra) -> dict:
    """Creates a member account as admin and leaves the client signed in as admin.

    A seeded demo member (e.g. carol) already exists as a plain member, so it is returned
    as is when no extra fields are asked for."""
    from app.seed_users import DEMO_USERS

    seeded = {u["username"]: u for u in DEMO_USERS}
    if username in seeded and not extra and password == "Member@123":
        login_as(client, "admin")
        return {k: seeded[username][k] for k in ("username", "role", "person_id")}
    r = login_as(client, "admin").post(
        "/api/admin/users",
        json={"username": username, "role": "member", "password": password, **extra},
    )
    assert r.status_code == 201, r.text
    PASSWORDS[username] = password
    return r.json()


@pytest.fixture
def client():
    from app.main import app

    _restore_demo_users()
    with TestClient(app, headers={"X-Requested-With": "silobreaker"}) as c:
        r = login_as(c, "admin").post("/api/demo/reset")
        assert r.status_code == 200, r.text
        c.bundle = r.json()
        yield c


@pytest.fixture
def oracle():
    """Evaluator-only expectations. Never imported by app code."""
    return {p.stem: json.loads(p.read_text()) for p in ORACLE.glob("*.json")}


def make_handoff(client, expert="alice", successor="bob"):
    """Created by the admin; leaves the client signed in as admin."""
    r = login_as(client, "admin").post(
        "/api/handoffs",
        json={"bundle_id": client.bundle["id"], "expert_id": expert, "successor_id": successor},
    )
    assert r.status_code == 201, r.text
    return r.json()


def analyze(client, handoff, selected=None, key=None, as_user=None):
    """Run by the handoff's expert (default); leaves the client signed in as that user."""
    headers = {"Idempotency-Key": key} if key else {}
    r = login_as(client, as_user or handoff["expert_id"]).post(
        f"/api/handoffs/{handoff['id']}/analyses",
        json={"selected_engineer_id": selected},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def by_area(analysis):
    return {f["area_key"]: f for f in analysis["findings"]}
