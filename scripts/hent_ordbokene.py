"""
Henter norske bokmålsord fra Ordbøkene (via api.ordbokapi.org GraphQL)
og lagrer dem i PostgreSQL-tabellen "ord".

Datakilden er Bokmålsordboka (~70 000 artikler med sekvensiell ID).
Skriptet henter artikler i paralleliserte batches, filtrerer på ordklasse
og bokstavlengde, og lagrer resultatene i databasen.

Bruk:
    python scripts/hent_ordbokene.py [--start ID] [--end ID]

Krav:
    pip install -r scripts/requirements.txt
    DATABASE_URL satt i .env
"""
import argparse
import logging
import os
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Konfigurasjon
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

API_URL = "https://api.ordbokapi.org/graphql"
MAX_ARTICLE_ID = 70_000
BATCH_SIZE = 50          # artikler per GraphQL-kall
DB_BATCH_SIZE = 500      # ord per INSERT
REQUEST_DELAY = 0.4      # sekunder mellom kall
MAX_RETRIES = 5
RETRY_BACKOFF = 2.0

TARGET_CLASSES = {"Substantiv", "Verb", "Adjektiv"}
ORDKLASSE_MAP = {
    "Substantiv": "substantiv",
    "Verb":       "verb",
    "Adjektiv":   "adjektiv",
}
MIN_LEN = 3
MAX_LEN = 15

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "ordbokene.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GraphQL-spørring (henter en batch av artikler i ett kall via aliaser)
# ---------------------------------------------------------------------------
def build_batch_query(ids: list[int]) -> str:
    fragments = []
    for aid in ids:
        fragments.append(f"""
  a{aid}: article(id: {aid}, dictionary: Bokmaalsordboka) {{
    wordClass
    lemmas {{ lemma }}
  }}""")
    return "{\n" + "\n".join(fragments) + "\n}"


# ---------------------------------------------------------------------------
# Nettverkskall med retry
# ---------------------------------------------------------------------------
def post_with_retry(session: requests.Session, query: str) -> dict:
    delay = REQUEST_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.post(API_URL, json={"query": query}, timeout=30)

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", delay * 2))
                log.warning("Rate limit – venter %ss ...", wait)
                time.sleep(wait)
                continue

            if resp.status_code == 200:
                return resp.json().get("data") or {}

            log.warning("HTTP %s (forsøk %d/%d)", resp.status_code, attempt, MAX_RETRIES)

        except requests.RequestException as exc:
            log.warning("Nettverksfeil (forsøk %d/%d): %s", attempt, MAX_RETRIES, exc)

        if attempt < MAX_RETRIES:
            time.sleep(delay)
            delay *= RETRY_BACKOFF

    log.error("Alle %d forsøk feilet for batch", MAX_RETRIES)
    return {}


# ---------------------------------------------------------------------------
# Databasehjelp
# ---------------------------------------------------------------------------
def get_db(database_url: str):
    return psycopg2.connect(database_url)


def upsert_batch(conn, batch: list[tuple[str, str]]) -> int:
    if not batch:
        return 0
    sql = """
        INSERT INTO ord (tekst, ordklasse)
        VALUES %s
        ON CONFLICT (tekst) DO NOTHING
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, batch, page_size=500)
        inserted = cur.rowcount if cur.rowcount >= 0 else 0
    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Parsing av API-svar
# ---------------------------------------------------------------------------
def extract_words(data: dict) -> list[tuple[str, str]]:
    results = []
    for article in data.values():
        if not article:
            continue
        word_class = article.get("wordClass") or ""
        if word_class not in TARGET_CLASSES:
            continue
        ordklasse = ORDKLASSE_MAP[word_class]
        for lemma_obj in article.get("lemmas") or []:
            tekst = (lemma_obj.get("lemma") or "").strip().lower()
            if not tekst:
                continue
            if not (MIN_LEN <= len(tekst) <= MAX_LEN):
                continue
            if not all(c.isalpha() or c == "-" for c in tekst):
                continue
            results.append((tekst, ordklasse))
    return results


# ---------------------------------------------------------------------------
# Hovedprogram
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Hent ord fra Ordbøkene")
    parser.add_argument("--start", type=int, default=1,
                        help=f"Start-ID (standard: 1)")
    parser.add_argument("--end",   type=int, default=MAX_ARTICLE_ID,
                        help=f"Slutt-ID (standard: {MAX_ARTICLE_ID})")
    args = parser.parse_args()

    log.info("=== Ordbøkene-innhenting startet (ID %d–%d) ===", args.start, args.end)

    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL mangler i .env")
        sys.exit(1)

    conn = get_db(database_url)
    session = requests.Session()
    session.headers.update({"User-Agent": "KryssordNorge/1.0 (hobby-prosjekt)"})

    total_seen = 0
    total_inserted = 0
    db_batch: list[tuple[str, str]] = []

    all_ids = list(range(args.start, args.end + 1))
    num_batches = (len(all_ids) + BATCH_SIZE - 1) // BATCH_SIZE

    try:
        for batch_num, offset in enumerate(range(0, len(all_ids), BATCH_SIZE), 1):
            ids = all_ids[offset : offset + BATCH_SIZE]
            query = build_batch_query(ids)
            data = post_with_retry(session, query)

            words = extract_words(data)
            db_batch.extend(words)
            total_seen += len(words)

            if batch_num % 10 == 0:
                log.info(
                    "Batch %d/%d | ID %d | ord funnet: %d | lagret: %d",
                    batch_num, num_batches, ids[-1], total_seen, total_inserted,
                )

            if len(db_batch) >= DB_BATCH_SIZE:
                total_inserted += upsert_batch(conn, db_batch)
                db_batch.clear()

            time.sleep(REQUEST_DELAY)

    except KeyboardInterrupt:
        log.info("Avbrutt av bruker.")
    finally:
        if db_batch:
            total_inserted += upsert_batch(conn, db_batch)
        conn.close()

    log.info(
        "=== Ferdig. %d ord prosessert, %d lagret i databasen ===",
        total_seen, total_inserted,
    )


if __name__ == "__main__":
    main()
