"""The fixed, read-only tools the assistant agent may call (app.assistant.agent).

The model chooses a tool and its arguments; code runs it. No tool takes a user, role or person:
execute() binds the session user and page in a ToolContext, and the argument models reject
anything else (extra="forbid"). Every tool reuses a v1.5 function under its visibility rule, so a
tool shows only what the app already shows that user, and the assessment lock is enforced inside
search_knowledge, where no prompt wording can reach it.

Each tool returns {"ok": bool, "items": [...], "message": str}, and every item has a stable id the
reply can cite. A handoff the user cannot see is "not found", never "forbidden", so its existence
does not leak.
"""

import hashlib
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.assistant import live_data
from app.assistant.retrieval import rank_knowledge, rank_topics
from app.assistant.service import assessment_lock, readable_versions
from app.auth.deps import visible_handoffs
from app.models import AppUser

LOCKED = "locked"
NOT_FOUND = "not found"
HELP_TOPIC_LIMIT = 3
QUERY_MAX = 200


class ToolRejected(Exception):
    """The model asked for an unknown tool or sent arguments the tool does not take. The text is
    safe to log: it never carries the arguments."""


@dataclass(frozen=True)
class ToolContext:
    """What the executor binds. The model can set none of it."""

    session: Session
    user: AppUser
    page: str
    roles: set[str]


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HandoffStatusArgs(NoArgs):
    handoff_ref: str | None = Field(
        default=None,
        max_length=QUERY_MAX,
        description='An item id or "expert→successor" label from a previous tool result.',
    )


class QueryArgs(NoArgs):
    query: str = Field(min_length=1, max_length=QUERY_MAX, description="Keywords in English.")


# ---------- results ----------


def _result(items: list[dict], message: str = "", ok: bool = True) -> dict:
    return {"ok": ok, "items": items, "message": message}


def _data_rows(answer: live_data.Answer) -> tuple[str, list[tuple[str, dict]]]:
    """Splits a live-data answer by its contract: a heading, then one row per citation. An
    answer without citations is a single message with no rows."""
    text, citations = answer
    if not citations:
        return text, []
    heading, *rows = text.split("\n")
    return heading, list(zip(rows, citations, strict=True))


def _data_item(item_id: str, text: str, citation: dict) -> dict:
    return {
        "id": item_id,
        "kind": "data",
        "title": citation["title"],
        "text": text,
        "citation": citation,
    }


def _hashed_items(prefix: str, answer: live_data.Answer) -> dict:
    """Rows that are not one per handoff get an id from the page and title they point to. Two
    identical rows (two handoffs with the same people) are told apart by a counter."""
    heading, rows = _data_rows(answer)
    seen: Counter[str] = Counter()
    items = []
    for text, citation in rows:
        key = hashlib.sha256(f"{citation['link']}|{citation['title']}".encode()).hexdigest()[:10]
        seen[key] += 1
        suffix = f"-{seen[key]}" if seen[key] > 1 else ""
        items.append(_data_item(f"{prefix}:{key}{suffix}", text, citation))
    return _result(items, heading)


def _per_handoff(ctx: ToolContext, prefix: str, answer: live_data.Answer) -> list[dict]:
    """live_data writes one row per visible handoff, in visible_handoffs order."""
    _, rows = _data_rows(answer)
    if not rows:
        return []
    handoffs = visible_handoffs(ctx.session, ctx.user)
    return [
        _data_item(f"{prefix}:{h.id}", text, citation)
        for h, (text, citation) in zip(handoffs, rows, strict=True)
    ]


def _normal_label(label: str) -> str:
    return re.sub(r"\s*(?:→|->|=>)\s*", "→", label.strip()).casefold()


def _is_ref(item: dict, ref: str) -> bool:
    handoff_id = item["id"].split(":", 1)[1]
    wanted = ref.strip().casefold()
    return wanted in (
        handoff_id,
        f"handoff:{handoff_id}",
        f"status:{handoff_id}",
    ) or _normal_label(ref) == _normal_label(item["title"])


