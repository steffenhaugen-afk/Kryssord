"""
[DEAKTIVERT – erstattet av kryssordkongen/NorWordNet/NAOB]

AI-basert ledetråd-generator for norske kryssord.

Bruker Anthropic Claude API til å generere ledetråder når synonym-databasen
ikke har gode nok alternativer.  Genererte ledetråder caches i ai_ledetrad-tabellen
slik at samme ord aldri kalles to ganger mot APIet.

Bruk:
    generator = AILedetradGenerator(database_url, api_key)
    ledetrad  = generator.hent_eller_generer("impregnere", "verb", kategorier=[])

    # Batch-generering av de N vanligste ordene:
    generator.batch_generer(n=5000, kall_per_sekund=10)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg2
import psycopg2.extras

log = logging.getLogger(__name__)

MODELL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = (
    "Du er ekspert på norske kryssord. Generer én kort, presis ledetråd på norsk "
    "for et kryssordord. Ledetråden skal:\n"
    "- Være et synonym, beskrivelse eller assosiasjon\n"
    "- ALDRI inneholde selve ordet eller en åpenbar variant av det\n"
    "- Være på 1–5 ord\n"
    "- Ikke avsløre ordklassen eksplisitt (ikke si 'substantiv', 'verb' osv.)\n"
    "Svar kun med ledetråden, ingenting annet."
)


# ---------------------------------------------------------------------------
# Dataklasse
# ---------------------------------------------------------------------------
@dataclass
class AILedetrad:
    ord:        str
    ledetrad:   str
    fra_cache:  bool


# ---------------------------------------------------------------------------
# Hjelpefunksjoner – DB
# ---------------------------------------------------------------------------
def _hent_fra_cache(cur, ord_id: str) -> str | None:
    cur.execute(
        "SELECT ledetrad FROM ai_ledetrad WHERE ord_id = %s",
        (ord_id,),
    )
    rad = cur.fetchone()
    if rad:
        cur.execute(
            "UPDATE ai_ledetrad SET brukt_antall = brukt_antall + 1 WHERE ord_id = %s",
            (ord_id,),
        )
        return rad[0]
    return None


def _lagre_i_cache(cur, ord_id: str, ledetrad: str, modell: str) -> None:
    cur.execute(
        """
        INSERT INTO ai_ledetrad (ord_id, ledetrad, modell)
        VALUES (%s, %s, %s)
        ON CONFLICT (ord_id) DO UPDATE
          SET ledetrad = EXCLUDED.ledetrad,
              modell   = EXCLUDED.modell,
              generert_dato = NOW(),
              brukt_antall  = ai_ledetrad.brukt_antall + 1
        """,
        (ord_id, ledetrad, modell),
    )


# ---------------------------------------------------------------------------
# Hoved-klasse
# ---------------------------------------------------------------------------
class AILedetradGenerator:
    """
    Genererer ledetråder via Claude API med DB-cache.

    Parametere
    ----------
    database_url : str
    api_key      : str  – Anthropic API-nøkkel
    modell       : str  – Claude-modell (default MODELL)
    """

    def __init__(
        self,
        database_url: str,
        api_key:      str,
        modell:       str = MODELL,
    ) -> None:
        self._db_url = database_url
        self._modell = modell

        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------ #
    # Offentlig API                                                        #
    # ------------------------------------------------------------------ #

    def hent_eller_generer(
        self,
        tekst:      str,
        ordklasse:  str | None,
        kategorier: list[str],
        ord_id:     str | None = None,
    ) -> AILedetrad:
        """
        Returnerer en ledetråd for ordet.  Bruker cache hvis tilgjengelig,
        ellers kaller Claude API og lagrer resultatet.
        """
        conn = psycopg2.connect(self._db_url)
        try:
            with conn.cursor() as cur:
                if ord_id is None:
                    cur.execute("SELECT id FROM ord WHERE tekst = %s", (tekst,))
                    rad = cur.fetchone()
                    if rad is None:
                        return AILedetrad(tekst, self._kall_api(tekst, ordklasse, kategorier), False)
                    ord_id = str(rad[0])

                cachet = _hent_fra_cache(cur, ord_id)
                if cachet:
                    conn.commit()
                    return AILedetrad(tekst, cachet, fra_cache=True)

                ledetrad = self._kall_api(tekst, ordklasse, kategorier)
                _lagre_i_cache(cur, ord_id, ledetrad, self._modell)
                conn.commit()
                return AILedetrad(tekst, ledetrad, fra_cache=False)
        finally:
            conn.close()

    def batch_generer(
        self,
        n:                  int   = 5000,
        kall_per_sekund:    float = 10.0,
        hopp_over_cachet:   bool  = True,
    ) -> dict:
        """
        Batch-generer ledetråder for de N vanligste ordene.

        Returnerer statistikk: {generert, cachet, feil, estimert_kostnad_usd}
        """
        conn = psycopg2.connect(self._db_url)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Hent de N vanligste ordene uten synonym og uten AI-cache
                # (de som faktisk vil dra nytte av AI-ledetråder)
                cur.execute(
                    """
                    SELECT o.id, o.tekst, o.ordklasse,
                           COALESCE(
                               ARRAY_AGG(k.navn) FILTER (WHERE k.navn IS NOT NULL),
                               '{}'
                           ) AS kategorier
                    FROM ord o
                    LEFT JOIN ord_kategorier ok ON ok.ord_id = o.id
                    LEFT JOIN kategorier     k  ON k.id = ok.kategori_id
                    WHERE o.har_bindestrek = false
                      AND o.har_mellomrom  = false
                      AND o.tekst ~ '^[a-zæøå]+$'
                      AND o.ordklasse != 'egennavn'
                      AND NOT EXISTS (
                          SELECT 1 FROM synonymer s WHERE s.ord_id = o.id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM ai_ledetrad a WHERE a.ord_id = o.id
                      )
                    GROUP BY o.id, o.tekst, o.ordklasse
                    ORDER BY o.frekvens DESC NULLS LAST, o.bokstavlengde
                    LIMIT %s
                    """,
                    (n,),
                )
                ord_liste = cur.fetchall()
        finally:
            conn.close()

        log.info("Batch-generering: %d ord", len(ord_liste))

        statistikk = {"generert": 0, "cachet": 0, "feil": 0, "input_tokens": 0, "output_tokens": 0}
        min_ventetid = 1.0 / kall_per_sekund

        for i, rad in enumerate(ord_liste):
            ord_id   = str(rad["id"])
            tekst    = rad["tekst"]
            ordklasse = rad["ordklasse"]
            kategorier = list(rad["kategorier"]) if rad["kategorier"] else []

            try:
                resultat = self.hent_eller_generer(tekst, ordklasse, kategorier, ord_id=ord_id)
                if resultat.fra_cache:
                    statistikk["cachet"] += 1
                    log.debug("Cache: %-20s → %s", tekst, resultat.ledetrad)
                else:
                    statistikk["generert"] += 1
                    log.info(
                        "[%d/%d] %-20s → %s",
                        i + 1, len(ord_liste), tekst, resultat.ledetrad,
                    )
                    time.sleep(min_ventetid)
            except Exception as exc:
                statistikk["feil"] += 1
                log.warning("Feil for '%s': %s", tekst, exc)

        # Estimert kostnad: claude-sonnet-4 ≈ $3/Mtok inn, $15/Mtok ut
        # Snitt ~50 input-tokens, ~10 output-tokens per kall
        kall = statistikk["generert"]
        estimert_kostnad = kall * (50 * 3 + 10 * 15) / 1_000_000
        statistikk["estimert_kostnad_usd"] = round(estimert_kostnad, 4)

        return statistikk

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _bygg_prompt(
        self,
        tekst:      str,
        ordklasse:  str | None,
        kategorier: list[str],
    ) -> str:
        deler = [f'Ord: "{tekst}"']
        if ordklasse:
            deler.append(f"Ordklasse: {ordklasse}")
        if kategorier:
            deler.append(f"Kategori: {', '.join(kategorier)}")
        return "\n".join(deler)

    def _kall_api(
        self,
        tekst:      str,
        ordklasse:  str | None,
        kategorier: list[str],
    ) -> str:
        bruker_melding = self._bygg_prompt(tekst, ordklasse, kategorier)

        melding = self._client.messages.create(
            model=self._modell,
            max_tokens=64,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": bruker_melding}],
        )
        ledetrad = melding.content[0].text.strip()

        # Fjern sitattegn hvis modellen la til dem
        ledetrad = ledetrad.strip('"\'')

        # Sikkerhet: avvis svar som inneholder selve ordet
        if tekst.lower() in ledetrad.lower():
            log.warning("API returnerte avslørende ledetråd for '%s': %s", tekst, ledetrad)
            raise ValueError(f"Avslørende ledetråd: {ledetrad!r}")

        return ledetrad


# ---------------------------------------------------------------------------
# CLI – test og batch
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os, sys
    from pathlib import Path
    from dotenv import load_dotenv

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    load_dotenv(Path(__file__).parent.parent.parent / ".env")
    db_url  = os.environ["DATABASE_URL"]
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key:
        print("Feil: ANTHROPIC_API_KEY ikke satt i .env")
        sys.exit(1)

    gen = AILedetradGenerator(db_url, api_key)

    # Test-ord fra rapport + 10 tilfeldige
    test_spesifikke = [
        ("impregnere", "verb",      []),
        ("hevngjerrig", "adjektiv", []),
    ]

    import psycopg2
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tekst, ordklasse FROM ord
            WHERE har_bindestrek = false AND har_mellomrom = false
              AND tekst ~ '^[a-zæøå]{4,8}$'
              AND ordklasse IN ('substantiv','verb','adjektiv')
            ORDER BY random()
            LIMIT 10
            """
        )
        tilfeldige = [(r[0], r[1], []) for r in cur.fetchall()]
    conn.close()

    alle_test = test_spesifikke + tilfeldige
    print(f"\n{'─'*70}")
    print(f"  {'ORD':<20} {'ORDKLASSE':<12} {'GAMMEL LEDETRÅD':<25} NY LEDETRÅD")
    print(f"{'─'*70}")

    # Hent gamle ledetråder fra synonym-DB for sammenligning
    from ledetrad_generator import LedetradGenerator, _hent_ord_info
    ld_gen = LedetradGenerator(db_url)

    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        alle_tekster = [t[0] for t in alle_test]
        ord_info = _hent_ord_info(cur, alle_tekster)
    conn.close()

    from ledetrad_generator import lag_ledetrad
    for tekst, ordklasse, kategorier in alle_test:
        info    = ord_info.get(tekst, {})
        gammel  = lag_ledetrad(
            tekst=tekst,
            ordklasse=info.get("ordklasse", ordklasse),
            synonymer=info.get("synonymer", []),
            kategorier=info.get("kategorier", kategorier),
        )
        try:
            ny = gen.hent_eller_generer(
                tekst, info.get("ordklasse", ordklasse), info.get("kategorier", kategorier)
            )
            cache_mark = "(cache)" if ny.fra_cache else "(ny)"
            ny_tekst = f"{ny.ledetrad} {cache_mark}"
        except Exception as e:
            ny_tekst = f"FEIL: {e}"

        print(f"  {tekst:<20} {(ordklasse or '?'):<12} {gammel.ledetrad:<25} {ny_tekst}")

    print(f"{'─'*70}\n")

    # Spør om batch
    if "--batch" in sys.argv:
        idx = sys.argv.index("--batch")
        n_batch = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 5000
        print(f"\nStarter batch-generering av {n_batch} ord (10 kall/sek)...")
        stats = gen.batch_generer(n=n_batch, kall_per_sekund=10.0)
        print(f"\n=== Batch-rapport ===")
        print(f"  Generert:          {stats['generert']}")
        print(f"  Fra cache:         {stats['cachet']}")
        print(f"  Feil:              {stats['feil']}")
        print(f"  Est. kostnad:      ${stats['estimert_kostnad_usd']:.4f} USD")
