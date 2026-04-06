"""
Henter ledetråd→svar-par fra kryssordkongen.no.

Strategi:
  For hvert ord vi søker med (/hint/?q={ord}), returnerer siden en liste
  over kryssordsvaret som passer til den ledetråden.
  Vi lagrer par (ledetrad=søkeord, svar=treff) i kryssord_ledetrad_par.

  I ledetrad_generator brukes tabellen omvendt:
  gitt et svar-ord → finn ledetråder som peker på det.

Bruk:
    python scripts/hent_kryssordkongen.py [--limit N] [--dry-run]

Krav:
    pip install -r scripts/requirements.txt
    DATABASE_URL satt i .env

Robots.txt: generisk crawler ikke eksplisitt blokkert.
Bruker 1,5 sekunder pause mellom requests.
"""
import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

ROOT    = Path(__file__).parent.parent
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

BASE_URL   = "https://kryssordkongen.no/hint/"
USER_AGENT = "KryssordNorge/1.0 (hobby-prosjekt; norsk-kryssord-forskning)"
DELAY      = 1.5   # sekunder mellom requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "kryssordkongen.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML-parser
# ---------------------------------------------------------------------------
def parse_svar(html: str) -> list[str]:
    """
    Parser tabellen i /hint/?q={ord} og returnerer svar-ord.

    Tabellstrukturen er: <td>{nr}</td><td>{SVAR}</td><td>{lengde}</td><td>…</td>
    Vi henter kolonnen med SVAR (ren tekst, kun bokstaver, 2–15 tegn).
    """
    svar = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        clean = [c for c in clean if c]
        # Typisk format: ['1', 'HUS', '3', '1']
        # Kolonnen med svar er index 1 (etter løpenummer)
        if len(clean) >= 2:
            kandidat = clean[1].upper()
            if re.match(r"^[A-ZÆØÅ]{2,15}$", kandidat):
                svar.append(kandidat)
    return svar


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def lagre_par(cur, ledetrad: str, svar_liste: list[str], kilde: str = "kryssordkongen") -> int:
    ny = 0
    for svar in svar_liste:
        cur.execute(
            """
            INSERT INTO kryssord_ledetrad_par (ledetrad, svar, kilde)
            VALUES (%s, %s, %s)
            ON CONFLICT (ledetrad, svar) DO NOTHING
            """,
            (ledetrad.lower(), svar.upper(), kilde),
        )
        ny += cur.rowcount
    return ny


def hent_ord_fra_db(conn, limit: int) -> list[str]:
    """
    Henter ord fra databasen som brukes som ledetråd-søkeord.
    Prioriterer:
    - Korte ord (2-6 bokstaver) – brukes hyppig som kryssordledetråder
    - Vanlige ordklasser
    - Ord vi ikke allerede har hentet for
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT o.tekst
            FROM ord o
            WHERE o.har_bindestrek = false
              AND o.har_mellomrom  = false
              AND o.tekst ~ '^[a-zæøå]+$'
              AND o.bokstavlengde BETWEEN 3 AND 10
              AND o.ordklasse IN ('substantiv', 'verb', 'adjektiv')
              AND NOT EXISTS (
                  SELECT 1 FROM kryssord_ledetrad_par p
                  WHERE p.ledetrad = o.tekst
              )
            ORDER BY o.bokstavlengde, random()
            LIMIT %s
            """,
            (limit,),
        )
        return [row[0] for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Hoved-logikk
# ---------------------------------------------------------------------------
def hent_par(ord_liste: list[str], conn, dry_run: bool) -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    stats = {"hentet": 0, "ny_par": 0, "feil": 0, "ord_uten_svar": 0}

    for i, ord_ in enumerate(ord_liste):
        try:
            url = f"{BASE_URL}?q={ord_}"
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            resp.encoding = "utf-8"

            svar_liste = parse_svar(resp.text)
            stats["hentet"] += 1

            if not svar_liste:
                stats["ord_uten_svar"] += 1
                log.debug("Ingen svar for: %s", ord_)
            else:
                if not dry_run:
                    with conn.cursor() as cur:
                        ny = lagre_par(cur, ord_, svar_liste)
                        stats["ny_par"] += ny
                    conn.commit()
                log.info(
                    "[%d/%d] %-15s → %d svar (f.eks. %s)",
                    i + 1, len(ord_liste), ord_,
                    len(svar_liste), ", ".join(svar_liste[:4]),
                )

        except Exception as exc:
            stats["feil"] += 1
            log.warning("Feil for '%s': %s", ord_, exc)

        if i < len(ord_liste) - 1:
            time.sleep(DELAY)

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Hent ledetråd/svar-par fra kryssordkongen.no")
    parser.add_argument("--limit",   type=int, default=500, help="Maks antall ord å søke")
    parser.add_argument("--dry-run", action="store_true",   help="Vis resultater uten å lagre")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        log.error("DATABASE_URL mangler"); sys.exit(1)

    conn = psycopg2.connect(db_url)

    log.info("=== Henter fra kryssordkongen.no ===")
    log.info("Limit: %d ord%s", args.limit, " (DRY-RUN)" if args.dry_run else "")

    ord_liste = hent_ord_fra_db(conn, args.limit)
    log.info("Fant %d ord å søke etter", len(ord_liste))

    if not ord_liste:
        log.info("Ingen nye ord å hente – alt er allerede hentet.")
        conn.close()
        return

    stats = hent_par(ord_liste, conn, args.dry_run)
    conn.close()

    print("\n=== RAPPORT ===")
    print(f"  Ord søkt:           {stats['hentet']}")
    print(f"  Nye par lagret:     {stats['ny_par']}")
    print(f"  Ord uten svar:      {stats['ord_uten_svar']}")
    print(f"  Feil:               {stats['feil']}")

    # Vis totalt antall par i DB
    conn2 = psycopg2.connect(db_url)
    with conn2.cursor() as cur:
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT svar) FROM kryssord_ledetrad_par")
        total_par, unike_svar = cur.fetchone()
    conn2.close()
    print(f"\n  Totalt i DB: {total_par} par ({unike_svar} unike svar)")


if __name__ == "__main__":
    main()
