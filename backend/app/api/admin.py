"""
Admin API – kryssord-generering, kvalitetssikring og ordbank.
Alle endepunkter krever X-Admin-Key header.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

import psycopg2
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.kryssord import Kryssord
from ..schemas.kryssord import KryssordUt

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

TEMA_KATEGORIER: dict[str, list[str]] = {
    "geografi":  ["Norske kommuner og byer", "Norske fjell", "Europeiske land", "Verdens land", "Verdens byer"],
    "politikk":  ["Norske politikere"],
    "natur":     ["Norske fjell"],
    "sport":     [],
    "generell":  [],
}


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------
def _verify(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(403, "Ugyldig eller manglende X-Admin-Key")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AdminKryssordElement(BaseModel):
    id:                UUID
    tittel:            str
    vanskelighetsgrad: str
    grid_storrelse:    int
    opprettet_dato:    str
    publisert:         bool
    godkjent:          bool
    antall_ord:        int


class AdminKryssordListe(BaseModel):
    totalt:   int
    kryssord: list[AdminKryssordElement]


class GenererAdminRequest(BaseModel):
    storrelse:  int = Field(default=13, ge=9, le=17)
    tema:       str = Field(default="generell")
    tvang_ord:  list[str] = Field(default_factory=list)


class OppdaterLedetradRequest(BaseModel):
    retning:  str
    nr:       str
    ledetrad: str


class OppdaterStatusRequest(BaseModel):
    godkjent:  bool | None = None
    publisert: bool | None = None
    tittel:    str | None = None


class OrdLedetradInfo(BaseModel):
    tekst:        str
    ordklasse:    str | None
    bokstavlengde: int
    kryssordkongen: list[str]
    synonymer:     list[str]
    kategorier:    list[str]


class LeggTilLedetradRequest(BaseModel):
    ledetrad: str = Field(min_length=2)


# ---------------------------------------------------------------------------
# DEL 1 – Kryssord-liste og status
# ---------------------------------------------------------------------------
@router.get("/kryssord", response_model=AdminKryssordListe, dependencies=[Depends(_verify)])
def admin_kryssord_liste(db: Session = Depends(get_db)) -> AdminKryssordListe:
    rader = db.scalars(
        select(Kryssord).order_by(Kryssord.opprettet_dato.desc())
    ).all()

    elementer = []
    for k in rader:
        lj = k.ledetrad_json or {}
        antall = len(lj.get("across", {})) + len(lj.get("down", {}))
        elementer.append(AdminKryssordElement(
            id=k.id,
            tittel=k.tittel,
            vanskelighetsgrad=k.vanskelighetsgrad,
            grid_storrelse=k.grid_storrelse,
            opprettet_dato=k.opprettet_dato.isoformat(),
            publisert=k.publisert,
            godkjent=k.godkjent,
            antall_ord=antall,
        ))

    return AdminKryssordListe(totalt=len(elementer), kryssord=elementer)


@router.get("/kryssord/{kryssord_id}", response_model=KryssordUt, dependencies=[Depends(_verify)])
def admin_hent_kryssord(kryssord_id: UUID, db: Session = Depends(get_db)) -> KryssordUt:
    k = db.get(Kryssord, kryssord_id)
    if k is None:
        raise HTTPException(404, "Kryssord ikke funnet")
    return KryssordUt(
        id=k.id, tittel=k.tittel, vanskelighetsgrad=k.vanskelighetsgrad,
        grid_storrelse=k.grid_storrelse, grid_json=k.grid_json,
        ledetrad_json=k.ledetrad_json, opprettet_dato=k.opprettet_dato,
        publisert=k.publisert, statistikk=k.statistikk,
    )


@router.patch("/kryssord/{kryssord_id}/status", dependencies=[Depends(_verify)])
def oppdater_status(
    kryssord_id: UUID,
    body: OppdaterStatusRequest,
    db: Session = Depends(get_db),
) -> dict:
    k = db.get(Kryssord, kryssord_id)
    if k is None:
        raise HTTPException(404, "Kryssord ikke funnet")
    if body.godkjent is not None:
        k.godkjent = body.godkjent
    if body.publisert is not None:
        k.publisert = body.publisert
    if body.tittel is not None:
        k.tittel = body.tittel
    db.commit()
    return {"ok": True, "godkjent": k.godkjent, "publisert": k.publisert}


@router.patch("/kryssord/{kryssord_id}/ledetrad", dependencies=[Depends(_verify)])
def oppdater_ledetrad(
    kryssord_id: UUID,
    body: OppdaterLedetradRequest,
    db: Session = Depends(get_db),
) -> dict:
    k = db.get(Kryssord, kryssord_id)
    if k is None:
        raise HTTPException(404, "Kryssord ikke funnet")

    lj = dict(k.ledetrad_json or {})
    retning = lj.get(body.retning, {})
    if body.nr not in retning:
        raise HTTPException(404, f"Ledetråd {body.retning}/{body.nr} ikke funnet")

    retning[body.nr] = {**retning[body.nr], "ledetrad": body.ledetrad, "kilde": "manuell"}
    lj[body.retning] = retning
    k.ledetrad_json = lj
    db.commit()
    return {"ok": True}


@router.delete("/kryssord/{kryssord_id}", dependencies=[Depends(_verify)])
def slett_kryssord(kryssord_id: UUID, db: Session = Depends(get_db)) -> dict:
    k = db.get(Kryssord, kryssord_id)
    if k is None:
        raise HTTPException(404, "Kryssord ikke funnet")
    db.delete(k)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# DEL 1 – Generering
# ---------------------------------------------------------------------------
def _vanskelighetsgrad(storrelse: int) -> str:
    return {9: "lett", 13: "middels", 17: "vanskelig"}.get(storrelse, "middels")


def _hent_tema_ord(database_url: str, kategorier: list[str], min_len: int, max_len: int, antall: int) -> list[str]:
    if not kategorier:
        return []
    pk = ",".join(["%s"] * len(kategorier))
    sql = f"""
        SELECT o.tekst FROM ord o
        JOIN ord_kategorier ok ON ok.ord_id = o.id
        JOIN kategorier k ON k.id = ok.kategori_id
        WHERE k.navn IN ({pk})
          AND o.bokstavlengde BETWEEN %s AND %s
          AND o.har_bindestrek = false
          AND o.har_mellomrom  = false
          AND o.tekst ~ '^[a-zæøå]+$'
          AND (
            EXISTS (SELECT 1 FROM kryssord_ledetrad_par klp WHERE UPPER(klp.svar) = UPPER(o.tekst))
            OR EXISTS (SELECT 1 FROM synonymer s WHERE s.ord_id = o.id AND s.relasjon_type = 'synonym')
          )
        ORDER BY random()
        LIMIT %s
    """
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (*kategorier, min_len, max_len, antall))
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/kryssord/generer", response_model=KryssordUt, dependencies=[Depends(_verify)])
def admin_generer(body: GenererAdminRequest, db: Session = Depends(get_db)) -> KryssordUt:
    from ...generator.kryssord_generator import (
        KryssordGenerator, hent_ord_fra_db, lagre_kryssord,
        VANSKELIGHET, GRID_MAKS_ORDLENGDE,
    )
    from ...generator.ledetrad_generator import LedetradGenerator

    vanskelighet = _vanskelighetsgrad(body.storrelse)
    cfg = VANSKELIGHET[vanskelighet]
    min_len = max(cfg["min_len"], 3)
    max_len = min(cfg["max_len"], GRID_MAKS_ORDLENGDE[body.storrelse])

    # Hent ordinær ordpool
    ord_liste = hent_ord_fra_db(settings.database_url, vanskelighet, body.storrelse)

    # Blend inn tema-ord (opp til 30% av pool_size)
    tema_kat = TEMA_KATEGORIER.get(body.tema, [])
    if tema_kat:
        tema_antall = cfg["pool_size"] // 3
        tema_ord = _hent_tema_ord(settings.database_url, tema_kat, min_len, max_len, tema_antall)
        ord_liste = tema_ord + ord_liste

    # Legg tvang_ord øverst (ingen garanti, men øker sannsynlighet)
    tvang = [o.lower().strip() for o in body.tvang_ord if o.strip()]
    if tvang:
        ord_liste = tvang + [o for o in ord_liste if o not in tvang]

    if len(ord_liste) < 20:
        raise HTTPException(500, "For få ord i ordbanken for denne konfigurasjonen")

    generator = KryssordGenerator(ord_liste, body.storrelse, vanskelighet, maks_tid=60.0)
    resultat = generator.generer()
    if resultat is None:
        raise HTTPException(500, "Klarte ikke generere kryssord innen tidsgrensen")

    tema_str = f" ({body.tema})" if body.tema != "generell" else ""
    tittel = f"Utkast {body.storrelse}×{body.storrelse}{tema_str}"
    kryssord_id = lagre_kryssord(
        settings.database_url, resultat, body.storrelse, vanskelighet,
        tittel=tittel, publiser=False,
    )

    # Generer ledetråder
    try:
        LedetradGenerator(settings.database_url).oppdater_kryssord_i_db(kryssord_id)
    except Exception as e:
        log.warning("LedetradGenerator feilet: %s", e)

    k = db.get(Kryssord, kryssord_id)
    db.refresh(k)
    return KryssordUt(
        id=k.id, tittel=k.tittel, vanskelighetsgrad=k.vanskelighetsgrad,
        grid_storrelse=k.grid_storrelse, grid_json=k.grid_json,
        ledetrad_json=k.ledetrad_json, opprettet_dato=k.opprettet_dato,
        publisert=k.publisert, statistikk=k.statistikk,
    )


# ---------------------------------------------------------------------------
# DEL 3 – Ordbank
# ---------------------------------------------------------------------------
@router.get("/ord", dependencies=[Depends(_verify)])
def admin_ord_sok(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
) -> dict:
    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor() as cur:
            # Finn ord
            cur.execute(
                """
                SELECT o.id::text, o.tekst, o.ordklasse, o.bokstavlengde
                FROM ord o
                WHERE o.tekst ILIKE %s
                ORDER BY o.bokstavlengde, o.tekst
                LIMIT 50
                """,
                (f"%{q}%",),
            )
            ord_rader = cur.fetchall()

            if not ord_rader:
                return {"totalt": 0, "resultater": []}

            tekster = [r[1] for r in ord_rader]
            placeholders = ",".join(["%s"] * len(tekster))

            # Kryssordkongen-ledetråder
            cur.execute(
                f"""
                SELECT LOWER(klp.svar), klp.ledetrad
                FROM kryssord_ledetrad_par klp
                WHERE LOWER(klp.svar) IN ({placeholders})
                ORDER BY klp.ledetrad
                """,
                [t.lower() for t in tekster],
            )
            kk_map: dict[str, list[str]] = {}
            for svar, ledetrad in cur.fetchall():
                kk_map.setdefault(svar, []).append(ledetrad)

            # Synonymer
            cur.execute(
                f"""
                SELECT o.tekst, os.tekst
                FROM synonymer s
                JOIN ord o  ON o.id  = s.ord_id
                JOIN ord os ON os.id = s.synonym_id
                WHERE o.tekst IN ({placeholders})
                  AND s.relasjon_type = 'synonym'
                ORDER BY LENGTH(os.tekst)
                """,
                tekster,
            )
            syn_map: dict[str, list[str]] = {}
            for tekst, syn in cur.fetchall():
                syn_map.setdefault(tekst, []).append(syn)

            # Kategorier
            cur.execute(
                f"""
                SELECT o.tekst, k.navn
                FROM ord_kategorier ok
                JOIN ord o        ON o.id = ok.ord_id
                JOIN kategorier k ON k.id = ok.kategori_id
                WHERE o.tekst IN ({placeholders})
                """,
                tekster,
            )
            kat_map: dict[str, list[str]] = {}
            for tekst, kat in cur.fetchall():
                kat_map.setdefault(tekst, []).append(kat)

    finally:
        conn.close()

    resultater = []
    for ord_id, tekst, ordklasse, bokstavlengde in ord_rader:
        resultater.append({
            "id": ord_id,
            "tekst": tekst,
            "ordklasse": ordklasse,
            "bokstavlengde": bokstavlengde,
            "kryssordkongen": kk_map.get(tekst.lower(), [])[:10],
            "synonymer": syn_map.get(tekst, [])[:10],
            "kategorier": kat_map.get(tekst, []),
        })

    return {"totalt": len(resultater), "resultater": resultater}


@router.post("/ord/{tekst}/ledetrad", dependencies=[Depends(_verify)])
def legg_til_ledetrad(tekst: str, body: LeggTilLedetradRequest) -> dict:
    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM ord WHERE LOWER(tekst) = LOWER(%s)", (tekst,))
            ord_rad = cur.fetchone()
            if not ord_rad:
                raise HTTPException(404, f"Ord '{tekst}' ikke funnet")

            cur.execute(
                """
                INSERT INTO kryssord_ledetrad_par (ledetrad, svar, kilde)
                VALUES (%s, %s, 'manuell')
                ON CONFLICT DO NOTHING
                """,
                (body.ledetrad, tekst.upper()),
            )
            conn.commit()
    finally:
        conn.close()
    return {"ok": True}
