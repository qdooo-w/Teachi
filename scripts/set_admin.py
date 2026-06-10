#!/usr/bin/env python3
"""Set an existing user role to admin by email.

Usage:
    uv run python scripts/set_admin.py user@example.com
    uv run python scripts/set_admin.py user@example.com --db data/project.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv(PROJECT_ROOT / ".env")

from backend.config import DATABASE_PATH  # noqa: E402
from backend.db import DatabaseFacade  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set an existing user role to admin by email.")
    parser.add_argument("email", help="Email of the existing user.")
    parser.add_argument(
        "--db",
        dest="database_path",
        default=DATABASE_PATH,
        help=f"SQLite database path. Defaults to DATABASE_PATH ({DATABASE_PATH}).",
    )
    return parser.parse_args()


def get_user_by_email(conn: sqlite3.Connection, email: str) -> dict | None:
    row = conn.execute(
        """
        SELECT uuid, username, email, role
        FROM users
        WHERE email = ?
        """,
        (email,),
    ).fetchone()
    return dict(row) if row else None


def set_admin(email: str, database_path: str) -> int:
    email = email.strip()
    if not email:
        print("Email cannot be empty.", file=sys.stderr)
        return 2

    db_path = Path(database_path)
    if not db_path.exists():
        print(f"Database does not exist: {db_path}", file=sys.stderr)
        return 1

    db = DatabaseFacade(str(db_path))
    try:
        with closing(db.get_connection()) as conn:
            user = get_user_by_email(conn, email)
            if user is None:
                print(f"User not found for email: {email}", file=sys.stderr)
                return 1

            old_role = user.get("role") or "user"
            if old_role == "admin":
                print(f"User is already admin: {user['email']} ({user['uuid']})")
                return 0

            conn.execute("UPDATE users SET role = ? WHERE uuid = ?", ("admin", user["uuid"]))
            conn.commit()
            updated = get_user_by_email(conn, email)
    except sqlite3.OperationalError as exc:
        print(f"Failed to update user role: {exc}", file=sys.stderr)
        return 1

    if updated is None or updated.get("role") != "admin":
        print("Role update did not persist.", file=sys.stderr)
        return 1

    print("User role updated.")
    print(f"UUID: {updated['uuid']}")
    print(f"Username: {updated['username']}")
    print(f"Email: {updated['email']}")
    print(f"Role: {old_role} -> admin")
    return 0


def main() -> int:
    args = parse_args()
    return set_admin(args.email, args.database_path)


if __name__ == "__main__":
    raise SystemExit(main())
