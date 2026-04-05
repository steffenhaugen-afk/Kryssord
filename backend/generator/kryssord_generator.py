"""
KryssordGenerator – backtracking-basert kryssordgenerator for norsk.

Arkitektur
----------
1. WordIndex    – rask kandidat-oppslag via (lengde, posisjon, bokstav)
2. Grid         – rutenett med validering og slot-oppdaging
3. KryssordGenerator.generer() – Most-Constrained-Variable (MCV) backtracking

MCV-heuristikken velger alltid sloten med færrest gyldige kandidatord
først.  Dette reduserer søketreet dramatisk sammenlignet med tilfeldig
rekkefølge.

Vanskelighetsgrader
-------------------
  lett      – 3-6 bokstaver, prioriterer vanlige ordklasser
  middels   – 4-9 bokstaver, blander ordklasser
  vanskelig – 5-15 bokstaver, inkluderer sjeldne ord og egennavn

Returnerer
----------
GridResultat med:
  grid_json      – {"storrelse": N, "celler": [[...], ...]}
  ledetrad_json  – {"across": {nr: {tekst, rad, kol}}, "down": {...}}
  ord_plassering – liste av OrdPlassering
"""
from __future__ import annotations

import json
import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterator

import psycopg2

log = logging.getLogger(__name__)

ACROSS = "across"
DOWN   = "down"

# ---------------------------------------------------------------------------
# Vanskelighetsgrad-konfigurasjon
# ---------------------------------------------------------------------------
VANSKELIGHET: dict[str, dict] = {
    "lett": {
        "min_len":       3,
        "max_len":       6,
        "pool_size":     400,
        "ordklasser":    ("substantiv", "verb", "adjektiv", "egennavn"),
        "min_ord":       5,
        "maks_korte":    2,   # maks antall 2-bokstavsord per brett
    },
    "middels": {
        "min_len":       4,
        "max_len":       9,
        "pool_size":     600,
        "ordklasser":    ("substantiv", "verb", "adjektiv", "egennavn"),
        "min_ord":       7,
        "maks_korte":    2,
    },
    "vanskelig": {
        "min_len":       5,
        "max_len":       15,
        "pool_size":     800,
        "ordklasser":    ("substantiv", "verb", "adjektiv", "egennavn"),
        "min_ord":       9,
        "maks_korte":    3,
    },
}

GRID_MAKS_ORDLENGDE = {9: 7, 13: 11, 17: 15}


# ---------------------------------------------------------------------------
# Dataklasser
# ---------------------------------------------------------------------------
@dataclass
class OrdPlassering:
    tekst:     str
    retning:   str
    rad:       int
    kol:       int
    nummer:    int = 0


@dataclass
class GridResultat:
    grid_json:      dict
    ledetrad_json:  dict
    ord_plassering: list[OrdPlassering]

    @property
    def antall_ord(self) -> int:
        return len(self.ord_plassering)


@dataclass
class Slot:
    rad:     int
    kol:     int
    retning: str
    lengde:  int

    def celler(self) -> list[tuple[int, int]]:
        if self.retning == ACROSS:
            return [(self.rad, self.kol + i) for i in range(self.lengde)]
        return [(self.rad + i, self.kol) for i in range(self.lengde)]

    def __hash__(self):
        return hash((self.rad, self.kol, self.retning, self.lengde))


# ---------------------------------------------------------------------------
# WordIndex – rask kandidat-oppslag
# ---------------------------------------------------------------------------
class WordIndex:
    def __init__(self, ord_liste: list[str]) -> None:
        # (lengde, posisjon, bokstav) → frozenset av ord
        self._idx: dict[tuple[int, int, str], set[str]] = defaultdict(set)
        self._by_len: dict[int, list[str]] = defaultdict(list)

        for ord_ in ord_liste:
            self._by_len[len(ord_)].append(ord_)
            for pos, bokstav in enumerate(ord_):
                self._idx[(len(ord_), pos, bokstav)].add(ord_)

    def kandidater(self, slot: Slot, grid: list[list[str]]) -> list[str]:
        """Returnerer alle ord som passer i sloten gitt eksisterende bokstaver."""
        kryss = [
            (i, grid[r][c])
            for i, (r, c) in enumerate(slot.celler())
            if grid[r][c] != "#"
        ]

        resultat: set[str] | None = None
        for pos, bokstav in kryss:
            treff = self._idx.get((slot.lengde, pos, bokstav), set())
            resultat = treff if resultat is None else resultat & treff
            if not resultat:
                return []

        if resultat is None:
            return list(self._by_len.get(slot.lengde, []))
        return list(resultat)

    def har_lengde(self, n: int) -> bool:
        return bool(self._by_len.get(n))


