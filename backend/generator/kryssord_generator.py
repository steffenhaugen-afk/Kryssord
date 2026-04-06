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
        "min_len":        3,
        "max_len":        7,     # korte ord → naturlig tettere svartmønster
        "pool_size":      30000,
        "ordklasser":     ("substantiv", "verb", "adjektiv"),
        "min_ord":        12,
        "maal_svart_pst": 20,    # stopp filling her (med nok ord)
        "min_svart_pst":  15,    # akseptgrense
        "maks_svart_pst": 28,
        "maks_korte":     2,
    },
    "middels": {
        "min_len":        4,
        "max_len":        11,
        "pool_size":      60000,
        "ordklasser":     ("substantiv", "verb", "adjektiv", "egennavn"),
        "min_ord":        22,
        "maal_svart_pst": 20,
        "min_svart_pst":  15,
        "maks_svart_pst": 28,
        "maks_korte":     2,
    },
    "vanskelig": {
        "min_len":        5,
        "max_len":        15,
        "pool_size":      80000,
        "ordklasser":     ("substantiv", "verb", "adjektiv", "egennavn"),
        "min_ord":        32,
        "maal_svart_pst": 20,
        "min_svart_pst":  15,
        "maks_svart_pst": 28,
        "maks_korte":     3,
    },
}

