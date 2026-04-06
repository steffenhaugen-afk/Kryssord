"""
Henter definisjoner og synonymer fra NAOB (Det Norske Akademis Ordbok).

Strategi:
  For hvert ord i DB som mangler definisjon, henter vi siden
  https://naob.no/ordbok/{ord} og parser HTML for:
    - Korteste meningsbærende definisjon (lagres i ord.definisjon)
    - Synonymer nevnt i definisjon (lagres i synonymer med kilde='naob')

  NAOB bruker Sanity CMS som backend – ingen offentlig API.
  Vi scraper HTML direkte med 2 sekunders pause mellom requests.

Bruk:
    python scripts/hent_naob.py [--limit N] [--dry-run]

Krav:
    pip install -r scripts/requirements.txt
    DATABASE_URL satt i .env
"""
import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

ROOT    = Path(__file__).parent.parent
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

BASE_URL   = "https://naob.no/ordbok/"
USER_AGENT = "KryssordNorge/1.0 (hobby-prosjekt; norsk-kryssord-forskning)"
DELAY      = 2.0   # sekunder mellom requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "naob.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML-parser
# ---------------------------------------------------------------------------
def _strip_tags(html: str) -> str:
    """Fjerner HTML-tagger og normaliserer mellomrom."""
    tekst = re.sub(r"<[^>]+>", " ", html)
    tekst = re.sub(r"\s+", " ", tekst)
    return tekst.strip()


