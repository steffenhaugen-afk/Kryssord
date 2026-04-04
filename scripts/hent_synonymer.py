"""
Henter norske synonympar fra ordbokapi.org og lagrer i PostgreSQL-tabellen "synonymer".

  Kilde – ordbokapi.org GraphQL (Bokmaalsordboka):
    Itererer gjennom ~70 000 artikler og trekker ut Synonym- og Antonym-relasjoner.

Kun ord som allerede finnes i "ord"-tabellen kobles sammen.
INSERT ON CONFLICT DO NOTHING sikrer idempotens.

Bruk:
    python scripts/hent_synonymer.py [--start ID] [--end ID]

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
ROOT    = Path(__file__).parent.parent
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

ORDBOKAPI_URL   = "https://api.ordbokapi.org/graphql"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT      = "KryssordNorge/1.0 (hobby-prosjekt; python)"

MAX_ARTICLE_ID  = 70_000
ARTICLE_BATCH   = 40       # artikler per GraphQL-kall
DB_FLUSH_EVERY  = 1_000    # synonympar før mellomlagring
REQUEST_DELAY   = 0.35

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "synonymer.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_db(database_url: str):
    return psycopg2.connect(database_url)


def load_ord_lookup(conn) -> dict[str, str]:
    """Returnerer {tekst: id} for alle rader i ord-tabellen."""
    with conn.cursor() as cur:
        cur.execute("SELECT tekst, id FROM ord")
        return {row[0]: str(row[1]) for row in cur.fetchall()}


def insert_synonympar(conn, batch: list[tuple]) -> int:
    """
    batch: liste av (ord_id, synonym_id, relasjon_type, kilde)
    Returnerer antall faktisk innsatte rader.
    """
    if not batch:
        return 0
    sql = """
        INSERT INTO synonymer (ord_id, synonym_id, relasjon_type, kilde)
        VALUES %s
        ON CONFLICT ON CONSTRAINT uq_synonym_par DO NOTHING
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, batch, page_size=500)
        n = cur.rowcount if cur.rowcount >= 0 else 0
    conn.commit()
    return n


# ---------------------------------------------------------------------------
# GraphQL-batch-bygging
# ---------------------------------------------------------------------------
def build_batch_query(ids: list[int]) -> str:
    frags = []
    for aid in ids:
        frags.append(f"""
  a{aid}: article(id: {aid}, dictionary: Bokmaalsordboka) {{
    lemmas {{ lemma }}
    relationships {{
      type
      article {{ lemmas {{ lemma }} }}
    }}
  }}""")
    return "{" + "".join(frags) + "\n}"


def post_with_retry(
    session: requests.Session, query: str, max_retries: int = 5
) -> dict:
    delay = REQUEST_DELAY
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(ORDBOKAPI_URL, json={"query": query}, timeout=30)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", delay * 3))
                log.warning("Rate limit – venter %ss", wait)
                time.sleep(wait)
                continue
            if resp.status_code == 200:
                return resp.json().get("data") or {}
            log.warning("HTTP %s (forsøk %d/%d)", resp.status_code, attempt, max_retries)
        except requests.RequestException as exc:
            log.warning("Nettverksfeil (forsøk %d/%d): %s", attempt, max_retries, exc)
        time.sleep(delay)
        delay *= 2
    return {}


