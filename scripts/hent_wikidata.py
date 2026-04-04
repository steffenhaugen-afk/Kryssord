"""
Henter norske egennavn fra Wikidata SPARQL og lagrer i PostgreSQL.

Kategorier:
  - Norske politikere
  - Norske kommuner og byer
  - Norske fjell
  - Norske kunstnere og musikere
  - Europeiske land (norske navn)

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
ROOT     = Path(__file__).parent.parent
LOG_DIR  = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT      = "KryssordNorge/1.0 (hobby-prosjekt; python SPARQLWrapper)"

MIN_LEN = 2
MAX_LEN = 25   # Egennavn kan være lengre enn vanlige ord
REQUEST_DELAY = 2.0   # Wikidata ber om minst 1s mellom kall

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
# ---------------------------------------------------------------------------
# Felles prefikser og label-service brukes i alle spørringer.
# Resultater returneres som ?navn (norsk bokmålsnavn).
# Ekstra felt (parti, høyde osv.) hentes der tilgjengelig.

QUERIES: list[dict] = [
    {
        "kategori":    "Norske politikere",
        "beskrivelse": "Norske politikere hentet fra Wikidata",
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P27  wd:Q20 ;       # statsborgerskap: Norge
        wdt:P106 wd:Q82955 .    # yrke: politiker
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
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  {
    ?item wdt:P31 wd:Q755707 .    # norsk kommune
  } UNION {
    ?item wdt:P31 wd:Q1115575 .   # norsk by
  } UNION {
    ?item wdt:P17 wd:Q20 ;
          wdt:P31 wd:Q515 .       # by i Norge
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
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P17 wd:Q20 ;          # land: Norge
        wdt:P31 wd:Q8502 .        # instanstype: fjell
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 3000
        """,
    },
    {
        "kategori":    "Norske kunstnere og musikere",
        "beskrivelse": "Norske kunstnere og musikere hentet fra Wikidata",
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P27 wd:Q20 .           # statsborgerskap: Norge
  {
    ?item wdt:P106 wd:Q483501 .    # yrke: kunstner
  } UNION {
    ?item wdt:P106 wd:Q639669 .    # yrke: musiker
  } UNION {
    ?item wdt:P106 wd:Q177220 .    # yrke: sanger
  } UNION {
    ?item wdt:P106 wd:Q1028181 .   # yrke: maler
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
        "sparql": """
SELECT DISTINCT ?navn WHERE {
  ?item wdt:P30 wd:Q46 ;           # kontinent: Europa
        wdt:P31 wd:Q6256 .         # instanstype: land
  ?item rdfs:label ?navn .
  FILTER(LANG(?navn) = "nb")
  FILTER(STRLEN(?navn) >= 2)
}
LIMIT 200
        """,
    },
]

# ---------------------------------------------------------------------------
# Database-hjelp
# ---------------------------------------------------------------------------
def get_db(database_url: str):
    return psycopg2.connect(database_url)


def upsert_ord(cur, tekst: str) -> str:
    """Setter inn ord og returnerer UUID-en (eksisterende eller ny)."""
    cur.execute("""
        INSERT INTO ord (tekst, ordklasse)
        VALUES (%s, 'egennavn')
        ON CONFLICT (tekst) DO UPDATE SET ordklasse = EXCLUDED.ordklasse
        RETURNING id
    """, (tekst,))
    return cur.fetchone()[0]


def upsert_kategori(cur, navn: str, beskrivelse: str) -> str:
    """Setter inn kategori og returnerer UUID-en."""
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
# SPARQL-kall
# ---------------------------------------------------------------------------
def run_sparql(sparql: SPARQLWrapper, query: str) -> list[str]:
    """
    Kjører SPARQL-spørring og returnerer liste av norske navn.
    Filtrerer ut flerleddsnavn for kryssordbruk (beholder enkeltord).
    Beholder navn med bindestrek (f.eks. Aust-Agder).
    """
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)

    try:
        results = sparql.query().convert()
    except Exception as exc:
        log.error("SPARQL-feil: %s", exc)
        return []

    names = []
    for row in results.get("results", {}).get("bindings", []):
        navn = row.get("navn", {}).get("value", "").strip()
        if not navn:
            continue

        # Kun enkeltord eller ord med bindestrek (kryssordvennlig)
        if " " in navn:
            # Behold enkeltleddet hvis det er informativt nok
            # F.eks. "Jan Egeland" → hopp over; "Aust-Agder" → behold
            continue

        tekst = navn.lower()
        if not (MIN_LEN <= len(tekst) <= MAX_LEN):
            continue
        if not all(c.isalpha() or c in "-'" for c in tekst):
            continue

        names.append(tekst)

    return names


# ---------------------------------------------------------------------------
# Prosessering per kategori
# ---------------------------------------------------------------------------
def process_category(conn, sparql: SPARQLWrapper, query_def: dict) -> int:
    kategori_navn = query_def["kategori"]
    log.info("--- Henter: %s ---", kategori_navn)

    names = run_sparql(sparql, query_def["sparql"])
    log.info("  Mottok %d enkeltord fra Wikidata", len(names))

    if not names:
        return 0

    inserted = 0
    with conn.cursor() as cur:
        kategori_id = upsert_kategori(cur, kategori_navn, query_def["beskrivelse"])

        for tekst in names:
            try:
                ord_id = upsert_ord(cur, tekst)
                link_ord_kategori(cur, ord_id, kategori_id)
                inserted += 1
            except Exception as exc:
                log.warning("Feil for '%s': %s", tekst, exc)
                conn.rollback()
                # Hent kategori-id på nytt etter rollback
                cur.execute("SELECT id FROM kategorier WHERE navn = %s", (kategori_navn,))
                row = cur.fetchone()
                if row:
                    kategori_id = row[0]
                continue

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
            log.info("Venter %ss før neste spørring ...", REQUEST_DELAY)
            time.sleep(REQUEST_DELAY)

    conn.close()
    log.info("=== Ferdig. Totalt %d egennavn lagret. ===", total)


if __name__ == "__main__":
    main()