def parse_naob(html: str) -> dict:
    """
    Parser NAOB-side og returnerer dict med:
      - definisjon: str | None  – korteste definisjon (maks 200 tegn)
      - synonymer:  list[str]   – synonym-ord nevnt i teksten

    NAOB-HTML inneholder definisjoner i <span>-elementer med klasser som
    'article__definition' eller inne i JSON-data. Vi prøver begge tilnærminger.
    """
    resultat = {"definisjon": None, "synonymer": []}

    # Strategi 1: lett etter <span class="...definition...">tekst</span>
    definisjoner = re.findall(
        r'<[^>]*class="[^"]*(?:definition|betydning|forklaring)[^"]*"[^>]*>(.*?)</[^>]+>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if definisjoner:
        kandidater = [_strip_tags(d) for d in definisjoner if len(_strip_tags(d)) > 10]
        if kandidater:
            # Velg korteste meningsbærende definisjon (maks 200 tegn)
            kandidater.sort(key=len)
            resultat["definisjon"] = kandidater[0][:200]

    # Strategi 2: finn JSON-data med "definition" fra Sanity-backend
    if not resultat["definisjon"]:
        json_match = re.search(
            r'"definition"\s*:\s*\[(.*?)\]',
            html,
            re.DOTALL,
        )
        if json_match:
            tekst = _strip_tags(json_match.group(1))
            if 10 < len(tekst) < 300:
                resultat["definisjon"] = tekst[:200]

    # Strategi 3: hent første avsnitt med meningsinnhold
    if not resultat["definisjon"]:
        # NAOB legger definisjon i <p> med data-block-key eller lignende
        p_tekster = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL)
        for p in p_tekster:
            ren = _strip_tags(p)
            # Filtrer ut navigasjon, copyright o.l.
            if len(ren) > 20 and not any(
                ord_ in ren.lower()
                for ord_ in ["copyright", "cookie", "naob.no", "javascript"]
            ):
                resultat["definisjon"] = ren[:200]
                break

    return resultat


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def hent_ord_fra_db(conn, limit: int) -> list[tuple]:
    """Henter ord som mangler definisjon, prioritert etter frekvens."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT o.id, o.tekst
            FROM ord o
            WHERE o.har_bindestrek = false
              AND o.har_mellomrom  = false
              AND o.tekst ~ '^[a-zæøå]+$'
              AND o.bokstavlengde BETWEEN 3 AND 15
              AND o.ordklasse IN ('substantiv', 'verb', 'adjektiv')
              AND (o.definisjon IS NULL OR o.definisjon = '')
            ORDER BY o.frekvens DESC NULLS LAST, o.bokstavlengde
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def lagre_resultat(
    conn,
    ord_id: str,
    tekst: str,
    definisjon: str | None,
    synonymer: list[str],
    dry_run: bool,
) -> dict:
    stats = {"definisjon_lagret": 0, "nye_synonymer": 0}

    if dry_run or not definisjon:
        return stats

    with conn.cursor() as cur:
        # Lagre definisjon
        cur.execute(
            "UPDATE ord SET definisjon = %s WHERE id = %s",
            (definisjon, ord_id),
        )
        if cur.rowcount:
            stats["definisjon_lagret"] = 1

        # Lagre synonymer fra NAOB
        for syn_tekst in synonymer:
            cur.execute("SELECT id FROM ord WHERE tekst = %s", (syn_tekst.lower(),))
            syn_rad = cur.fetchone()
            if syn_rad:
                for a_id, b_id in [(ord_id, syn_rad[0]), (syn_rad[0], ord_id)]:
                    cur.execute(
                        """
                        INSERT INTO synonymer (ord_id, synonym_id, relasjon_type, kilde)
                        VALUES (%s, %s, 'synonym', 'naob')
                        ON CONFLICT (ord_id, synonym_id) DO NOTHING
                        """,
                        (a_id, b_id),
                    )
                    stats["nye_synonymer"] += cur.rowcount

    conn.commit()
    return stats


# ---------------------------------------------------------------------------
# Hoved-logikk
# ---------------------------------------------------------------------------
def hent_naob(ord_liste: list[tuple], conn, dry_run: bool) -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    total_stats = {
        "hentet": 0,
        "definisjoner_funnet": 0,
        "definisjoner_lagret": 0,
        "nye_synonymer": 0,
        "ikke_funnet": 0,
        "feil": 0,
    }

    for i, (ord_id, tekst) in enumerate(ord_liste):
        try:
            url  = f"{BASE_URL}{tekst}"
            resp = session.get(url, timeout=15)

            if resp.status_code == 404:
                total_stats["ikke_funnet"] += 1
                log.debug("Ikke funnet: %s", tekst)
            else:
                resp.raise_for_status()
                resp.encoding = "utf-8"

                parsed = parse_naob(resp.text)
                total_stats["hentet"] += 1

                if parsed["definisjon"]:
                    total_stats["definisjoner_funnet"] += 1
                    log.info(
                        "[%d/%d] %-15s → %s",
                        i + 1, len(ord_liste), tekst,
                        parsed["definisjon"][:80],
                    )
                else:
                    log.debug("[%d/%d] %-15s → (ingen definisjon)", i + 1, len(ord_liste), tekst)

                res = lagre_resultat(
                    conn, str(ord_id), tekst,
                    parsed["definisjon"], parsed["synonymer"],
                    dry_run,
                )
                total_stats["definisjoner_lagret"] += res["definisjon_lagret"]
                total_stats["nye_synonymer"]        += res["nye_synonymer"]

        except Exception as exc:
            total_stats["feil"] += 1
            log.warning("Feil for '%s': %s", tekst, exc)

        if i < len(ord_liste) - 1:
            time.sleep(DELAY)

    return total_stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Hent definisjoner fra NAOB")
    parser.add_argument("--limit",   type=int, default=200, help="Maks antall ord å hente")
    parser.add_argument("--dry-run", action="store_true",   help="Vis resultater uten å lagre")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        log.error("DATABASE_URL mangler"); sys.exit(1)

    conn = psycopg2.connect(db_url)

    log.info("=== Henter fra NAOB ===")
    log.info("Limit: %d ord%s", args.limit, " (DRY-RUN)" if args.dry_run else "")

    ord_liste = hent_ord_fra_db(conn, args.limit)
    log.info("Fant %d ord uten definisjon", len(ord_liste))

    if not ord_liste:
        log.info("Alle ord har allerede definisjon.")
        conn.close()
        return

    stats = hent_naob(ord_liste, conn, args.dry_run)
    conn.close()

    print("\n=== RAPPORT ===")
    print(f"  Ord hentet:               {stats['hentet']}")
    print(f"  Definisjoner funnet:      {stats['definisjoner_funnet']}")
    print(f"  Definisjoner lagret:      {stats['definisjoner_lagret']}")
    print(f"  Nye NAOB-synonymer:       {stats['nye_synonymer']}")
    print(f"  Ikke funnet (404):        {stats['ikke_funnet']}")
    print(f"  Feil:                     {stats['feil']}")
    if args.dry_run:
        print("  (DRY-RUN – ingenting ble lagret)")


if __name__ == "__main__":
    main()
