"""Support tools for the command line.

Create the first support account:
    uv run python -m askdb.cli create-user --username NAME --role support
"""

from __future__ import annotations

import argparse
import getpass
import os
import sqlite3
import sys
from pathlib import Path

from askdb.appdb import init_schema, open_appdb
from askdb.auth import MIN_PASSWORD_LENGTH, create_user
from askdb.config import load_settings
from askdb.main import CONFIG_DIR_ENV


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="askdb")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("create-user", help="create an account")
    add.add_argument("--username", required=True)
    add.add_argument("--role", choices=["support", "analyst"], default="analyst")
    args = parser.parse_args(argv)

    config_dir = Path(os.environ.get(CONFIG_DIR_ENV, "config"))
    settings = load_settings(config_dir / "settings.yaml")
    db_path = Path(settings.app_db_path)
    init_schema(db_path)

    password = getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Repeat password: ") != password:
        print("Passwords do not match.", file=sys.stderr)
        return 1

    try:
        with open_appdb(db_path) as conn:
            user = create_user(conn, args.username, password, args.role)
    except sqlite3.IntegrityError:
        print(f"Username {args.username} already exists.", file=sys.stderr)
        return 1
    print(f"Created {user.role} account {user.username}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
