from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class MigrationError(RuntimeError):
    """Raised when schema migration state is inconsistent."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    applied: bool = False


def migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def load_migrations(path: Path | None = None) -> list[Migration]:
    root = path or migrations_dir()
    migrations: list[Migration] = []
    for candidate in sorted(root.glob("*.sql")):
        prefix, _, name = candidate.stem.partition("_")
        if not prefix.isdigit() or not name:
            continue
        text = candidate.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=int(prefix),
                name=name,
                path=candidate,
                checksum=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    versions = [migration.version for migration in migrations]
    if len(versions) != len(set(versions)):
        raise MigrationError("duplicate schema migration versions")
    return migrations


def ensure_migration_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        create table if not exists schema_migrations (
            version    integer primary key,
            name       text not null,
            checksum   text not null,
            applied_at text not null
        )
        """
    )


def applied_migrations(db: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    ensure_migration_table(db)
    return {
        int(row["version"]): row
        for row in db.execute(
            """
            select version, name, checksum, applied_at
            from schema_migrations
            order by version
            """
        )
    }


def migration_status(db: sqlite3.Connection) -> list[Migration]:
    applied = applied_migrations(db)
    status: list[Migration] = []
    for migration in load_migrations():
        row = applied.get(migration.version)
        if row is not None and row["checksum"] != migration.checksum:
            raise MigrationError(
                f"applied migration {migration.version} checksum changed"
            )
        status.append(
            Migration(
                version=migration.version,
                name=migration.name,
                path=migration.path,
                checksum=migration.checksum,
                applied=row is not None,
            )
        )
    return status


def run_migrations(db: sqlite3.Connection, *, dry_run: bool = False) -> list[Migration]:
    ensure_migration_table(db)
    applied = applied_migrations(db)
    completed: list[Migration] = []
    for migration in load_migrations():
        row = applied.get(migration.version)
        if row is not None:
            if row["checksum"] != migration.checksum:
                raise MigrationError(
                    f"applied migration {migration.version} checksum changed"
                )
            continue
        if dry_run:
            completed.append(migration)
            continue
        sql = migration.path.read_text(encoding="utf-8")
        try:
            db.execute("begin")
            for statement in sql_statements(sql):
                db.execute(statement)
            db.execute(
                """
                insert into schema_migrations(version, name, checksum, applied_at)
                values (?, ?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        completed.append(migration)
    return completed


def sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in sql:
        current.append(char)
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == ";":
            statement = "".join(current).strip().rstrip(";").strip()
            current = []
            if statement:
                statements.append(statement)
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements
