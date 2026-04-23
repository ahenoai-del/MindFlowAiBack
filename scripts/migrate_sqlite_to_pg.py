"""
Миграция данных из SQLite в PostgreSQL.

Использование:
    python scripts/migrate_sqlite_to_pg.py --sqlite mindflow.db --pg postgresql://user:pass@localhost:5432/mindflow

Требования:
    pip install aiosqlite asyncpg
"""
import argparse
import asyncio
import json
import sqlite3
import sys

import asyncpg


TABLES_ORDER = [
    "users",
    "tasks",
    "plans",
    "stats",
    "gamification",
    "reminders",
    "push_subscriptions",
]


async def migrate(sqlite_path: str, pg_url: str):
    conn_pg = await asyncpg.connect(pg_url)
    conn_sql = sqlite3.connect(sqlite_path)
    conn_sql.row_factory = sqlite3.Row

    try:
        for table in TABLES_ORDER:
            print(f"\n--- Migrating table: {table} ---")
            cursor = conn_sql.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            if not rows:
                print(f"  No rows in {table}, skipping.")
                continue

            columns = rows[0].keys()
            print(f"  Columns: {list(columns)}")
            print(f"  Row count: {len(rows)}")

            placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
            col_names = ", ".join(columns)
            insert_sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"

            migrated = 0
            errors = 0
            for row in rows:
                values = []
                for col in columns:
                    val = row[col]
                    if table == "users" and col == "is_premium":
                        val = bool(val)
                    elif table == "reminders" and col == "sent":
                        val = bool(val)
                    values.append(val)

                try:
                    await conn_pg.execute(insert_sql, *values)
                    migrated += 1
                except Exception as e:
                    errors += 1
                    if errors <= 3:
                        print(f"  ERROR on row: {e}")
                    if errors == 3:
                        print(f"  ... suppressing further errors for {table}")

            print(f"  Migrated: {migrated}, Errors: {errors}")

        print("\n--- Verifying row counts ---")
        for table in TABLES_ORDER:
            sqlite_count = conn_sql.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            pg_row = await conn_pg.fetchrow(f"SELECT COUNT(*) as cnt FROM {table}")
            pg_count = pg_row["cnt"]
            status = "OK" if sqlite_count == pg_count else "MISMATCH"
            print(f"  {table}: SQLite={sqlite_count}, PostgreSQL={pg_count} [{status}]")

    finally:
        conn_sql.close()
        await conn_pg.close()

    print("\nMigration complete!")


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite to PostgreSQL")
    parser.add_argument("--sqlite", required=True, help="Path to SQLite database file")
    parser.add_argument("--pg", required=True, help="PostgreSQL connection URL")
    args = parser.parse_args()

    asyncio.run(migrate(args.sqlite, args.pg))


if __name__ == "__main__":
    main()
