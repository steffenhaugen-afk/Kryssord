"""
Kjør SQL-migrasjoner mot lokal PostgreSQL-database.

Bruk:
    python database/migrate.py
"""
import os
import sys
import psycopg2
from pathlib import Path

ROOT = Path(__file__).parent.parent
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
ENV_FILE = ROOT / ".env"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def get_connection():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("Feil: DATABASE_URL mangler i miljøvariabler / .env")
        sys.exit(1)
    return psycopg2.connect(url)


def ensure_migrations_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS _migrasjoner (
            id          SERIAL PRIMARY KEY,
            filnavn     TEXT NOT NULL UNIQUE,
            kjort_dato  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def already_run(cur, filename: str) -> bool:
    cur.execute("SELECT 1 FROM _migrasjoner WHERE filnavn = %s", (filename,))
    return cur.fetchone() is not None


def mark_run(cur, filename: str) -> None:
    cur.execute("INSERT INTO _migrasjoner (filnavn) VALUES (%s)", (filename,))


def run_migrations():
    load_env(ENV_FILE)
    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            ensure_migrations_table(cur)
            conn.commit()

            sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            if not sql_files:
                print("Ingen SQL-filer funnet i", MIGRATIONS_DIR)
                return

            ran = 0
            for sql_file in sql_files:
                if already_run(cur, sql_file.name):
                    print(f"  Hopper over (allerede kjort): {sql_file.name}")
                    continue

                print(f"  Kjorer: {sql_file.name} ...", end=" ")
                sql = sql_file.read_text(encoding="utf-8")
                cur.execute(sql)
                mark_run(cur, sql_file.name)
                conn.commit()
                print("OK")
                ran += 1

            if ran == 0:
                print("Ingen nye migrasjoner.")
            else:
                print(f"\n{ran} migrasjon(er) fullfort.")

            # Vis tabeller
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            tables = [r[0] for r in cur.fetchall()]
            print(f"\nTabeller i databasen: {', '.join(tables)}")

    except Exception as e:
        conn.rollback()
        print(f"\nFeil under migrasjon: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
