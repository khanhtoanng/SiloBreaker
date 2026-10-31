"""Create or update the demo accounts: python -m app.seed_users

Idempotent: re-running updates the existing rows by username instead of duplicating them.
Passwords are hashed before they reach the database and are never printed.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.db import get_session
from app.models import AppUser

DEMO_USERS = [
    {
        "username": "admin",
        "display_name": "Admin",
        "role": "admin",
        "person_id": None,
        "password": "Admin@123",
    },
    {
        "username": "alice",
        "display_name": "Alice",
        "role": "member",
        "person_id": "alice",
        "password": "Alice@123",
    },
    {
        "username": "bob",
        "display_name": "Bob",
        "role": "member",
        "person_id": "bob",
        "password": "Bob@123",
    },
    {
        "username": "carol",
        "display_name": "Carol",
        "role": "member",
        "person_id": "carol",
        "password": "Carol@123",
    },
    {
        # A new hire: candidate for the successor role, absent from the evidence.
        "username": "minh",
        "display_name": "Minh",
        "role": "member",
        "person_id": "minh",
        "password": "Minh@123",
    },
]


def seed_users(session: Session) -> list[tuple[str, str]]:
    """Upserts DEMO_USERS; returns (username, "created"|"updated") pairs."""
    results = []
    for spec in DEMO_USERS:
        user = session.scalar(select(AppUser).where(AppUser.username == spec["username"]))
        if user is None:
            user = AppUser(username=spec["username"])
            session.add(user)
            results.append((spec["username"], "created"))
        else:
            results.append((spec["username"], "updated"))
        user.display_name = spec["display_name"]
        user.role = spec["role"]
        user.person_id = spec["person_id"]
        user.password_hash = hash_password(spec["password"])
        user.is_active = True
    session.flush()
    return results


def main() -> None:
    for session in get_session():
        results = seed_users(session)
        session.commit()
        for username, outcome in results:
            print(f"{outcome}: {username}")


if __name__ == "__main__":
    main()