# ---------------------------------------------------------------------------
# Grid – rutenett med validering
# ---------------------------------------------------------------------------
class Grid:
    def __init__(self, storrelse: int) -> None:
        self.n = storrelse
        self.celler: list[list[str]] = [["#"] * storrelse for _ in range(storrelse)]

    # ---- Plassering og fjerning ----

    def plasser(self, ord_: str, rad: int, kol: int, retning: str) -> None:
        for i, bokstav in enumerate(ord_):
            r, c = (rad, kol + i) if retning == ACROSS else (rad + i, kol)
            self.celler[r][c] = bokstav

    def fjern(self, ord_: str, rad: int, kol: int, retning: str) -> None:
        """Fjerner et ord, men beholder bokstaver som tilhører kryss med andre ord."""
        for i in range(len(ord_)):
            r, c = (rad, kol + i) if retning == ACROSS else (rad + i, kol)
            # Sjekk om bokstaven brukes av et ord i vinkelrett retning
            if not self._har_annet_ord(r, c, retning):
                self.celler[r][c] = "#"

    def _har_annet_ord(self, rad: int, kol: int, retning: str) -> bool:
        """Returnerer True hvis (rad, kol) inngår i et ord vinkelrett på retning."""
        if retning == ACROSS:
            # Sjekk DOWN-retning: er det bokstaver over eller under?
            return (
                (rad > 0 and self.celler[rad - 1][kol] != "#")
                or (rad < self.n - 1 and self.celler[rad + 1][kol] != "#")
            )
        else:
            return (
                (kol > 0 and self.celler[rad][kol - 1] != "#")
                or (kol < self.n - 1 and self.celler[rad][kol + 1] != "#")
            )

    # ---- Validering ----

    def kan_plassere(self, ord_: str, rad: int, kol: int, retning: str) -> bool:
        n = len(ord_)

        if retning == ACROSS:
            if kol < 0 or kol + n > self.n or rad < 0 or rad >= self.n:
                return False
            # Ingen løpende nabo før/etter
            if kol > 0 and self.celler[rad][kol - 1] != "#":
                return False
            if kol + n < self.n and self.celler[rad][kol + n] != "#":
                return False
            for i, bokstav in enumerate(ord_):
                c = kol + i
                celle = self.celler[rad][c]
                if celle != "#" and celle != bokstav:
                    return False
                # Ingen parallell nabo (med mindre vi krysser)
                if celle == "#":
                    if rad > 0 and self.celler[rad - 1][c] != "#":
                        return False
                    if rad < self.n - 1 and self.celler[rad + 1][c] != "#":
                        return False
        else:
            if rad < 0 or rad + n > self.n or kol < 0 or kol >= self.n:
                return False
            if rad > 0 and self.celler[rad - 1][kol] != "#":
                return False
            if rad + n < self.n and self.celler[rad + n][kol] != "#":
                return False
            for i, bokstav in enumerate(ord_):
                r = rad + i
                celle = self.celler[r][kol]
                if celle != "#" and celle != bokstav:
                    return False
                if celle == "#":
                    if kol > 0 and self.celler[r][kol - 1] != "#":
                        return False
                    if kol < self.n - 1 and self.celler[r][kol + 1] != "#":
                        return False

        # Krev minst ett kryss (unntatt første ord)
        har_kryss = any(
            self.celler[r][c] != "#"
            for r, c in (
                [(rad, kol + i) for i in range(n)]
                if retning == ACROSS
                else [(rad + i, kol) for i in range(n)]
            )
        )
        return har_kryss

    # ---- Slot-oppdaging ----

    def finn_slots(self, brukte_ord: set[str], min_len: int = 3, max_len: int = 15) -> list[Slot]:
        """
        Finner alle posisjoner der et nytt ord kan starte.
        En slot må ha minst én eksisterende bokstav (kryss) og
        riktig avstand til naboer.
        """
        slots: list[Slot] = []
        for retning in (ACROSS, DOWN):
            for rad in range(self.n):
                for kol in range(self.n):
                    for lengde in range(min_len, min(max_len, self.n) + 1):
                        slot = Slot(rad, kol, retning, lengde)
                        celler = slot.celler()
                        if any(r >= self.n or c >= self.n for r, c in celler):
                            break  # lengde er for stor, øk rad/kol
                        if self._slot_gyldig(slot, brukte_ord):
                            slots.append(slot)
        return slots

    def _slot_gyldig(self, slot: Slot, brukte_ord: set[str]) -> bool:
        n = slot.lengde
        rad, kol, retning = slot.rad, slot.kol, slot.retning

        if retning == ACROSS:
            if kol + n > self.n:
                return False
            if kol > 0 and self.celler[rad][kol - 1] != "#":
                return False
            if kol + n < self.n and self.celler[rad][kol + n] != "#":
                return False
        else:
            if rad + n > self.n:
                return False
            if rad > 0 and self.celler[rad - 1][kol] != "#":
                return False
            if rad + n < self.n and self.celler[rad + n][kol] != "#":
                return False

        har_kryss = False
        for r, c in slot.celler():
            celle = self.celler[r][c]
            if celle != "#":
                har_kryss = True
            elif retning == ACROSS:
                if (r > 0 and self.celler[r - 1][c] != "#") or \
                   (r < self.n - 1 and self.celler[r + 1][c] != "#"):
                    return False
            else:
                if (c > 0 and self.celler[r][c - 1] != "#") or \
                   (c < self.n - 1 and self.celler[r][c + 1] != "#"):
                    return False

        return har_kryss

    # ---- Ledetråd-nummerering ----

    def nummerer_celler(self) -> dict[tuple[int, int], int]:
        nummer = 1
        nummerert: dict[tuple[int, int], int] = {}
        for rad in range(self.n):
            for kol in range(self.n):
                if self.celler[rad][kol] == "#":
                    continue
                starter = (
                    (kol == 0 or self.celler[rad][kol - 1] == "#")
                    and kol + 1 < self.n
                    and self.celler[rad][kol + 1] != "#"
                ) or (
                    (rad == 0 or self.celler[rad - 1][kol] == "#")
                    and rad + 1 < self.n
                    and self.celler[rad + 1][kol] != "#"
                )
                if starter:
                    nummerert[(rad, kol)] = nummer
                    nummer += 1
        return nummerert

    def til_dict(self) -> dict:
        return {"storrelse": self.n, "celler": [rad[:] for rad in self.celler]}


