"""
Henter norske egennavn fra Wikidata SPARQL og lagrer i PostgreSQL.

Kategorier:
  - Norske politikere
  - Norske kommuner og byer
  - Norske fjell
  - Norske kunstnere og musikere
  - Europeiske land
  - Verdens land
  - Verdens byer
  - Norske fornavn
  - Norske etternavn

For personnavn lagres fornavn og etternavn som separate oppslag
slik at hvert ord kan brukes som kryssordsvar.

Bruk:
    python scripts/hent_wikidata.py

Krav:
    pip install -r scripts/requirements.txt
    DATABASE_URL satt i .env
"""
import logging
import os
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from SPARQLWrapper import SPARQLWrapper, JSON

# ---------------------------------------------------------------------------
# Konfigurasjon
# ---------------------------------------------------------------------------
ROOT    = Path(__file__).parent.parent
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT      = "KryssordNorge/1.0 (hobby-prosjekt; python SPARQLWrapper)"

MIN_LEN = 2
MAX_LEN = 25
REQUEST_DELAY = 2.5  # Wikidata ber om minst 1s mellom kall

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "wikidata.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SPARQL-spørringer
#
# split_names=True:  flerleddsnavn brytes opp til enkeltord (fornavn/etternavn)
# split_names=False: kun enkeltord beholdes (steder, land osv.)
# ---------------------------------------------------------------------------
QUERIES: list[dict] = [
    {
        "kategori":    "Norske politikere",
        "beskrivelse": "Norske politikere hentet fra Wikidata",
        "split_names": True,
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P27  wd:Q20 ;
        wdt:P106 wd:Q82955 .
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 5000
        """,
    },
    {
        "kategori":    "Norske kommuner og byer",
        "beskrivelse": "Norske kommuner og byer hentet fra Wikidata",
        "split_names": False,
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  {
    ?item wdt:P31 wd:Q755707 .
  } UNION {
    ?item wdt:P31 wd:Q1115575 .
  } UNION {
    ?item wdt:P17 wd:Q20 ;
          wdt:P31 wd:Q515 .
  }
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 2000
        """,
    },
    {
        "kategori":    "Norske fjell",
        "beskrivelse": "Norske fjell hentet fra Wikidata",
        "split_names": False,
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P17 wd:Q20 ;
        wdt:P31 wd:Q8502 .
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 5000
        """,
    },
    {
        "kategori":    "Norske kunstnere og musikere",
        "beskrivelse": "Norske kunstnere og musikere hentet fra Wikidata",
        "split_names": True,
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P27 wd:Q20 .
  {
    ?item wdt:P106 wd:Q483501 .
  } UNION {
    ?item wdt:P106 wd:Q639669 .
  } UNION {
    ?item wdt:P106 wd:Q177220 .
  } UNION {
    ?item wdt:P106 wd:Q1028181 .
  }
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 5000
        """,
    },
    {
        "kategori":    "Europeiske land",
        "beskrivelse": "Europeiske land på norsk hentet fra Wikidata",
        "split_names": False,
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P30 wd:Q46 ;
        wdt:P31 wd:Q6256 .
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 200
        """,
    },
    {
        "kategori":    "Verdens land",
        "beskrivelse": "Alle suverene land i verden på norsk hentet fra Wikidata",
        "split_names": False,
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P31 wd:Q3624078 .   # suverent land
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 500
        """,
    },
    {
        "kategori":    "Verdens byer",
        "beskrivelse": "Store byer i verden på norsk hentet fra Wikidata",
        "split_names": False,
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P31 wd:Q515 .        # by
  ?item wdt:P1082 ?pop .         # innbyggertall
  FILTER(?pop > 500000)
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 2000
        """,
    },
    {
        "kategori":    "Norske fornavn",
        "beskrivelse": "Norske fornavn hentet fra Wikidata",
        "split_names": False,
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P31 wd:Q202444 .     # mannlig fornavn
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 3000
        """,
    },
    {
        "kategori":    "Norske fornavn",
        "beskrivelse": "Norske fornavn hentet fra Wikidata",
        "split_names": False,
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P31 wd:Q11879590 .   # kvinnelig fornavn
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 3000
        """,
    },
    {
        "kategori":    "Norske etternavn",
        "beskrivelse": "Norske etternavn hentet fra Wikidata",
        "split_names": False,
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P31 wd:Q101352 .     # etternavn
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 5000
        """,
    },
]

# ---------------------------------------------------------------------------
# Database-hjelp
# ---------------------------------------------------------------------------
def get_db(database_url: str):
    return psycopg2.connect(database_url)


def upsert_ord(cur, tekst: str) -> str:
    cur.execute("""
        INSERT INTO ord (tekst, ordklasse)
        VALUES (%s, 'egennavn')
        ON CONFLICT (tekst) DO UPDATE SET ordklasse = EXCLUDED.ordklasse
        RETURNING id
    """, (tekst,))
    return cur.fetchone()[0]


