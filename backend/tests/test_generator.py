"""
Enhetstester for kryssordgeneratoren.
Tester ren logikk uten databasetilkobling.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generator.kryssord_generator import Grid, Slot, WordIndex


# ---------------------------------------------------------------------------
# WordIndex
# ---------------------------------------------------------------------------
class TestWordIndex:
    def test_index_bygges_korrekt(self):
        idx = WordIndex(["hund", "katt", "fugl"])
        assert len(idx._idx) > 0

    def test_kandidater_uten_kryss_gir_alle_av_rett_lengde(self):
        idx = WordIndex(["hund", "katt", "fugl", "sol"])
        grid = Grid(9)
        slot = Slot(rad=0, kol=0, retning="across", lengde=4)
        result = idx.kandidater(slot, grid.celler)
        assert set(result) == {"hund", "katt", "fugl"}

    def test_kandidater_med_kryss_filtrerer(self):
        idx = WordIndex(["hund", "katt", "haus"])
        grid = Grid(9)
        # Sett 'h' på posisjon (0, 0) — slot starter der
        grid.celler[0][0] = "h"
        slot = Slot(rad=0, kol=0, retning="across", lengde=4)
        result = idx.kandidater(slot, grid.celler)
        # Alle resultatord skal starte med 'h'
        assert all(r[0] == "h" for r in result)
        assert "katt" not in result

    def test_tom_ordliste(self):
        idx = WordIndex([])
        assert idx._idx == {}

    def test_har_lengde(self):
        idx = WordIndex(["hund", "sol"])
        assert idx.har_lengde(4)
        assert idx.har_lengde(3)
        assert not idx.har_lengde(7)


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------
class TestGrid:
    def test_tom_grid_er_svart(self):
        grid = Grid(9)
        for rad in grid.celler:
            for celle in rad:
                assert celle == "#"

    def test_plasser_og_les_celler(self):
        grid = Grid(9)
        grid.plasser("hund", 4, 2, "across")
        assert grid.celler[4][2] == "h"
        assert grid.celler[4][3] == "u"
        assert grid.celler[4][4] == "n"
        assert grid.celler[4][5] == "d"

    def test_plasser_down(self):
        grid = Grid(9)
        grid.plasser("sol", 1, 3, "down")
        assert grid.celler[1][3] == "s"
        assert grid.celler[2][3] == "o"
        assert grid.celler[3][3] == "l"

    def test_fjern_sletter_bokstaver(self):
        grid = Grid(9)
        grid.plasser("hund", 4, 2, "across")
        grid.fjern("hund", 4, 2, "across")
        # Bokstaver uten kryss skal fjernes
        assert grid.celler[4][3] == "#"  # 'u' — ingen kryss
        assert grid.celler[4][4] == "#"  # 'n'

    def test_kan_plassere_krever_kryss(self):
        # Uten kryss returnerer kan_plassere False — dette er med vilje.
        # Det første ordet plasseres direkte via plasser(), ikke via kan_plassere().
        grid = Grid(9)
        assert not grid.kan_plassere("hund", 4, 0, "across")

    def test_kan_plassere_med_kryss(self):
        grid = Grid(9)
        grid.plasser("hund", 4, 2, "across")
        # "and" down: a=(3,4), n=(4,4) krysser 'n' i "hund", d=(5,4)
        assert grid.kan_plassere("and", 3, 4, "down")

    def test_kan_ikke_plassere_utenfor_grid(self):
        grid = Grid(9)
        assert not grid.kan_plassere("hund", 0, 7, "across")  # 7+4=11 > 9

    def test_kan_plassere_med_konflikt(self):
        grid = Grid(9)
        grid.plasser("katt", 4, 2, "across")
        # Prøv å plassere "hund" som krysser med feil bokstav (k != h)
        assert not grid.kan_plassere("hund", 4, 2, "across")

    def test_kan_plassere_med_korrekt_kryss(self):
        grid = Grid(9)
        grid.plasser("hund", 4, 2, "across")
        # "haus" down starter på rad 2, kol 2 — bokstav på (4,2) er 'h' = 'h' ✓
        assert grid.kan_plassere("aah", 2, 2, "down")  # a,a,h — h matcher


# ---------------------------------------------------------------------------
# Ledetrad-logikk
# ---------------------------------------------------------------------------
class TestLedetrad:
    def test_lag_ledetrad_synonym(self):
        from generator.ledetrad_generator import lag_ledetrad
        resultat = lag_ledetrad(
            tekst="hund",
            ordklasse="substantiv",
            synonymer=["bikkje", "hund", "kjæledyr"],
            kategorier=[],
        )
        assert resultat.kilde == "synonym"
        assert "4 bokstaver" in resultat.ledetrad

    def test_lag_ledetrad_egennavn_med_kategori(self):
        from generator.ledetrad_generator import lag_ledetrad
        resultat = lag_ledetrad(
            tekst="Oslo",
            ordklasse="egennavn",
            synonymer=[],
            kategorier=["Norske kommuner og byer"],
        )
        assert resultat.kilde == "kategori"
        assert "Norsk by" in resultat.ledetrad

    def test_lag_ledetrad_ordklasse_fallback(self):
        from generator.ledetrad_generator import lag_ledetrad
        resultat = lag_ledetrad(
            tekst="spring",
            ordklasse="verb",
            synonymer=[],
            kategorier=[],
        )
        assert resultat.kilde == "ordklasse"
        assert "Verb" in resultat.ledetrad

    def test_lag_ledetrad_nøytral_fallback(self):
        from generator.ledetrad_generator import lag_ledetrad
        resultat = lag_ledetrad(
            tekst="xyzqw",
            ordklasse=None,
            synonymer=[],
            kategorier=[],
        )
        assert resultat.kilde == "fallback"
        assert "Se opp" in resultat.ledetrad

    def test_velg_synonym_filtrerer_rot(self):
        from generator.ledetrad_generator import _velg_synonym
        # "abstraksjon" → filtrerer ut "abstrahering" (samme rot 'abst')
        syn = _velg_synonym("abstraksjon", ["abstrahering", "begrep", "konsept"])
        assert syn in ("begrep", "konsept")

    def test_velg_synonym_ingen_kandidater(self):
        from generator.ledetrad_generator import _velg_synonym
        assert _velg_synonym("ord", []) is None
        assert _velg_synonym("ord", ["ord"]) is None

    def test_velg_synonym_korteste_velges(self):
        from generator.ledetrad_generator import _velg_synonym
        # Synonymer er allerede sortert etter LENGTH(os.tekst) fra DB
        # _velg_synonym tar det første i lista etter filtering
        syn = _velg_synonym("stein", ["klipp", "berget", "fjell"])
        assert syn == "klipp"  # korteste (5 bokstaver)
