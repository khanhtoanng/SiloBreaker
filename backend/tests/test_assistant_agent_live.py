"""Optional smoke test against a real local model server (the Llama app by default).

Skipped unless SB_ASSISTANT_LIVE=1. SB_ASSISTANT_MODEL names the model, exactly as GET
{SB_ASSISTANT_BASE_URL}/models lists it:

    SB_ASSISTANT_LIVE=1 SB_ASSISTANT_MODEL=<id> pytest -q -m local_model
"""

import os

import pytest
from sqlalchemy import select

from app.assistant import live_data as L
from app.config import get_settings
from app.db import get_session
from app.models import AppUser
from tests.conftest import login_as, make_handoff

pytestmark = [
    pytest.mark.local_model,
    pytest.mark.skipif(os.environ.get("SB_ASSISTANT_LIVE") != "1", reason="SB_ASSISTANT_LIVE!=1"),
]


def visible_rows() -> list[tuple[str, dict]]:
    """The rows and links of the admin's list, from the same rule the pages use."""
    session = next(get_session())
    try:
        admin = session.scalar(select(AppUser).where(AppUser.username == "admin"))
        text, citations = L.list_handoffs(session, admin)
        return list(zip(text.split("\n")[1:], citations, strict=True))
    finally:
        session.close()


@pytest.mark.parametrize("question", ["Are there any handoffs?", "Có handoff nào không?"])
def test_live_model_lists_handoffs(client, monkeypatch, question):
    settings = get_settings()
    if not settings.assistant_model:
        pytest.fail("SB_ASSISTANT_LIVE=1 needs SB_ASSISTANT_MODEL")
    monkeypatch.setattr(settings, "assistant_provider", "local")
    make_handoff(client)

    r = login_as(client, "admin").post(
        "/api/assistant/ask", json={"question": question, "page": "/admin"}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["provider"] == "local", out
    assert out["mode"] == "data", out
    assert "list_handoffs" in out["tools_used"] or "handoff_status" in out["tools_used"]
    rows = out["sections"][0]["answer"].split("\n")[1:]
    if "list_handoffs" in out["tools_used"]:
        assert list(zip(rows, out["citations"], strict=True)) == visible_rows()
    assert out["reply"]