def upsert_kategori(cur, navn: str, beskrivelse: str) -> str:
    cur.execute("""
        INSERT INTO kategorier (navn, beskrivelse)
        VALUES (%s, %s)
        ON CONFLICT (navn) DO UPDATE SET beskrivelse = EXCLUDED.beskrivelse
        RETURNING id
    """, (navn, beskrivelse))
    return cur.fetchone()[0]


def link_ord_kategori(cur, ord_id: str, kategori_id: str) -> None:
    cur.execute("""
        INSERT INTO ord_kategorier (ord_id, kategori_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
    """, (ord_id, kategori_id))


# ---------------------------------------------------------------------------
# Parsing av navn
# ---------------------------------------------------------------------------
def parse_names(raw_navn: str, split_names: bool) -> list[str]:
    """
    Gjør om et råtnavn fra Wikidata til lagringsklar(e) tekst(er).

    - split_names=False: kun enkeltord beholdes (steder, land)
    - split_names=True:  hvert mellomromseparert ledd lagres separat
      slik at "Jonas Gahr Støre" gir ["jonas", "gahr", "støre"]
    """
    navn = raw_navn.strip()
    if not navn:
        return []

    if " " not in navn:
        tekst = navn.lower()
        if _valid(tekst):
            return [tekst]
        return []

    if not split_names:
        return []

    # Split på mellomrom — behold hvert ledd som er gyldig
    results = []
    for ledd in navn.split():
        tekst = ledd.lower().strip(".,-()")
        if _valid(tekst):
            results.append(tekst)
    return results


def _valid(tekst: str) -> bool:
    return (
        MIN_LEN <= len(tekst) <= MAX_LEN
        and all(c.isalpha() or c in "-'" for c in tekst)
    )


# ---------------------------------------------------------------------------
# SPARQL-kall
# ---------------------------------------------------------------------------
def run_sparql(sparql: SPARQLWrapper, query: str) -> list[str]:
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    try:
        results = sparql.query().convert()
    except Exception as exc:
        log.error("SPARQL-feil: %s", exc)
        return []
    return [
        row["navn"]["value"]
        for row in results.get("results", {}).get("bindings", [])
        if row.get("navn", {}).get("value")
    ]


# ---------------------------------------------------------------------------
# Prosessering per kategori
# ---------------------------------------------------------------------------
def process_category(conn, sparql: SPARQLWrapper, query_def: dict) -> int:
    kategori_navn  = query_def["kategori"]
    split_names    = query_def.get("split_names", False)

    log.info("--- Henter: %s (split=%s) ---", kategori_navn, split_names)

    raw_names = run_sparql(sparql, query_def["sparql"])
    log.info("  Rådata fra Wikidata: %d treff", len(raw_names))

    words: list[str] = []
    for raw in raw_names:
        words.extend(parse_names(raw, split_names))

    # Dedupliser (innen denne batchen)
    words = list(dict.fromkeys(words))
    log.info("  Unike kryssordvennlige ord: %d", len(words))

    if not words:
        return 0

    inserted = 0
    with conn.cursor() as cur:
        kategori_id = upsert_kategori(cur, kategori_navn, query_def["beskrivelse"])

        for tekst in words:
            try:
                ord_id = upsert_ord(cur, tekst)
                link_ord_kategori(cur, ord_id, kategori_id)
                inserted += 1
            except Exception as exc:
                log.warning("Feil for '%s': %s", tekst, exc)
                conn.rollback()
                cur.execute(
                    "SELECT id FROM kategorier WHERE navn = %s", (kategori_navn,)
                )
                row = cur.fetchone()
                if row:
                    kategori_id = row[0]

    conn.commit()
    log.info("  → %d ord lagret i '%s'", inserted, kategori_navn)
    return inserted


# ---------------------------------------------------------------------------
# Hovedprogram
# ---------------------------------------------------------------------------
def main() -> None:
    log.info("=== Wikidata-innhenting startet ===")

    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL mangler i .env")
        sys.exit(1)

    conn = get_db(database_url)
    sparql = SPARQLWrapper(SPARQL_ENDPOINT)
    sparql.addCustomHttpHeader("User-Agent", USER_AGENT)

    total = 0
    for i, query_def in enumerate(QUERIES):
        count = process_category(conn, sparql, query_def)
        total += count
        if i < len(QUERIES) - 1:
            log.info("Venter %ss ...", REQUEST_DELAY)
            time.sleep(REQUEST_DELAY)

    conn.close()
    log.info("=== Ferdig. Totalt %d egennavn lagret. ===", total)


if __name__ == "__main__":
    main()
