"""
LedetradGenerator – genererer kontekstuelle ledetråder for hvert ord i et kryssord.

Strategi per ordklasse
-----------------------
substantiv / verb / adjektiv
    → Synonym fra synonymer-tabellen (korteste synonym prioriteres,
      unngår samme rot som selve ordet).
    → Fallback: ordklasse + lengde, f.eks. "Substantiv (5 bokstaver)"

egennavn
    → Kategori-basert mal, f.eks. "Norsk politiker (7 bokstaver)".
    → Prioriteringsliste: spesifikk kategori > generisk egennavn-mal.

Formater
--------
  Med synonym:     "Synonym for X (5 bokstaver)"   – hvis synonymet er informativt
  Egennavn:        "Norsk fjell (8 bokstaver)"
  Ingen data:      "Se opp (5 bokstaver)"           – nøytral fallback
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import psycopg2
import psycopg2.extras

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kategori → norsk ledetråd-mal
# ---------------------------------------------------------------------------
_KATEGORI_MAL: dict[str, str] = {
    "Norske politikere":            "Norsk politiker",
    "Norske kommuner og byer":      "Norsk by",
    "Norske fjell":                 "Norsk fjell",
    "Norske kunstnere og musikere": "Norsk kunstner",
    "Norske fornavn":               "Norsk fornavn",
    "Norske etternavn":             "Norsk etternavn",
    "Europeiske land":              "Europeisk land",
    "Verdens land":                 "Land i verden",
    "Verdens byer":                 "Verdensby",
}

_ORDKLASSE_MAL: dict[str, str] = {
    "substantiv": "Substantiv",
    "verb":       "Verb",
    "adjektiv":   "Adjektiv",
    "egennavn":   "Egennavn",
}


# ---------------------------------------------------------------------------
# Dataklasser
# ---------------------------------------------------------------------------
@dataclass
class LedetradOppslag:
    tekst:         str
    ordklasse:     str | None
    ledetrad:      str
    kilde:         str          # "synonym" | "kategori" | "ordklasse" | "fallback"
    synonymer:     list[str]    = field(default_factory=list)
    kategorier:    list[str]    = field(default_factory=list)


# ---------------------------------------------------------------------------
# Databaseuthenting
# ---------------------------------------------------------------------------
def _hent_ord_info(
    cur,
    tekst_liste: list[str],
) -> dict[str, dict]:
    """
    Henter ordklasse, synonymer og kategorier for en liste med ord.
    Returnerer {tekst: {ordklasse, synonymer, kategorier}}.
    """
    if not tekst_liste:
        return {}

    placeholders = ",".join(["%s"] * len(tekst_liste))

    # Ordklasse
    cur.execute(
        f"SELECT tekst, ordklasse FROM ord WHERE tekst IN ({placeholders})",
        tekst_liste,
    )
    ord_info: dict[str, dict] = {
        row[0]: {"ordklasse": row[1], "synonymer": [], "kategorier": []}
        for row in cur.fetchall()
    }

    # Synonymer: hent synonym-tekst for hvert basisord
    cur.execute(
        f"""
        SELECT o.tekst, os.tekst AS syn
        FROM synonymer s
        JOIN ord o  ON o.id  = s.ord_id
        JOIN ord os ON os.id = s.synonym_id
        WHERE o.tekst IN ({placeholders})
          AND s.relasjon_type = 'synonym'
        ORDER BY LENGTH(os.tekst)
        """,
        tekst_liste,
    )
    for tekst, syn in cur.fetchall():
        if tekst in ord_info:
            ord_info[tekst]["synonymer"].append(syn)

    # Kategorier
    cur.execute(
        f"""
        SELECT o.tekst, k.navn
        FROM ord_kategorier ok
        JOIN ord        o ON o.id = ok.ord_id
        JOIN kategorier k ON k.id = ok.kategori_id
        WHERE o.tekst IN ({placeholders})
        ORDER BY k.navn
        """,
        tekst_liste,
    )
    for tekst, kat in cur.fetchall():
        if tekst in ord_info:
            ord_info[tekst]["kategorier"].append(kat)

    return ord_info


# ---------------------------------------------------------------------------
# Ledetråd-logikk
# ---------------------------------------------------------------------------
def _velg_synonym(tekst: str, synonymer: list[str]) -> str | None:
    """
    Velger det beste synonymet:
    – Filtrerer ut synonymet hvis det starter med samme rot som ordet
      (unngår "abstraksjon → abstrahering" som er for åpenbar).
    – Prioriterer kortere synonymer.
    """
    rot = tekst[:4].lower()
    kandidater = [
        s for s in synonymer
        if s.lower() != tekst.lower() and not s.lower().startswith(rot)
    ]
    if not kandidater:
        kandidater = [s for s in synonymer if s.lower() != tekst.lower()]
    return kandidater[0] if kandidater else None


def _lengde_streng(tekst: str) -> str:
    """
    Returnerer lengde-representasjonen for ledetråden.

    Enkle ord:        "6 bokstaver"
    Sammensatte ord:  "5-4-5"   (lengden av hvert del, uten separator)
    """
    if "-" in tekst or " " in tekst:
        separator = "-" if "-" in tekst else " "
        deler = tekst.split(separator)
        del_lengder = [str(len(d)) for d in deler if d]
        return "-".join(del_lengder)
    return f"{len(tekst)} bokstaver"


def _kategori_ledetrad(kategorier: list[str], tekst: str) -> str | None:
    """Finner beste kategori-mal. Returnerer ferdig ledetråd eller None."""
    lengde_str = _lengde_streng(tekst)
    for kat in kategorier:
        if kat in _KATEGORI_MAL:
            return f"{_KATEGORI_MAL[kat]} ({lengde_str})"
    return None


def lag_ledetrad(
    tekst:     str,
    ordklasse: str | None,
    synonymer: list[str],
    kategorier: list[str],
) -> LedetradOppslag:
    """Bygger en LedetradOppslag for ett ord."""
    lengde_str = _lengde_streng(tekst)
    # Faktisk bokstavlengde (uten separatorer) — brukes til fallback-tekster
    bokstavlengde = len(tekst.replace("-", "").replace(" ", ""))

    # 1. Egennavn → prøv kategori-mal
    if ordklasse == "egennavn" or (not ordklasse and kategorier):
        kat_ledetrad = _kategori_ledetrad(kategorier, tekst)
        if kat_ledetrad:
            return LedetradOppslag(
                tekst=tekst,
                ordklasse=ordklasse,
                ledetrad=kat_ledetrad,
                kilde="kategori",
                synonymer=synonymer,
                kategorier=kategorier,
            )
        return LedetradOppslag(
            tekst=tekst,
            ordklasse=ordklasse,
            ledetrad=f"Egennavn ({lengde_str})",
            kilde="ordklasse",
            synonymer=synonymer,
            kategorier=kategorier,
        )

    # 2. Vanlige ord → prøv synonym
    if synonymer:
        valgt = _velg_synonym(tekst, synonymer)
        if valgt:
            return LedetradOppslag(
                tekst=tekst,
                ordklasse=ordklasse,
                ledetrad=f"{valgt.capitalize()} ({lengde_str})",
                kilde="synonym",
                synonymer=synonymer,
                kategorier=kategorier,
            )

    # 3. Ordklasse-fallback
    if ordklasse and ordklasse in _ORDKLASSE_MAL:
        return LedetradOppslag(
            tekst=tekst,
            ordklasse=ordklasse,
            ledetrad=f"{_ORDKLASSE_MAL[ordklasse]} ({lengde_str})",
            kilde="ordklasse",
            synonymer=synonymer,
            kategorier=kategorier,
        )

    # 4. Nøytral fallback
    return LedetradOppslag(
        tekst=tekst,
        ordklasse=ordklasse,
        ledetrad=f"Se opp ({lengde_str})",
        kilde="fallback",
        synonymer=synonymer,
        kategorier=kategorier,
    )


# ---------------------------------------------------------------------------
# Offentlig API
# ---------------------------------------------------------------------------
class LedetradGenerator:
    """
    Henter ord-info fra DB og genererer ledetråder for alle ord
    i et kryssords ledetrad_json.
    """

    def __init__(self, database_url: str) -> None:
        self._db_url = database_url

    def generer_for_kryssord(self, ledetrad_json: dict) -> dict:
        """
        Tar inn eksisterende ledetrad_json (fra kryssord-tabellen),
        beriker hvert oppslag med en reell ledetråd og returnerer
        oppdatert JSON.
        """
        alle_tekster = [
            oppslag["tekst"]
            for retning in ("across", "down")
            for oppslag in ledetrad_json.get(retning, {}).values()
            if "tekst" in oppslag
        ]

        if not alle_tekster:
            return ledetrad_json

        ord_info = self._hent_info(alle_tekster)
        oppdatert = {"across": {}, "down": {}}

        for retning in ("across", "down"):
            for nr, oppslag in ledetrad_json.get(retning, {}).items():
                tekst = oppslag.get("tekst", "")
                info  = ord_info.get(tekst, {})

                resultat = lag_ledetrad(
                    tekst=tekst,
                    ordklasse=info.get("ordklasse"),
                    synonymer=info.get("synonymer", []),
                    kategorier=info.get("kategorier", []),
                )

                oppdatert[retning][nr] = {
                    **oppslag,
                    "ledetrad":  resultat.ledetrad,
                    "kilde":     resultat.kilde,
                }

                log.debug(
                    "%-15s  [%s]  →  %s  (%s)",
                    tekst,
                    info.get("ordklasse", "?"),
                    resultat.ledetrad,
                    resultat.kilde,
                )

        return oppdatert

    def oppdater_kryssord_i_db(self, kryssord_id: str) -> dict:
        """
        Henter ledetrad_json fra DB, beriker og lagrer tilbake.
        Returnerer statistikk-dict.
        """
        import json

        conn = psycopg2.connect(self._db_url)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT ledetrad_json FROM kryssord WHERE id = %s",
                    (kryssord_id,),
                )
                rad = cur.fetchone()
                if not rad:
                    raise ValueError(f"Kryssord {kryssord_id} ikke funnet")

                ledetrad_json = rad["ledetrad_json"]
                if isinstance(ledetrad_json, str):
                    ledetrad_json = json.loads(ledetrad_json)

            oppdatert = self.generer_for_kryssord(ledetrad_json)

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE kryssord SET ledetrad_json = %s WHERE id = %s",
                    (json.dumps(oppdatert, ensure_ascii=False), kryssord_id),
                )
            conn.commit()

        finally:
            conn.close()

        return _lag_statistikk(oppdatert)

    def _hent_info(self, tekst_liste: list[str]) -> dict[str, dict]:
        conn = psycopg2.connect(self._db_url)
        try:
            with conn.cursor() as cur:
                return _hent_ord_info(cur, tekst_liste)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Statistikk
# ---------------------------------------------------------------------------
def _lag_statistikk(ledetrad_json: dict) -> dict:
    kilde_teller: dict[str, int] = {}
    totalt = 0

    for retning in ("across", "down"):
        for oppslag in ledetrad_json.get(retning, {}).values():
            kilde = oppslag.get("kilde", "ukjent")
            kilde_teller[kilde] = kilde_teller.get(kilde, 0) + 1
            totalt += 1

    return {"totalt": totalt, "per_kilde": kilde_teller}


# ---------------------------------------------------------------------------
# CLI – test mot et eksisterende kryssord
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import os
    import sys
    from pathlib import Path

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
    db_url = os.environ["DATABASE_URL"]

    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SELECT id, tittel FROM kryssord ORDER BY opprettet_dato DESC LIMIT 1")
        row = cur.fetchone()
    conn.close()

    if not row:
        print("Ingen kryssord i databasen")
        sys.exit(1)

    kryssord_id, tittel = row
    print(f"\nOppdaterer ledetråder for: {tittel} (id={kryssord_id})\n")

    gen   = LedetradGenerator(db_url)
    stats = gen.oppdater_kryssord_i_db(str(kryssord_id))

    print(f"\n=== Rapport ===")
    print(f"  Totalt ord:  {stats['totalt']}")
    for kilde, antall in sorted(stats["per_kilde"].items()):
        print(f"  {kilde:<12} {antall}")

    # Skriv ut ferdig ledetrad_json
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SELECT ledetrad_json FROM kryssord WHERE id = %s", (str(kryssord_id),))
        data = cur.fetchone()[0]
    conn.close()
    if isinstance(data, str):
        data = json.loads(data)

    print("\n=== Ledetråder ===")
    for retning in ("across", "down"):
        for nr, oppslag in sorted(data.get(retning, {}).items(), key=lambda x: int(x[0])):
            print(f"  {nr:>3} {'→' if retning == 'across' else '↓'}  "
                  f"{oppslag.get('tekst',''):15}  {oppslag.get('ledetrad','')}")
