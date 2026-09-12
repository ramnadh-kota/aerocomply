"""One-time bootstrap: create the first PLATFORM_ADMIN user in a
deployment.

There is deliberately no public API endpoint for this (PLATFORM_MANAGE
cannot be self-granted — see app/api/v1/platform.py), so the very first
platform admin has to be created by someone with direct database access.
This script does that safely and idempotently instead of requiring raw
SQL against production: it reuses the exact same password hashing and
model classes the application itself uses.

Usage (reads DATABASE_URL from the environment, same as the app):

    DATABASE_URL=postgresql+psycopg://... \\
        python scripts/create_platform_admin.py \\
        --email ops@yourcompany.com \\
        --full-name "Platform Ops" \\
        --password 'a-strong-password'

Safe to re-run: if a user with that email already exists, the script
reports it and exits without modifying anything.
"""

import argparse
import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import hash_password  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--organization-name",
        default="Platform Operations",
        help="Name of the internal organization the platform admin belongs to "
        "(created if it doesn't already exist). Default: 'Platform Operations'.",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db: Session = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.email == args.email)).scalar_one_or_none()
        if existing is not None:
            print(
                f"A user with email {args.email!r} already exists (id={existing.id}). "
                "Nothing to do."
            )
            return

        org = db.execute(
            select(Organization).where(Organization.name == args.organization_name)
        ).scalar_one_or_none()
        if org is None:
            org = Organization(name=args.organization_name)
            db.add(org)
            db.flush()
            print(f"Created organization {args.organization_name!r} (id={org.id}).")

        user = User(
            organization_id=org.id,
            email=args.email,
            hashed_password=hash_password(args.password),
            full_name=args.full_name,
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_name="PLATFORM_ADMIN", organization_id=org.id))
        db.commit()
        print(f"Created PLATFORM_ADMIN user {args.email!r} (id={user.id}).")
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
