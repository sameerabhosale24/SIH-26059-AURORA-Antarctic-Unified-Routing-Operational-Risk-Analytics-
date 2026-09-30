"""
Create the demo operator.

    python scripts/seed_demo_user.py

Idempotent: an existing account is reported, never rewritten, so rerunning
after a password change does not silently reset it.
"""

import asyncio
import sys
from pathlib import Path

# `python scripts/seed_demo_user.py` puts scripts/, not the project root, on
# sys.path — add the root so `import app...` works exactly as documented.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import User
from app.security.password import hash_password

DEMO_EMAIL = "operator@aurora.demo"
DEMO_PASSWORD = "aurora123"


async def run() -> int:
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if existing is not None:
            print(f"Seed user already exists: {existing.email} (id={existing.id}, role={existing.role})")
            return 0

        user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD), role="operator")
        db.add(user)
        await db.commit()
        await db.refresh(user)

        print(f"Created seed user: {user.email} (id={user.id}, role={user.role})")
        print(f"Password: {DEMO_PASSWORD}")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run()))
    except Exception as exc:  # noqa: BLE001 — report and exit non-zero
        print(f"Seed failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
