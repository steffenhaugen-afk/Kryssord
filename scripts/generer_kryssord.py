"""
Genererer norske kryssord i ulike størrelser og lagrer dem i databasen.

Algoritmen:
  1. Hent ord fra databasen filtrert på bokstavlengde
  2. Plasser første ord horisontalt midt på griden
  3. Bygg ut krysset ved å finne ord som deler bokstaver
  4. Lagre ferdig grid i kryssord-tabellen og marker som publisert

Bruk:
    python scripts/generer_kryssord.py --storrelse 9
    python scripts/generer_kryssord.py --storrelse 9 13 17

Krav:
    pip install -r scripts/requirements.txt
    DATABASE_URL satt i .env
"""
import argparse
import json
import logging
import os
import random
import sys
from dataclasses import dataclass, field
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
        logging.FileHandler(LOG_DIR / "generator.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Datastrukturer
# ---------------------------------------------------------------------------
ACROSS = "across"
DOWN   = "down"

VANSKELIGHETSGRAD = {9: "lett", 13: "middels", 17: "vanskelig"}


@dataclass
class PlassertOrd:
    tekst:    str
    rad:      int
    kol:      int
    retning:  str


@dataclass
class Kryssordgrid:
    storrelse: int
    celler:    list[list[str]] = field(default_factory=list)
    ord_liste: list[PlassertOrd] = field(default_factory=list)

    def __post_init__(self):
        self.celler = [["#"] * self.storrelse for _ in range(self.storrelse)]

    def kan_plassere(self, tekst: str, rad: int, kol: int, retning: str) -> bool:
        n = len(tekst)
        if retning == ACROSS:
            if kol < 0 or kol + n > self.storrelse:
                return False
            # Sjekk at det ikke er naboord rett før/etter
            if kol > 0 and self.celler[rad][kol - 1] != "#":
                return False
            if kol + n < self.storrelse and self.celler[rad][kol + n] != "#":
                return False
            for i, bokstav in enumerate(tekst):
                celle = self.celler[rad][kol + i]
                if celle != "#" and celle != bokstav:
                    return False
        else:  # DOWN
            if rad < 0 or rad + n > self.storrelse:
                return False
            if rad > 0 and self.celler[rad - 1][kol] != "#":
                return False
            if rad + n < self.storrelse and self.celler[rad + n][kol] != "#":
                return False
            for i, bokstav in enumerate(tekst):
                celle = self.celler[rad + i][kol]
                if celle != "#" and celle != bokstav:
                    return False
        return True

    def plasser(self, tekst: str, rad: int, kol: int, retning: str) -> None:
        for i, bokstav in enumerate(tekst):
            if retning == ACROSS:
                self.celler[rad][kol + i] = bokstav
            else:
                self.celler[rad + i][kol] = bokstav
        self.ord_liste.append(PlassertOrd(tekst, rad, kol, retning))

    def til_json(self) -> dict:
        return {
            "storrelse": self.storrelse,
            "celler":    self.celler,
        }

    def ledetrad_json(self) -> dict:
        across = {}
        down   = {}
        nummer = 1
        nummerert: dict[tuple, int] = {}

        for rad in range(self.storrelse):
            for kol in range(self.storrelse):
                if self.celler[rad][kol] == "#":
                    continue
                starter_across = (
                    kol == 0 or self.celler[rad][kol - 1] == "#"
                ) and kol + 1 < self.storrelse and self.celler[rad][kol + 1] != "#"
                starter_down = (
                    rad == 0 or self.celler[rad - 1][kol] == "#"
                ) and rad + 1 < self.storrelse and self.celler[rad + 1][kol] != "#"

                if starter_across or starter_down:
                    nummerert[(rad, kol)] = nummer
                    nummer += 1

        for pw in self.ord_liste:
            pos = (pw.rad, pw.kol)
            nr  = nummerert.get(pos, 0)
            entry = {"nr": nr, "tekst": pw.tekst, "ledetrad": f"Se opp ({len(pw.tekst)})"}
            if pw.retning == ACROSS:
                across[str(nr)] = entry
            else:
                down[str(nr)] = entry

        return {"across": across, "down": down}


# ---------------------------------------------------------------------------
# Orduthenting fra database
# ---------------------------------------------------------------------------
def hent_ord(conn, min_len: int, max_len: int, antall: int = 500) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tekst FROM ord
            WHERE bokstavlengde BETWEEN %s AND %s
              AND ordklasse IN ('substantiv', 'verb', 'adjektiv')
              AND tekst NOT LIKE '%%-%%'
            ORDER BY random()
            LIMIT %s
        """, (min_len, max_len, antall))
        return [row[0] for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Generering
# ---------------------------------------------------------------------------
def generer(storrelse: int, ord_liste: list[str], seed: int | None = None) -> Kryssordgrid | None:
    if seed is not None:
        random.seed(seed)

    grid = Kryssordgrid(storrelse)
    midt = storrelse // 2

    # Filtrer ord etter passende lengde for gridet
    min_len = max(3, storrelse // 3)
    max_len = storrelse - 2
    kandidater = sorted(
        [o for o in ord_liste if min_len <= len(o) <= max_len],
        key=lambda x: -len(x),
    )

    if not kandidater:
        return None

    # Plasser første ord horisontalt i midten
    forste = kandidater[0]
    start_kol = (storrelse - len(forste)) // 2
    grid.plasser(forste, midt, start_kol, ACROSS)

    plasserte_ord = {forste}
    forsok = 0
    maks_forsok = min(len(kandidater) * 2, 2000)

    while forsok < maks_forsok and len(grid.ord_liste) < storrelse:
        forsok += 1
        kandidat = random.choice(kandidater)
        if kandidat in plasserte_ord:
            continue

        # Finn krysningspunkter med allerede plasserte ord
        for pw in list(grid.ord_liste):
            plassert_retning = pw.retning
            ny_retning = DOWN if plassert_retning == ACROSS else ACROSS

            for i, bokstav_i in enumerate(pw.tekst):
                for j, bokstav_j in enumerate(kandidat):
                    if bokstav_i != bokstav_j:
                        continue

                    if ny_retning == DOWN:
                        rad = pw.rad - j
                        kol = pw.kol + i
                    else:
                        rad = pw.rad + i
                        kol = pw.kol - j

                    if grid.kan_plassere(kandidat, rad, kol, ny_retning):
                        grid.plasser(kandidat, rad, kol, ny_retning)
                        plasserte_ord.add(kandidat)
                        break
                else:
                    continue
                break

    min_ord = storrelse // 3
    if len(grid.ord_liste) < min_ord:
        log.warning(
            "Kun %d ord plassert (minimum %d) for %dx%d",
            len(grid.ord_liste), min_ord, storrelse, storrelse,
        )
        return None

    return grid


# ---------------------------------------------------------------------------
# Lagring
# ---------------------------------------------------------------------------
def lagre_kryssord(conn, grid: Kryssordgrid, storrelse: int) -> str:
    vanskelighetsgrad = VANSKELIGHETSGRAD.get(storrelse, "middels")
    tittel = f"Ukens kryssord {storrelse}×{storrelse}"

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO kryssord
              (tittel, vanskelighetsgrad, grid_storrelse, grid_json, ledetrad_json, publisert)
            VALUES (%s, %s, %s, %s, %s, true)
            RETURNING id
        """, (
            tittel,
            vanskelighetsgrad,
            storrelse,
            json.dumps(grid.til_json(), ensure_ascii=False),
            json.dumps(grid.ledetrad_json(), ensure_ascii=False),
        ))
        kryssord_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO kryssord_statistikk (kryssord_id)
            VALUES (%s)
            ON CONFLICT DO NOTHING
        """, (str(kryssord_id),))

    conn.commit()
    return str(kryssord_id)


# ---------------------------------------------------------------------------
# Hovedprogram
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Generer norske kryssord")
    parser.add_argument(
        "--storrelse", type=int, nargs="+", default=[9, 13, 17],
        help="Grid-størrelse(r), f.eks. --storrelse 9 13 17",
    )
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL mangler")
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    log.info("=== Kryssordgenerator startet ===")

    for storrelse in args.storrelse:
        log.info("Genererer %dx%d ...", storrelse, storrelse)
        ord_liste = hent_ord(conn, min_len=3, max_len=storrelse - 2)

        if len(ord_liste) < 20:
            log.error("For få ord i databasen for %dx%d (fant %d)", storrelse, storrelse, len(ord_liste))
            continue

        grid = generer(storrelse, ord_liste, seed=args.seed)
        if grid is None:
            log.error("Klarte ikke generere %dx%d kryssord", storrelse, storrelse)
            continue

        kryssord_id = lagre_kryssord(conn, grid, storrelse)
        log.info(
            "  Lagret %dx%d kryssord (id=%s) med %d ord",
            storrelse, storrelse, kryssord_id, len(grid.ord_liste),
        )

    conn.close()
    log.info("=== Ferdig ===")


if __name__ == "__main__":
    main()