# ---------- the tools ----------


def _list_handoffs(ctx: ToolContext, _: NoArgs) -> dict:
    answer = live_data.list_handoffs(ctx.session, ctx.user)
    return _result(_per_handoff(ctx, "handoff", answer), _data_rows(answer)[0])


def _handoff_status(ctx: ToolContext, args: HandoffStatusArgs) -> dict:
    answer = live_data.handoff_status(ctx.session, ctx.user)
    items = _per_handoff(ctx, "status", answer)
    if args.handoff_ref is not None:
        items = [item for item in items if _is_ref(item, args.handoff_ref)]
        if not items:
            return _result([], NOT_FOUND, ok=False)
    return _result(items, _data_rows(answer)[0])


def _my_pending(ctx: ToolContext, _: NoArgs) -> dict:
    return _hashed_items("pending", live_data.my_pending(ctx.session, ctx.user))


def _my_due(ctx: ToolContext, _: NoArgs) -> dict:
    return _hashed_items("due", live_data.my_due(ctx.session, ctx.user))


def _search_knowledge(ctx: ToolContext, args: QueryArgs) -> dict:
    if assessment_lock(ctx.session, ctx.user):
        return _result([], LOCKED, ok=False)
    hit = rank_knowledge(args.query, readable_versions(ctx.session))
    if hit is None:
        return _result([])
    return _result(
        [
            {
                "id": line.id,
                "kind": "knowledge",
                "title": line.title,
                "text": line.text,
                "field": line.field,
                "index": line.index,
                "version_id": line.version_id,
                "version_no": line.version_no,
            }
            for line in hit.lines
        ]
    )


def _help_topics(ctx: ToolContext, args: QueryArgs) -> dict:
    hits = rank_topics(args.query, ctx.roles, ctx.page)[:HELP_TOPIC_LIMIT]
    return _result(
        [
            {"id": h.topic.id, "kind": "help", "title": h.topic.title, "text": h.topic.answer}
            for h in hits
        ]
    )


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[NoArgs]
    run: Callable[[ToolContext, BaseModel], dict]


TOOLS = {
    t.name: t
    for t in (
        Tool(
            "list_handoffs",
            "List the handoffs the signed-in user can see, newest first.",
            NoArgs,
            _list_handoffs,
        ),
        Tool(
            "handoff_status",
            "Status of the handoffs the signed-in user can see, or of one handoff if handoff_ref "
            "is given.",
            HandoffStatusArgs,
            _handoff_status,
        ),
        Tool(
            "my_pending",
            "What is waiting for the signed-in user: their next tasks.",
            NoArgs,
            _my_pending,
        ),
        Tool(
            "my_due",
            "The signed-in user's assessment due time and whether their official attempt is used.",
            NoArgs,
            _my_due,
        ),
        Tool(
            "search_knowledge",
            "Search approved operational knowledge. Returns approved lines. Query in English.",
            QueryArgs,
            _search_knowledge,
        ),
        Tool(
            "help_topics",
            "Search the guide to using this website and how its numbers work. Query in English.",
            QueryArgs,
            _help_topics,
        ),
    )
}


def tool_schemas() -> list[dict]:
    """The tools as the chat completions API takes them."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.args.model_json_schema(),
            },
        }
        for t in TOOLS.values()
    ]


def execute(name: str, arguments: dict, ctx: ToolContext) -> dict:
    """Runs one tool as the session user. Raises ToolRejected for an unknown tool or bad args."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolRejected("unknown tool")
    try:
        args = tool.args.model_validate(arguments)
    except ValidationError:
        raise ToolRejected(f"invalid arguments for {name}") from None
    return tool.run(ctx, args)


def for_model(result: dict) -> dict:
    """The result as the model sees it: rendering details stay with the code."""
    return {
        "ok": result["ok"],
        "message": result["message"],
        "items": [{k: item[k] for k in ("id", "title", "text")} for item in result["items"]],
    }