# ---------------------------------------------------------------------------
# KryssordGenerator
# ---------------------------------------------------------------------------
class KryssordGenerator:
    def __init__(
        self,
        ord_liste:  list[str],
        storrelse:  int         = 13,
        vanskelighetsgrad: str  = "middels",
        maks_tid:   float       = 10.0,
        seed:       int | None  = None,
    ) -> None:
        if storrelse not in (9, 13, 17):
            raise ValueError(f"Ugyldig grid-størrelse: {storrelse}. Velg 9, 13 eller 17.")
        if vanskelighetsgrad not in VANSKELIGHET:
            raise ValueError(f"Ugyldig vanskelighetsgrad: {vanskelighetsgrad}")

        self.storrelse         = storrelse
        self.vanskelighetsgrad = vanskelighetsgrad
        self.maks_tid          = maks_tid
        self.cfg               = VANSKELIGHET[vanskelighetsgrad]
        self.maks_ordlen       = min(self.cfg["max_len"], GRID_MAKS_ORDLENGDE[storrelse])
        self.min_ord           = self.cfg["min_ord"]

        if seed is not None:
            random.seed(seed)

        maks_korte = self.cfg.get("maks_korte", 2)

        # Skill korte ord (2 bokstaver) fra vanlige
        korte   = [o for o in ord_liste if len(o) == 2 and o.isalpha()]
        vanlige = [
            o for o in ord_liste
            if self.cfg["min_len"] <= len(o) <= self.maks_ordlen
            and len(o) > 2
            and o.isalpha()
        ]

        random.shuffle(vanlige)
        random.shuffle(korte)

        # Begrens korte ord og kombiner
        valgte_korte = korte[:maks_korte]
        filtrert = vanlige[: self.cfg["pool_size"]] + valgte_korte

        self._ord_liste = filtrert
        self._index     = WordIndex(self._ord_liste)
        self._ord_sett  = set(self._ord_liste)

    # ---- Offentlig API ----

    def generer(self) -> GridResultat | None:
        """
        Returnerer et GridResultat eller None hvis ingen løsning finnes
        innen maks_tid sekunder.
        """
        start = time.monotonic()

        grid       = Grid(self.storrelse)
        plasserte: list[OrdPlassering] = []
        brukte_ord: set[str] = set()

        # Plasser første ord horisontalt i midten
        midt = self.storrelse // 2
        kandidater = sorted(
            [o for o in self._ord_liste if self.cfg["min_len"] + 2 <= len(o) <= self.maks_ordlen],
            key=lambda x: -len(x),
        )
        if not kandidater:
            log.warning("Ingen gyldige startord funnet")
            return None

        forste = kandidater[0]
        start_kol = (self.storrelse - len(forste)) // 2
        grid.plasser(forste, midt, start_kol, ACROSS)
        plasserte.append(OrdPlassering(forste, ACROSS, midt, start_kol))
        brukte_ord.add(forste)

        # Backtracking
        resultat = self._backtrack(grid, plasserte, brukte_ord, start)
        if resultat is None:
            return None

        return self._bygg_resultat(grid, plasserte)

    # ---- Internals ----

    def _backtrack(
        self,
        grid:       Grid,
        plasserte:  list[OrdPlassering],
        brukte_ord: set[str],
        start_tid:  float,
        dybde:      int = 0,
    ) -> bool | None:
        if len(plasserte) >= self.min_ord:
            return True

        if time.monotonic() - start_tid > self.maks_tid:
            # Returner det beste vi har funnet hvis vi har nok ord
            return len(plasserte) >= max(3, self.min_ord // 2) or None

        slots = grid.finn_slots(brukte_ord, self.cfg["min_len"], self.maks_ordlen)
        if not slots:
            return len(plasserte) >= max(3, self.min_ord // 2) or None

        # MCV: sorter etter færrest kandidater (mest begrenset slot først)
        slots_med_kandidater = []
        for slot in slots:
            kands = self._index.kandidater(slot, grid.celler)
            kands = [k for k in kands if k not in brukte_ord]
            if kands:
                slots_med_kandidater.append((slot, kands))

        if not slots_med_kandidater:
            return len(plasserte) >= max(3, self.min_ord // 2) or None

        slots_med_kandidater.sort(key=lambda x: len(x[1]))

        for slot, kands in slots_med_kandidater[:6]:   # prøv maks 6 slots per nivå
            random.shuffle(kands)
            for ord_ in kands[:12]:                    # prøv maks 12 ord per slot
                if time.monotonic() - start_tid > self.maks_tid:
                    return len(plasserte) >= max(3, self.min_ord // 2) or None

                if not grid.kan_plassere(ord_, slot.rad, slot.kol, slot.retning):
                    continue

                grid.plasser(ord_, slot.rad, slot.kol, slot.retning)
                plasserte.append(OrdPlassering(ord_, slot.retning, slot.rad, slot.kol))
                brukte_ord.add(ord_)

                resultat = self._backtrack(grid, plasserte, brukte_ord, start_tid, dybde + 1)
                if resultat:
                    return True

                # Angre
                grid.fjern(ord_, slot.rad, slot.kol, slot.retning)
                plasserte.pop()
                brukte_ord.discard(ord_)

        return len(plasserte) >= max(3, self.min_ord // 2) or None

    def _bygg_resultat(self, grid: Grid, plasserte: list[OrdPlassering]) -> GridResultat:
        nummerert = grid.nummerer_celler()

        across: dict[str, dict] = {}
        down:   dict[str, dict] = {}

        for pw in plasserte:
            pos = (pw.rad, pw.kol)
            nr  = nummerert.get(pos, 0)
            pw.nummer = nr
            entry = {
                "nr":       nr,
                "tekst":    pw.tekst,
                "rad":      pw.rad,
                "kol":      pw.kol,
                "lengde":   len(pw.tekst),
                "ledetrad": f"({len(pw.tekst)} bokstaver)",
            }
            if pw.retning == ACROSS:
                across[str(nr)] = entry
            else:
                down[str(nr)] = entry

        return GridResultat(
            grid_json=grid.til_dict(),
            ledetrad_json={"across": across, "down": down},
            ord_plassering=plasserte,
        )


# ---------------------------------------------------------------------------
# Databasehjelp
# ---------------------------------------------------------------------------
def hent_ord_fra_db(
    database_url: str,
    vanskelighetsgrad: str = "middels",
    storrelse: int = 13,
) -> list[str]:
    """
    Henter ord fra databasen filtrert på vanskelighetsgrad og gridstørrelse.

    - Ekskluderer sammensatte ord (har_bindestrek / har_mellomrom).
    - Inkluderer maksimalt `maks_korte` 2-bokstavsord per brett.
    """
    cfg          = VANSKELIGHET[vanskelighetsgrad]
    maks_len     = min(cfg["max_len"], GRID_MAKS_ORDLENGDE[storrelse])
    maks_korte   = cfg.get("maks_korte", 2)
    ordklasser   = cfg["ordklasser"]
    placeholders = ",".join(["%s"] * len(ordklasser))

    # Vanlige ord (3+ bokstaver, ingen sammensatte)
    sql_vanlg = f"""
        SELECT tekst FROM ord
        WHERE bokstavlengde BETWEEN %s AND %s
          AND ordklasse IN ({placeholders})
          AND har_bindestrek = false
          AND har_mellomrom  = false
          AND tekst ~ '^[a-zæøå]+$'
        ORDER BY random()
        LIMIT %s
    """

    # Korte ord (2 bokstaver) – begrenset antall per brett
    sql_korte = """
        SELECT tekst FROM ord
        WHERE kort_ord = true
          AND har_bindestrek = false
          AND har_mellomrom  = false
          AND tekst ~ '^[a-zæøå]+$'
        ORDER BY random()
        LIMIT %s
    """

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            min_len = max(cfg["min_len"], 3)   # aldri under 3 for vanlige ord
            cur.execute(sql_vanlg, (min_len, maks_len, *ordklasser, cfg["pool_size"] * 2))
            vanlige = [row[0] for row in cur.fetchall()]

            korte: list[str] = []
            if maks_korte > 0:
                cur.execute(sql_korte, (maks_korte * 8,))   # hent litt ekstra, velg tilfeldig
                alle_korte = [row[0] for row in cur.fetchall()]
                random.shuffle(alle_korte)
                korte = alle_korte[:maks_korte]

            return vanlige + korte
    finally:
        conn.close()


def lagre_kryssord(
    database_url:      str,
    resultat:          GridResultat,
    storrelse:         int,
    vanskelighetsgrad: str,
    tittel:            str | None = None,
    publiser:          bool = False,
) -> str:
    """Lagrer GridResultat i kryssord-tabellen. Returnerer UUID."""
    import json as _json
    vanskelighet_db = {"lett": "lett", "middels": "middels", "vanskelig": "vanskelig"}
    tittel = tittel or f"Kryssord {storrelse}×{storrelse}"

    sql = """
        INSERT INTO kryssord
          (tittel, vanskelighetsgrad, grid_storrelse, grid_json, ledetrad_json, publisert)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (
                tittel,
                vanskelighet_db.get(vanskelighetsgrad, "middels"),
                storrelse,
                _json.dumps(resultat.grid_json,     ensure_ascii=False),
                _json.dumps(resultat.ledetrad_json, ensure_ascii=False),
                publiser,
            ))
            kryssord_id = str(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO kryssord_statistikk (kryssord_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (kryssord_id,),
            )
        conn.commit()
        return kryssord_id
    finally:
        conn.close()


def generer_og_lagre(
    database_url:      str,
    storrelse:         int   = 13,
    vanskelighetsgrad: str   = "middels",
    publiser:          bool  = False,
    tittel:            str | None = None,
    maks_tid:          float = 15.0,
    seed:              int | None = None,
) -> dict:
    """
    Konvenienssfunksjon: henter ord, genererer kryssord og lagrer det.
    Returnerer dict med id, antall_ord, tid_sekunder.
    """
    t0 = time.monotonic()

    ord_liste = hent_ord_fra_db(database_url, vanskelighetsgrad, storrelse)
    if len(ord_liste) < 20:
        raise ValueError(
            f"For få ord i databasen for {vanskelighetsgrad}/{storrelse}: {len(ord_liste)}"
        )

    generator = KryssordGenerator(
        ord_liste, storrelse, vanskelighetsgrad, maks_tid=maks_tid, seed=seed
    )
    resultat = generator.generer()

    if resultat is None:
        raise RuntimeError(f"Klarte ikke generere {storrelse}×{storrelse} kryssord innen {maks_tid}s")

    kryssord_id = lagre_kryssord(
        database_url, resultat, storrelse, vanskelighetsgrad, tittel, publiser
    )

    tid = round(time.monotonic() - t0, 2)
    log.info("Generert %dx%d (%s) med %d ord på %.2fs", storrelse, storrelse, vanskelighetsgrad, resultat.antall_ord, tid)

    return {
        "id":          kryssord_id,
        "storrelse":   storrelse,
        "antall_ord":  resultat.antall_ord,
        "publisert":   publiser,
        "tid_sekunder": tid,
    }


# ---------------------------------------------------------------------------
# Benchmark – kjøres direkte: python kryssord_generator.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os, statistics
    from pathlib import Path
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
    db_url = os.environ["DATABASE_URL"]

    print("\n=== Kryssord-generator benchmark (10 kjøringer per konfigurasjon) ===\n")

    konfigurasjoner = [
        (9,  "lett"),
        (13, "middels"),
        (17, "vanskelig"),
    ]

    for storrelse, vanskelighetsgrad in konfigurasjoner:
        tider:    list[float] = []
        ant_ord:  list[int]   = []
        feil                  = 0

        print(f"  {storrelse}×{storrelse} / {vanskelighetsgrad}", end="", flush=True)
        ord_liste = hent_ord_fra_db(db_url, vanskelighetsgrad, storrelse)
        print(f" ({len(ord_liste)} ord i pool)", end="", flush=True)

        for i in range(10):
            t0 = time.monotonic()
            gen = KryssordGenerator(ord_liste, storrelse, vanskelighetsgrad, maks_tid=15.0)
            res = gen.generer()
            t1 = time.monotonic()

            if res:
                tider.append(t1 - t0)
                ant_ord.append(res.antall_ord)
                print(".", end="", flush=True)
            else:
                feil += 1
                print("x", end="", flush=True)

        print()
        if tider:
            print(
                f"    Tid:     snitt={statistics.mean(tider):.2f}s  "
                f"min={min(tider):.2f}s  max={max(tider):.2f}s"
            )
            print(
                f"    Ord:     snitt={statistics.mean(ant_ord):.1f}  "
                f"min={min(ant_ord)}  max={max(ant_ord)}"
            )
        print(f"    Feil:    {feil}/10\n")