# ---------------------------------------------------------------------------
# Kilde 1: ordbokapi.org
# ---------------------------------------------------------------------------
def hent_fra_ordbokapi(
    conn,
    ord_lookup: dict[str, str],
    start_id: int = 1,
    end_id: int = MAX_ARTICLE_ID,
) -> tuple[int, int]:
    """Returnerer (antall_sett, antall_lagret)."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    all_ids   = list(range(start_id, end_id + 1))
    n_batches = (len(all_ids) + ARTICLE_BATCH - 1) // ARTICLE_BATCH

    pending: list[tuple] = []
    total_seen = total_saved = 0

    log.info("Starter ordbokapi.org – %d artikler i %d batcher", len(all_ids), n_batches)

    for batch_num, offset in enumerate(range(0, len(all_ids), ARTICLE_BATCH), 1):
        ids   = all_ids[offset : offset + ARTICLE_BATCH]
        query = build_batch_query(ids)
        data  = post_with_retry(session, query)

        for article in data.values():
            if not article:
                continue
            base_lemmas = [
                l["lemma"].strip().lower()
                for l in (article.get("lemmas") or [])
                if l.get("lemma")
            ]
            syn_rels = [
                r for r in (article.get("relationships") or [])
                if r.get("type") in ("Synonym", "Antonym")
            ]
            for rel in syn_rels:
                syn_lemmas = [
                    l["lemma"].strip().lower()
                    for l in (rel.get("article", {}).get("lemmas") or [])
                    if l.get("lemma")
                ]
                for base in base_lemmas:
                    base_id = ord_lookup.get(base)
                    if not base_id:
                        continue
                    for syn in syn_lemmas:
                        syn_id = ord_lookup.get(syn)
                        if not syn_id or syn_id == base_id:
                            continue
                        total_seen += 1
                        relasjon = rel.get("type", "Synonym").lower()
                        # Lagre begge retninger
                        pending.append((base_id, syn_id, relasjon, "ordbokapi"))
                        pending.append((syn_id, base_id, relasjon, "ordbokapi"))

        if len(pending) >= DB_FLUSH_EVERY:
            # Dedupliser før INSERT
            pending = list({p[:2]: p for p in pending}.values())
            total_saved += insert_synonympar(conn, pending)
            pending.clear()

        if batch_num % 200 == 0:
            log.info(
                "  ordbokapi batch %d/%d | sett: %d | lagret: %d",
                batch_num, n_batches, total_seen, total_saved,
            )
        time.sleep(REQUEST_DELAY)

    if pending:
        pending = list({p[:2]: p for p in pending}.values())
        total_saved += insert_synonympar(conn, pending)

    log.info(
        "ordbokapi ferdig: %d synonympar sett, %d lagret", total_seen, total_saved
    )
    return total_seen, total_saved


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------
def generer_rapport(conn) -> None:
    log.info("\n========== RAPPORT ==========")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM synonymer")
        total = cur.fetchone()[0]
        log.info("Totalt synonympar i databasen: %d", total)

        cur.execute(
            "SELECT kilde, COUNT(*) FROM synonymer GROUP BY kilde ORDER BY COUNT(*) DESC"
        )
        log.info("Fordeling per kilde:")
        for row in cur.fetchall():
            log.info("  %-15s %d", row[0], row[1])

        cur.execute("""
            SELECT relasjon_type, COUNT(*)
            FROM synonymer
            GROUP BY relasjon_type
            ORDER BY COUNT(*) DESC
        """)
        log.info("Fordeling per relasjonstype:")
        for row in cur.fetchall():
            log.info("  %-15s %d", row[0], row[1])

        cur.execute("""
            SELECT o.tekst, COUNT(s.synonym_id) AS antall_synonymer
            FROM synonymer s
            JOIN ord o ON o.id = s.ord_id
            GROUP BY o.tekst
            ORDER BY antall_synonymer DESC
            LIMIT 10
        """)
        log.info("Topp 10 ord med flest synonymer:")
        for row in cur.fetchall():
            log.info("  %-20s %d", row[0], row[1])
    log.info("==============================\n")


# ---------------------------------------------------------------------------
# Hovedprogram
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Hent synonymer fra ordbokapi.org og Wikidata")
    parser.add_argument("--start", type=int, default=1,
                        help="Start-artikkel-ID (standard: 1)")
    parser.add_argument("--end", type=int, default=MAX_ARTICLE_ID,
                        help=f"Slutt-artikkel-ID (standard: {MAX_ARTICLE_ID})")
    args = parser.parse_args()

    log.info("=== Synonyminnhenting startet (ID %d–%d) ===", args.start, args.end)

    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL mangler i .env")
        sys.exit(1)

    conn = get_db(database_url)

    log.info("Laster ord-oppslag fra databasen ...")
    ord_lookup = load_ord_lookup(conn)
    log.info("  %d ord lastet inn i minnet", len(ord_lookup))

    sett, lagret = hent_fra_ordbokapi(conn, ord_lookup, args.start, args.end)

    generer_rapport(conn)
    conn.close()

    log.info("=== Ferdig. %d synonympar sett, %d nye lagret. ===", sett, lagret)


if __name__ == "__main__":
    main()