GRID_MAKS_ORDLENGDE = {9: 9, 13: 13, 17: 17}


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
        """
        Sjekker om et ord kan plasseres.

        Regler:
        - Ord må være innenfor grid-grensene
        - Ingen løpende nabo rett før/etter ordet (unngår ord som støter sammen)
        - Ingen bokstavkonflikter med allerede plasserte bokstaver
        - Minst ett kryss med en eksisterende bokstav
        """
        n = len(ord_)

        if retning == ACROSS:
            if kol < 0 or kol + n > self.n or rad < 0 or rad >= self.n:
                return False
            # Ingen løpende nabo rett FØR og ETTER ordet
            if kol > 0 and self.celler[rad][kol - 1] != "#":
                return False
            if kol + n < self.n and self.celler[rad][kol + n] != "#":
                return False
            for i, bokstav in enumerate(ord_):
                celle = self.celler[rad][kol + i]
                if celle != "#" and celle != bokstav:
                    return False
        else:
            if rad < 0 or rad + n > self.n or kol < 0 or kol >= self.n:
                return False
            if rad > 0 and self.celler[rad - 1][kol] != "#":
                return False
            if rad + n < self.n and self.celler[rad + n][kol] != "#":
                return False
            for i, bokstav in enumerate(ord_):
                celle = self.celler[rad + i][kol]
                if celle != "#" and celle != bokstav:
                    return False

        # Krev minst ett kryss med eksisterende bokstav
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
            # Ingen løpende nabo rett før/etter
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

        # Krev minst én eksisterende bokstav (kryss) i sloten
        har_kryss = any(self.celler[r][c] != "#" for r, c in slot.celler())
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

        # Bruk alle ord (hent_ord_fra_db begrenser allerede til pool_size)
        valgte_korte = korte[:maks_korte]
        filtrert = vanlige + valgte_korte

        self._ord_liste = filtrert
        self._index     = WordIndex(self._ord_liste)
        self._ord_sett  = set(self._ord_liste)

    # ---- Offentlig API ----

    def generer(self) -> GridResultat | None:
        """
        Returnerer et GridResultat eller None hvis ingen løsning finnes
        innen maks_tid sekunder.

        Strategi: bygg ryggrad (lange kryss-ord i midten), deretter greedy fill.
        Prøver inntil 3 ganger.
        """
        start = time.monotonic()
        maks_forsok = 5

        for forsok in range(maks_forsok):
            elapsed = time.monotonic() - start
            if elapsed > self.maks_tid * 0.95:
                break

            tid_per_forsok = (self.maks_tid - elapsed) / (maks_forsok - forsok)
            forsok_start   = time.monotonic()

            grid       = Grid(self.storrelse)
            plasserte: list[OrdPlassering] = []
            brukte_ord: set[str] = set()

            if not self._konstruer_ryggrad(grid, plasserte, brukte_ord, forsok):
                continue

            self._fyll_graadig(grid, plasserte, brukte_ord, forsok_start, tid_per_forsok)
            self._juster_svarte_ruter(grid)

            n          = self.storrelse
            svarte     = sum(1 for rad in grid.celler for c in rad if c == "#")
            svart_pst  = svarte / (n * n) * 100
            min_svart  = self.cfg.get("min_svart_pst",  12)
            maks_svart = self.cfg.get("maks_svart_pst", 30)

            log.info(
                "Forsøk %d/%d: %d ord, %.1f%% svarte ruter (%d–%d%%)",
                forsok + 1, maks_forsok, len(plasserte), svart_pst,
                min_svart, maks_svart,
            )

            if (len(plasserte) >= self.min_ord
                    and min_svart <= svart_pst <= maks_svart):
                return self._bygg_resultat(grid, plasserte)

        log.warning(
            "Klarte ikke fylle brettet etter %d forsøk (min_ord=%d)",
            maks_forsok, self.min_ord,
        )
        return None

    def _konstruer_ryggrad(
        self,
        grid:       Grid,
        plasserte:  list[OrdPlassering],
        brukte_ord: set[str],
        forsok:     int,
    ) -> bool:
        """
        Legger 1-3 startord som dekker ulike deler av brettet:
        - Første ord ACROSS i midtraden (grunnspine)
        - Deretter ned-ord som krysser det og spenner topp/bunn
        Returnerer False hvis ingen startord ble funnet.
        """
        n    = self.storrelse
        midt = n // 2

        alle_sortert = sorted(self._ord_liste, key=lambda x: -len(x))

        # --- 1. Langt ACROSS-ord i midten ---
        h_kand = [o for o in alle_sortert if self.cfg["min_len"] + 2 <= len(o) <= self.maks_ordlen]
        if not h_kand:
            return False

        forste    = h_kand[forsok % min(5, len(h_kand))]
        start_kol = (n - len(forste)) // 2
        grid.plasser(forste, midt, start_kol, ACROSS)
        plasserte.append(OrdPlassering(forste, ACROSS, midt, start_kol))
        brukte_ord.add(forste)

        # --- 2. Lange ned-ord som krysser midtordet og dekker topp til bunn ---
        # Prøv å plassere 2-3 ned-ord ved ulike kolonner i midtordet
        # slik at vi har bokstaver i rad 0 og rad n-1
        kol_kand = list(range(start_kol, start_kol + len(forste)))
        random.shuffle(kol_kand)
        ned_plassert = 0

        for kol in kol_kand:
            if ned_plassert >= max(2, n // 4):
                break
            bokstav = grid.celler[midt][kol]

            # Finn ned-ord som spenner fra rad 0 til midt (eller midt til n-1)
            for lengde in range(min(n, self.maks_ordlen), self.cfg["min_len"] - 1, -1):
                funnet = False
                for start_rad in [0, max(0, midt - lengde + 1), midt]:
                    pos_i_ord = midt - start_rad
                    if pos_i_ord < 0 or pos_i_ord >= lengde:
                        continue
                    if start_rad + lengde > n:
                        continue

                    # Sjekk at dette ned-ordet ikke kolliderer
                    konflikt = False
                    for ii in range(lengde):
                        celle = grid.celler[start_rad + ii][kol]
                        if ii == pos_i_ord:
                            if celle != bokstav and celle != "#":
                                konflikt = True
                                break
                        elif celle != "#":
                            konflikt = True
                            break
                    if konflikt:
                        continue

                    passende = [
                        o for o in alle_sortert
                        if len(o) == lengde
                        and o[pos_i_ord] == bokstav
                        and o not in brukte_ord
                    ]
                    random.shuffle(passende)
                    for ned_ord in passende[:8]:
                        # Enkel bounds+konflikt-sjekk (ikke den strenge kan_plassere)
                        if start_rad + lengde <= n:
                            ok = True
                            for ii, bk in enumerate(ned_ord):
                                celle = grid.celler[start_rad + ii][kol]
                                if celle != "#" and celle != bk:
                                    ok = False
                                    break
                            if ok:
                                grid.plasser(ned_ord, start_rad, kol, DOWN)
                                plasserte.append(OrdPlassering(ned_ord, DOWN, start_rad, kol))
                                brukte_ord.add(ned_ord)
                                ned_plassert += 1
                                funnet = True
                                break
                    if funnet:
                        break
                if funnet:
                    break

        return True

    # ---- Internals ----

    def _fyll_graadig(
        self,
        grid:       Grid,
        plasserte:  list[OrdPlassering],
        brukte_ord: set[str],
        start_tid:  float,
        maks_tid:   float,
    ) -> None:
        """
        Greedy fill – fortsetter å plassere ord til ingen flere passer
        ELLER til svartandelen faller under måltettheten.

        Velger alltid sloten med færrest gyldige kandidater (MCV) og
        plasserer det første ordet som faktisk kan settes inn.  Ingen
        backtracking – et plassert ord blir aldri angret.
        """
        n         = grid.n
        # Stopp primært ved måltettheten (17%).
        # Hvis vi mangler nok ord, fortsetter vi ned til minimumsgrensen (12%).
        maal_pst  = self.cfg.get("maal_svart_pst", 17) / 100
        stopp_pst = self.cfg.get("min_svart_pst",  12) / 100

        while time.monotonic() - start_tid < maks_tid:
            svarte = sum(1 for rad in grid.celler for c in rad if c == "#")
            svart_andel = svarte / (n * n)
            # Stopp ved målet med mindre vi fremdeles mangler nok ord
            if svart_andel <= maal_pst and len(plasserte) >= self.min_ord:
                break
            # Hard stopp ved minimumgrensen
            if svart_andel <= stopp_pst:
                break

            slots = grid.finn_slots(brukte_ord, self.cfg["min_len"], self.maks_ordlen)

            gyldige: list[tuple[Slot, list[str]]] = []
            for slot in slots:
                kands = [
                    k for k in self._index.kandidater(slot, grid.celler)
                    if k not in brukte_ord
                ]
                if kands:
                    gyldige.append((slot, kands))

            if not gyldige:
                break

            # MCV: mest begrensede slot først
            gyldige.sort(key=lambda x: len(x[1]))

            plassert = False
            for slot, kands in gyldige:
                kands_prøv = kands[:30]
                random.shuffle(kands_prøv)
                for ord_ in kands_prøv:
                    if grid.kan_plassere(ord_, slot.rad, slot.kol, slot.retning):
                        grid.plasser(ord_, slot.rad, slot.kol, slot.retning)
                        plasserte.append(
                            OrdPlassering(ord_, slot.retning, slot.rad, slot.kol)
                        )
                        brukte_ord.add(ord_)
                        plassert = True
                        break
                if plassert:
                    break

            if not plassert:
                break

    def _juster_svarte_ruter(self, grid: Grid) -> None:
        """
        Legg til svarte ruter med 180°-rotasjonssymmetri til vi når maal_svart_pst.

        Strategi – finner celler som trygt kan bli svarte:
        En celle (r,c) er trygt svart hvis:
          - Den er allerede '#', OG
          - Det ikke finnes bokstaver på BEGGE sider horisontalt
            (da ville vi delt et horisontalt ord), OG
          - Det ikke finnes bokstaver på BEGGE sider vertikalt.

        For celler med bokstav: aldri konverter – det ville fjerne et ord.

        Kaller vi par (r,c) + speil (n-1-r, n-1-c): begge må oppfylle kravet.
        """
        n         = grid.n
        maal      = self.cfg.get("maal_svart_pst", 17) / 100
        min_svart = self.cfg.get("min_svart_pst",  12) / 100

        def svart_pst() -> float:
            return sum(1 for rad in grid.celler for c in rad if c == "#") / (n * n)

        if svart_pst() >= min_svart:
            return  # allerede innenfor ønsket område

        def er_trygg(r: int, c: int) -> bool:
            if grid.celler[r][c] != "#":
                return False
            h_v = c > 0     and grid.celler[r][c - 1] != "#"
            h_h = c < n - 1 and grid.celler[r][c + 1] != "#"
            v_o = r > 0     and grid.celler[r - 1][c] != "#"
            v_u = r < n - 1 and grid.celler[r + 1][c] != "#"
            if h_v and h_h:
                return False   # horisontalt ord splittes
            if v_o and v_u:
                return False   # vertikalt ord splittes
            return True

        # Samle gyldige symmetriske par, prioriter de nærmest midten
        # (hjørner/kanter er gjerne de enkleste å legge svarte ruter)
        sett: set[tuple] = set()
        par_liste: list[tuple] = []
        midt = n / 2
        for r in range(n):
            for c in range(n):
                sr, sc = n - 1 - r, n - 1 - c
                if (r, c) == (sr, sc):
                    continue
                nøkkel = (min(r, sr), min(c, sc), max(r, sr), max(c, sc))
                if nøkkel in sett:
                    continue
                sett.add(nøkkel)
                if er_trygg(r, c) and er_trygg(sr, sc):
                    # Avstand fra sentrum – foretrekk celler langt fra midten
                    avstand = (r - midt) ** 2 + (c - midt) ** 2
                    par_liste.append((avstand, (r, c), (sr, sc)))

        # Sorter: lengst fra sentrum først (hjørner og kanter)
        par_liste.sort(key=lambda x: -x[0])

        for _, (r, c), (sr, sc) in par_liste:
            if svart_pst() >= maal:
                break
            grid.celler[r][c]   = "#"
            grid.celler[sr][sc] = "#"

        log.debug(
            "Etter symmetri-justering: %.1f%% svarte ruter (mål %.1f%%)",
            svart_pst() * 100, maal * 100,
        )

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

    # Vanlige ord (3+ bokstaver, ingen sammensatte, med gyldig ledetråd)
    sql_vanlg = f"""
        SELECT tekst FROM ord o
        WHERE bokstavlengde BETWEEN %s AND %s
          AND ordklasse IN ({placeholders})
          AND har_bindestrek = false
          AND har_mellomrom  = false
          AND tekst ~ '^[a-zæøå]+$'
          AND (
            EXISTS (
              SELECT 1 FROM kryssord_ledetrad_par klp
              WHERE UPPER(klp.svar) = UPPER(o.tekst)
            )
            OR EXISTS (
              SELECT 1 FROM synonymer s
              WHERE s.ord_id = o.id AND s.relasjon_type = 'synonym'
            )
            OR EXISTS (
              SELECT 1 FROM ord_kategorier ok
              JOIN kategorier k ON k.id = ok.kategori_id
              WHERE ok.ord_id = o.id
                AND k.navn IN (
                  'Norske politikere', 'Norske kommuner og byer',
                  'Norske fjell', 'Norske kunstnere og musikere',
                  'Norske fornavn', 'Norske etternavn',
                  'Europeiske land', 'Verdens land', 'Verdens byer'
                )
            )
          )
        ORDER BY random()
        LIMIT %s
    """

    # Korte ord (2 bokstaver) – begrenset antall per brett, med gyldig ledetråd
    sql_korte = """
        SELECT tekst FROM ord o
        WHERE kort_ord = true
          AND har_bindestrek = false
          AND har_mellomrom  = false
          AND tekst ~ '^[a-zæøå]+$'
          AND (
            EXISTS (
              SELECT 1 FROM kryssord_ledetrad_par klp
              WHERE UPPER(klp.svar) = UPPER(o.tekst)
            )
            OR EXISTS (
              SELECT 1 FROM synonymer s
              WHERE s.ord_id = o.id AND s.relasjon_type = 'synonym'
            )
          )
        ORDER BY random()
        LIMIT %s
    """

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            min_len = max(cfg["min_len"], 3)   # aldri under 3 for vanlige ord
            cur.execute(sql_vanlg, (min_len, maks_len, *ordklasser, cfg["pool_size"]))
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
    maks_tid:          float = 30.0,
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
# CLI – generer og vis ASCII-grid: python kryssord_generator.py [storrelse] [vanskelighetsgrad]
# ---------------------------------------------------------------------------
def _print_ascii_grid(grid_data: dict, ledetrad_json: dict) -> None:
    celler = grid_data["celler"]
    n      = len(celler)

    hvite     = sum(1 for rad in celler for c in rad if c != "#")
    svart_pst = (n * n - hvite) / (n * n) * 100

    print(f"\n  {'─' * (n * 4 - 1)}")
    for rad in celler:
        linje = "  "
        for celle in rad:
            if celle == "#":
                linje += "███ "
            else:
                linje += f" {celle.upper()}  "
        print(linje)
    print(f"  {'─' * (n * 4 - 1)}")
    print(f"\n  Svarte ruter: {n * n - hvite}/{n * n} ({svart_pst:.1f}%)")

    print("\n  Vannrett (across):")
    for nr, oppslag in sorted(ledetrad_json.get("across", {}).items(), key=lambda x: int(x[0])):
        print(f"    {nr:>3}. {oppslag['tekst'].upper():<15} ({oppslag['ledetrad']})")

    print("\n  Loddrett (down):")
    for nr, oppslag in sorted(ledetrad_json.get("down", {}).items(), key=lambda x: int(x[0])):
        print(f"    {nr:>3}. {oppslag['tekst'].upper():<15} ({oppslag['ledetrad']})")


if __name__ == "__main__":
    import os, sys, statistics
    from pathlib import Path
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
    db_url = os.environ["DATABASE_URL"]

    # Les argumenter: storrelse og vanskelighetsgrad
    args = sys.argv[1:]
    if args and args[0].isdigit():
        storrelse = int(args[0])
        args = args[1:]
    else:
        storrelse = 9

    if args and args[0] in VANSKELIGHET:
        vanskelighetsgrad = args[0]
    else:
        vanskelighetsgrad = "lett" if storrelse == 9 else ("middels" if storrelse == 13 else "vanskelig")

    print(f"\n=== Genererer {storrelse}×{storrelse} kryssord ({vanskelighetsgrad}) ===\n")

    ord_liste = hent_ord_fra_db(db_url, vanskelighetsgrad, storrelse)
    print(f"  Ord i pool: {len(ord_liste)}")

    min_ord = VANSKELIGHET[vanskelighetsgrad]["min_ord"]
    maks_svart = VANSKELIGHET[vanskelighetsgrad]["maks_svart_pst"]
    print(f"  Mål: min {min_ord} ord, maks {maks_svart}% svarte ruter\n")

    t0  = time.monotonic()
    gen = KryssordGenerator(ord_liste, storrelse, vanskelighetsgrad, maks_tid=30.0)
    res = gen.generer()
    tid = time.monotonic() - t0

    if res is None:
        print("  FEIL: Klarte ikke generere kryssord.")
        sys.exit(1)

    print(f"\n  Resultat: {res.antall_ord} ord plassert på {tid:.1f}s\n")
    _print_ascii_grid(res.grid_json, res.ledetrad_json)

    # Benchmark – 5 kjøringer
    print("\n\n=== Benchmark (5 kjøringer) ===\n")
    tider: list[float] = []
    ant_ord: list[int] = []
    feil = 0

    for i in range(5):
        t0  = time.monotonic()
        gen = KryssordGenerator(ord_liste, storrelse, vanskelighetsgrad, maks_tid=30.0)
        r   = gen.generer()
        t1  = time.monotonic()
        if r:
            tider.append(t1 - t0)
            ant_ord.append(r.antall_ord)
            print(f"  {i+1}. {r.antall_ord} ord ({t1-t0:.1f}s)")
        else:
            feil += 1
            print(f"  {i+1}. FEIL")

    if tider:
        print(f"\n  Snitt: {statistics.mean(ant_ord):.1f} ord, {statistics.mean(tider):.1f}s")
        print(f"  Min/max ord: {min(ant_ord)} / {max(ant_ord)}")
    print(f"  Feil: {feil}/5")
