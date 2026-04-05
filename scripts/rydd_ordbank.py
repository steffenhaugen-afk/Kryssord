"""
Rydder ordbanken i databasen og beriker ord med nye flagg.

Regler
------
SLETT:
  - Ord som inneholder siffer (0-9)
  - Ord som starter eller slutter med bindestrek eller mellomrom
  - Ord der faktisk bokstavlengde (uten bindestrek/mellomrom) < 2
  - Ord der faktisk bokstavlengde > 15

BEHOLD og marker:
  - Egennavn med bindestrek  → har_bindestrek = true
  - Egennavn med mellomrom   → har_mellomrom  = true
  - Alle ord med bokstavlengde = 2 → kort_ord = true

LEGG TIL (hvis ikke finnes):
  - Kuraterte 2-bokstavsord med ordklasse og kort_ord = true

Bruk:
    python scripts/rydd_ordbank.py [--dry-run]
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kuraterte korte ord som skal legges til hvis de mangler
# ---------------------------------------------------------------------------
TALLORD = [
    ("en",  "substantiv"),
    ("to",  "substantiv"),
    ("ti",  "substantiv"),
    ("ni",  "substantiv"),
]

VANLIGE_KORTE = [
    ("ås",  "substantiv"),
    ("is",  "substantiv"),
    ("ly",  "substantiv"),
    ("by",  "substantiv"),
    ("fy",  "interjeksjon"),
    ("ny",  "adjektiv"),
    ("sy",  "verb"),
    ("få",  "verb"),
    ("gå",  "verb"),
    ("på",  "preposisjon"),
    ("så",  "konjunksjon"),
    ("dø",  "verb"),
    ("nå",  "verb"),
]

KURATERTE_KORTE_ORD = TALLORD + VANLIGE_KORTE


def _bokstavlengde(tekst: str) -> int:
    return len(tekst.replace("-", "").replace(" ", ""))


def rydd(conn, dry_run: bool) -> dict:
    stats: dict[str, int] = {
        "slettet_siffer":          0,
        "slettet_starts_slutter":  0,
        "slettet_for_kort":        0,
        "slettet_for_lang":        0,
        "markert_bindestrek":      0,
        "markert_mellomrom":       0,
        "markert_kort_ord":        0,
        "lagt_til_korte":          0,
    }

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

        # ------------------------------------------------------------------
        # 1. Egennavn med bindestrek → marker
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT id FROM ord
            WHERE tekst LIKE '%-%'
              AND ordklasse = 'egennavn'
              AND har_bindestrek = false
        """)
        bindestrek_ids = [r["id"] for r in cur.fetchall()]
        stats["markert_bindestrek"] = len(bindestrek_ids)
        log.info("Egennavn med bindestrek: %d", stats["markert_bindestrek"])

        if not dry_run and bindestrek_ids:
            cur.execute(
                "UPDATE ord SET har_bindestrek = true WHERE id = ANY(%s::uuid[])",
                (bindestrek_ids,),
            )

        # ------------------------------------------------------------------
        # 2. Egennavn med mellomrom → marker
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT id FROM ord
            WHERE tekst LIKE '% %'
              AND ordklasse = 'egennavn'
              AND har_mellomrom = false
        """)
        mellomrom_ids = [r["id"] for r in cur.fetchall()]
        stats["markert_mellomrom"] = len(mellomrom_ids)
        log.info("Egennavn med mellomrom: %d", stats["markert_mellomrom"])

        if not dry_run and mellomrom_ids:
            cur.execute(
                "UPDATE ord SET har_mellomrom = true WHERE id = ANY(%s::uuid[])",
                (mellomrom_ids,),
            )

        # ------------------------------------------------------------------
        # 3. Slett ord som starter eller slutter med bindestrek/mellomrom
        #    (dette inkluderer ikke-egennavn med ledende bindestrek)
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT id, tekst FROM ord
            WHERE tekst ~ '^[- ]|[- ]$'
        """)
        starts_slutter = cur.fetchall()
        starts_slutter_ids = [r["id"] for r in starts_slutter]
        stats["slettet_starts_slutter"] = len(starts_slutter_ids)
        log.info("Ord som starter/slutter med separator: %d", stats["slettet_starts_slutter"])

        if not dry_run and starts_slutter_ids:
            cur.execute("DELETE FROM ord WHERE id = ANY(%s::uuid[])", (starts_slutter_ids,))

        # ------------------------------------------------------------------
        # 4. Slett ord med siffer
        # ------------------------------------------------------------------
        cur.execute("SELECT id FROM ord WHERE tekst ~ '[0-9]'")
        siffer_ids = [r["id"] for r in cur.fetchall()]
        stats["slettet_siffer"] = len(siffer_ids)
        log.info("Ord med siffer: %d", stats["slettet_siffer"])

        if not dry_run and siffer_ids:
            cur.execute("DELETE FROM ord WHERE id = ANY(%s::uuid[])", (siffer_ids,))

        # ------------------------------------------------------------------
        # 5. Slett ord med for få/mange faktiske bokstaver
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT id FROM ord
            WHERE length(regexp_replace(tekst, '[- ]', '', 'g')) < 2
        """)
        for_korte_ids = [r["id"] for r in cur.fetchall()]
        stats["slettet_for_kort"] = len(for_korte_ids)
        log.info("Ord under 2 bokstaver (ekskl. separator): %d", stats["slettet_for_kort"])

        if not dry_run and for_korte_ids:
            cur.execute("DELETE FROM ord WHERE id = ANY(%s::uuid[])", (for_korte_ids,))

        cur.execute("""
            SELECT id FROM ord
            WHERE length(regexp_replace(tekst, '[- ]', '', 'g')) > 15
        """)
        for_lange_ids = [r["id"] for r in cur.fetchall()]
        stats["slettet_for_lang"] = len(for_lange_ids)
        log.info("Ord over 15 bokstaver (ekskl. separator): %d", stats["slettet_for_lang"])

        if not dry_run and for_lange_ids:
            cur.execute("DELETE FROM ord WHERE id = ANY(%s::uuid[])", (for_lange_ids,))

        # ------------------------------------------------------------------
        # 6. Sett kort_ord = true for alle gjenværende 2-bokstavsord
        # ------------------------------------------------------------------
        cur.execute("""
            UPDATE ord SET kort_ord = true
            WHERE length(regexp_replace(tekst, '[- ]', '', 'g')) = 2
              AND kort_ord = false
        """)
        stats["markert_kort_ord"] = cur.rowcount if not dry_run else 0

        if dry_run:
            cur.execute("""
                SELECT COUNT(*) FROM ord
                WHERE length(regexp_replace(tekst, '[- ]', '', 'g')) = 2
            """)
            stats["markert_kort_ord"] = cur.fetchone()[0]
        log.info("Kort_ord markert: %d", stats["markert_kort_ord"])

        # ------------------------------------------------------------------
        # 7. Legg til kuraterte korte ord
        # ------------------------------------------------------------------
        for tekst, ordklasse in KURATERTE_KORTE_ORD:
            cur.execute("SELECT id FROM ord WHERE tekst = %s", (tekst,))
            existing = cur.fetchone()
            if existing:
                # Oppdater ordklasse og kort_ord hvis nødvendig
                if not dry_run:
                    cur.execute(
                        "UPDATE ord SET kort_ord = true, ordklasse = %s WHERE tekst = %s",
                        (ordklasse, tekst),
                    )
            else:
                log.info("  Legger til: '%s' (%s)", tekst, ordklasse)
                stats["lagt_til_korte"] += 1
                if not dry_run:
                    cur.execute(
                        """
                        INSERT INTO ord (tekst, ordklasse, kort_ord)
                        VALUES (%s, %s, true)
                        ON CONFLICT (tekst) DO UPDATE
                          SET kort_ord = true, ordklasse = EXCLUDED.ordklasse
                        """,
                        (tekst, ordklasse),
                    )

    if not dry_run:
        conn.commit()
    else:
        conn.rollback()

    return stats


def rapport(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                length(regexp_replace(tekst, '[- ]', '', 'g')) AS bokstaver,
                COUNT(*) AS antall
            FROM ord
            GROUP BY 1
            ORDER BY 1
        """)
        fordeling = cur.fetchall()

        cur.execute("SELECT COUNT(*) FROM ord")
        totalt = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM ord WHERE har_bindestrek = true")
        n_bindestrek = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM ord WHERE har_mellomrom = true")
        n_mellomrom = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM ord WHERE kort_ord = true")
        n_kort = cur.fetchone()[0]

        cur.execute("""
            SELECT ordklasse, COUNT(*) FROM ord GROUP BY ordklasse ORDER BY COUNT(*) DESC
        """)
        per_klasse = cur.fetchall()

    print("\n=== RAPPORT ===")
    print(f"\nTotalt ord i databasen: {totalt}")
    print(f"  Har bindestrek:       {n_bindestrek}")
    print(f"  Har mellomrom:        {n_mellomrom}")
    print(f"  Korte ord (2 boks.):  {n_kort}")

    print("\nFordeling per ordklasse:")
    for klasse, antall in per_klasse:
        print(f"  {(klasse or 'ukjent'):<20} {antall:>6}")

    print("\nFordeling per bokstavlengde:")
    for bokstaver, antall in fordeling:
        bar = "█" * min(40, antall // 200)
        print(f"  {bokstaver:>2} bokstaver:  {antall:>6}  {bar}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rydd ordbanken")
    parser.add_argument("--dry-run", action="store_true", help="Vis endringer uten å skrive til DB")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        log.error("DATABASE_URL mangler")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    try:
        if args.dry_run:
            log.info("=== TØRRKJØRING — ingen endringer skrives ===")
        else:
            log.info("=== Starter opprydding av ordbanken ===")

        stats = rydd(conn, dry_run=args.dry_run)

        print("\n=== OPPSUMMERING AV ENDRINGER ===")
        print(f"  Slettet (starter/slutter med separator): {stats['slettet_starts_slutter']}")
        print(f"  Slettet (inneholder siffer):             {stats['slettet_siffer']}")
        print(f"  Slettet (for kort, < 2 bokstaver):       {stats['slettet_for_kort']}")
        print(f"  Slettet (for lang, > 15 bokstaver):      {stats['slettet_for_lang']}")
        totalt_slettet = (
            stats["slettet_starts_slutter"]
            + stats["slettet_siffer"]
            + stats["slettet_for_kort"]
            + stats["slettet_for_lang"]
        )
        print(f"  Totalt slettet:                          {totalt_slettet}")
        print()
        print(f"  Markert har_bindestrek:                  {stats['markert_bindestrek']}")
        print(f"  Markert har_mellomrom:                   {stats['markert_mellomrom']}")
        print(f"  Markert kort_ord:                        {stats['markert_kort_ord']}")
        print(f"  Lagt til korte ord:                      {stats['lagt_til_korte']}")

        if not args.dry_run:
            rapport(conn)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
