"""Reset the StockSense database to empty tables.

    venv\\Scripts\\python.exe reset_db.py --yes

Reads DB_HOST / DB_USER / DB_PASSWORD / DB_NAME from .env, creates the database
if it does not exist, then runs schema.sql (drop + create every table). The
database itself is not dropped, so a running Flask server keeps working. Also
removes seed_demo_state.json because every seeded row is gone.
"""
import argparse
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
SCHEMA = HERE / "schema.sql"
STATE_FILE = HERE / "seed_demo_state.json"


def main():
    parser = argparse.ArgumentParser(description="Drop and recreate every StockSense table.")
    parser.add_argument("--yes", action="store_true", help="required; this deletes every row in every table")
    args = parser.parse_args()
    if not args.yes:
        print("This deletes every user, watchlist and price row. Re-run with --yes to confirm.")
        return 2

    db_name = os.getenv("DB_NAME") or "stock_watchlist"
    conn = pymysql.connect(host=os.getenv("DB_HOST"), user=os.getenv("DB_USER"),
                           password=os.getenv("DB_PASSWORD"), autocommit=True)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
    cur.execute(f"USE `{db_name}`")

    # Drop comment lines before splitting on ";" so a semicolon inside a comment cannot break a statement.
    sql = "\n".join(line for line in SCHEMA.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("--"))
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for statement in statements:
        cur.execute(statement)

    cur.execute("SHOW TABLES")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    print(f"database `{db_name}` reset: {len(tables)} empty tables ({', '.join(tables)})")
    print("next: venv\\Scripts\\python.exe seed_demo_data.py --arm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
