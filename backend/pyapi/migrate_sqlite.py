"""One-time, non-destructive SQLite to PostgreSQL copy for the existing API."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from .workspace_store import BACKUP_TABLES, ROOT


JSON_COLUMNS = {"body", "sources", "input", "output", "response", "detail", "payload"}


def migrate(sqlite_file: Path, database_url: str, apply: bool = False) -> dict[str, int]:
    if not sqlite_file.is_file():
        raise ValueError(f"SQLite 파일을 찾을 수 없습니다: {sqlite_file}")
    if apply and not database_url:
        raise ValueError("DATABASE_URL이 필요합니다.")
    source = sqlite3.connect(f"file:{sqlite_file.resolve().as_posix()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        counts = {table: source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in BACKUP_TABLES}
        if not apply:
            return counts
        with psycopg.connect(database_url) as target:
            with target.cursor() as cursor:
                for table in BACKUP_TABLES:
                    cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
                    if cursor.fetchone()[0]:
                        raise ValueError("PostgreSQL 대상 테이블에 자료가 있습니다. 빈 별도 DB로 이전해 주세요.")
                for table in BACKUP_TABLES:
                    rows = source.execute(f"SELECT * FROM {table}").fetchall()
                    for row in rows:
                        columns = row.keys()
                        values = []
                        for key in columns:
                            value = row[key]
                            if key in JSON_COLUMNS and value is not None:
                                value = Jsonb(json.loads(value))
                            elif key == "active":
                                value = bool(value)
                            values.append(value)
                        query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                            sql.Identifier(table),
                            sql.SQL(",").join(map(sql.Identifier, columns)),
                            sql.SQL(",").join(sql.Placeholder() for _ in columns),
                        )
                        cursor.execute(query, values)
        return counts
    finally:
        source.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy an existing SQLite workspace into an empty PostgreSQL database")
    parser.add_argument("--sqlite", required=True, type=Path, help="Path to the existing SQLite file")
    parser.add_argument("--apply", action="store_true", help="Perform the copy; default is a read-only count preview")
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        env_file = ROOT / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.strip().partition("=")
                if separator and key == "DATABASE_URL":
                    database_url = value.strip().strip("\"'")
                    break
    counts = migrate(args.sqlite, database_url, apply=args.apply)
    print(("Copied" if args.apply else "Would copy") + ": " + ", ".join(f"{name}={count}" for name, count in counts.items()))


if __name__ == "__main__":
    main()
