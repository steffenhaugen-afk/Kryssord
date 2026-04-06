"""
Henter norske synonym-par fra NorWordNet via NLTK OMW (Open Multilingual Wordnet).

Strategi:
  For hvert synset i WordNet med norsk (nob/nno) lemma, finn alle norske
  lemmaer i samme synset og lagre krysspar som synonymer i DB.

Bruk:
    python scripts/hent_norwordnet.py [--dry-run]

Krav:
    pip install nltk
    python -c "import nltk; nltk.download('omw-1.4'); nltk.download('wordnet')"
    DATABASE_URL satt i .env
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT    = Path(__file__).parent.parent
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "norwordnet.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NorWordNet-henting
# ---------------------------------------------------------------------------
def hent_norwordnet_par() -> list[tuple[str, str]]:
    """
    Henter alle norske synonym-par fra NLTK OMW.
    Returnerer liste av (ord1, ord2) der begge er norske lemmaer i samme synset.
    """
    import nltk
    from nltk.corpus import wordnet as wn

    # Last ned hvis nødvendig
    try:
        wn.synsets("hus", lang="nob")
    except LookupError:
        log.info("Laster ned NLTK WordNet/OMW …")
        nltk.download("omw-1.4", quiet=True)
        nltk.download("wordnet",  quiet=True)

    par: set[tuple[str, str]] = set()
    spraak = ["nob", "nno"]

    for lang in spraak:
        for synset in wn.all_synsets():
            lemmaer = [
                l.name().replace("_", " ").lower()
                for l in synset.lemmas(lang=lang)
            ]
            # Fjern duplikater innad i synset
            lemmaer = list(dict.fromkeys(lemmaer))
            for i, a in enumerate(lemmaer):
                for b in lemmaer[i + 1:]:
                    if a != b:
                        par.add((min(a, b), max(a, b)))

    return list(par)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def lagre_par(conn, par: list[tuple[str, str]], dry_run: bool) -> dict:
    """Lagrer synonym-par i synonymer-tabellen med kilde='norwordnet'."""
    stats = {"funnet_par": 0, "nye_synonymer": 0, "mangler_i_db": 0}

    # Hent alle relevante ord-IDer i én query
    alle_ord = list({ord_ for paret in par for ord_ in paret})
    placeholders = ",".join(["%s"] * len(alle_ord))

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id, tekst FROM ord WHERE tekst IN ({placeholders})",
            alle_ord,
        )
        ord_til_id = {row[1]: row[0] for row in cur.fetchall()}

    log.info("Ord fra DB: %d / %d unike lemmaer", len(ord_til_id), len(alle_ord))

    if dry_run:
        for ord1, ord2 in par:
            if ord1 in ord_til_id and ord2 in ord_til_id:
                stats["funnet_par"] += 1
            else:
                stats["mangler_i_db"] += 1
        return stats

    batch = []
    for ord1, ord2 in par:
        if ord1 not in ord_til_id or ord2 not in ord_til_id:
            stats["mangler_i_db"] += 1
            continue
        stats["funnet_par"] += 1
        id1, id2 = ord_til_id[ord1], ord_til_id[ord2]
        batch.append((id1, id2, "synonym", "norwordnet"))
        batch.append((id2, id1, "synonym", "norwordnet"))

    with conn.cursor() as cur:
        from psycopg2.extras import execute_values
        execute_values(
            cur,
            """
            INSERT INTO synonymer (ord_id, synonym_id, relasjon_type, kilde)
            VALUES %s
            ON CONFLICT (ord_id, synonym_id) DO NOTHING
            """,
            batch,
        )
        stats["nye_synonymer"] = cur.rowcount
    conn.commit()

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Hent NorWordNet-synonymer via NLTK OMW")
    parser.add_argument("--dry-run", action="store_true", help="Vis resultater uten å lagre")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        log.error("DATABASE_URL mangler"); sys.exit(1)

    log.info("=== Henter NorWordNet via NLTK OMW ===")
    par = hent_norwordnet_par()
    log.info("Fant %d unike synonym-par totalt (nob+nno)", len(par))

    conn = psycopg2.connect(db_url)
    stats = lagre_par(conn, par, args.dry_run)
    conn.close()

    print("\n=== RAPPORT ===")
    print(f"  Synonym-par fra NorWordNet:       {len(par)}")
    print(f"  Par der begge ord finnes i DB:    {stats['funnet_par']}")
    print(f"  Nye synonymer lagret (2 retninger): {stats['nye_synonymer']}")
    print(f"  Par der et ord mangler i DB:      {stats['mangler_i_db']}")
    if args.dry_run:
        print("  (DRY-RUN – ingenting ble lagret)")


if __name__ == "__main__":
    main()
