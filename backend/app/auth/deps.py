"""FastAPI dependencies for authorization. The acting person is always the signed-in
account's person_id; it is never read from a request body or query string."""

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import service
from app.config import get_settings
from app.db import tx
from app.errors import AppError
from app.models import AppUser, Handoff, HandoffCandidate


def session_token(request: Request) -> str | None:
    return request.cookies.get(get_settings().session_cookie_name)


def current_user(
    token: str | None = Depends(session_token), session: Session = Depends(tx)
) -> AppUser:
    found = service.resolve_session(session, token)
    if found is None:
        raise AppError(401, "not_authenticated", "Sign in required")
    return found[1]


def require_admin(user: AppUser = Depends(current_user)) -> AppUser:
    if user.role != "admin":
        raise AppError(403, "not_admin", "administrator access required")
    return user


def actor_label(user: AppUser) -> str:
    """Audit actor: the person for members, the username for admins (who have no person)."""
    return user.person_id or user.username


def handoff_role(user: AppUser, handoff: Handoff) -> str:
    """'admin', 'expert' or 'successor'. Anyone else is refused.

    An admin is never a participant, even if the account also carries a person_id. While a
    handoff is selecting, every candidate acts as a successor (own attempts only).
    """
    if user.role == "admin":
        return "admin"
    if user.person_id and user.person_id == handoff.expert_id:
        return "expert"
    if user.person_id and user.person_id == handoff.successor_id:
        return "successor"
    if handoff.candidate(user.person_id) is not None:
        return "successor"
    raise AppError(403, "not_participant", "you are not the expert or successor of this handoff")


def visible_handoffs(session: Session, user: AppUser) -> list[Handoff]:
    """Every handoff this user may open, newest first: all of them for an admin; for a member
    the ones they are the expert or successor of, and selecting handoffs they are a candidate
    of. The one visibility rule shared by GET /api/handoffs and the help assistant."""
    stmt = select(Handoff).order_by(Handoff.created_at.desc())
    if user.role != "admin":
        pid = user.person_id or ""
        candidate_of = select(HandoffCandidate.handoff_id).where(HandoffCandidate.person_id == pid)
        stmt = stmt.where(
            (Handoff.expert_id == pid)
            | (Handoff.successor_id == pid)
            | ((Handoff.status == "selecting") & Handoff.id.in_(candidate_of))
        )
    return list(session.scalars(stmt))


def require_handoff_role(user: AppUser, handoff: Handoff, *allowed: str) -> str:
    r = handoff_role(user, handoff)
    if r not in allowed:
        wanted = " or ".join(a for a in allowed)
        raise AppError(403, f"not_{allowed[0]}", f"only the handoff's {wanted} may do this")
    return r
