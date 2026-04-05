from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.ord import Kategori, Ord, OrdKategori, Synonym
from ..schemas.ord import OrdSokResultat, OrdUt, SynonymUt, SynonymerUt

router = APIRouter(prefix="/api", tags=["ord"])

PER_SIDE = 50


@router.get("/ord", response_model=OrdSokResultat, summary="Søk i ordbanken")
def sok_ord(
    lengde:    int | None = Query(None, ge=1, le=30, description="Eksakt bokstavlengde"),
    min_lengde: int | None = Query(None, ge=1, le=30),
    max_lengde: int | None = Query(None, ge=1, le=30),
    kategori:  str | None = Query(None, description="Kategorinavn, f.eks. 'geografi'"),
    ordklasse: str | None = Query(None, description="substantiv, verb, adjektiv, egennavn"),
    side:      int        = Query(1, ge=1),
    db:        Session    = Depends(get_db),
) -> OrdSokResultat:
    q = select(Ord)

    if lengde is not None:
        q = q.where(Ord.bokstavlengde == lengde)
    else:
        if min_lengde is not None:
            q = q.where(Ord.bokstavlengde >= min_lengde)
        if max_lengde is not None:
            q = q.where(Ord.bokstavlengde <= max_lengde)

    if ordklasse:
        q = q.where(Ord.ordklasse == ordklasse.lower())

    if kategori:
        kat = db.scalar(
            select(Kategori).where(
                func.lower(Kategori.navn).contains(kategori.lower())
            )
        )
        if kat is None:
            raise HTTPException(status_code=404, detail=f"Kategori '{kategori}' ikke funnet")
        q = q.join(OrdKategori, OrdKategori.ord_id == Ord.id).where(
            OrdKategori.kategori_id == kat.id
        )

    totalt = db.scalar(select(func.count()).select_from(q.subquery()))
    rader  = db.scalars(q.order_by(Ord.tekst).offset((side - 1) * PER_SIDE).limit(PER_SIDE)).all()

    return OrdSokResultat(
        totalt=totalt or 0,
        side=side,
        per_side=PER_SIDE,
        resultater=[
            OrdUt(
                id=o.id,
                tekst=o.tekst,
                ordklasse=o.ordklasse,
                bokstavlengde=o.bokstavlengde,
                frekvens=float(o.frekvens or 0),
            )
            for o in rader
        ],
    )


@router.get("/synonymer/{ord}", response_model=SynonymerUt, summary="Hent synonymer for et ord")
def hent_synonymer(
    ord: str,
    db: Session = Depends(get_db),
) -> SynonymerUt:
    base = db.scalar(select(Ord).where(Ord.tekst == ord.lower()))
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ordet '{ord}' finnes ikke i databasen")

    rader = db.execute(
        select(Ord, Synonym.relasjon_type, Synonym.kilde)
        .join(Synonym, Synonym.synonym_id == Ord.id)
        .where(Synonym.ord_id == base.id)
        .order_by(Ord.tekst)
    ).all()

    return SynonymerUt(
        ord=base.tekst,
        synonymer=[
            SynonymUt(
                id=o.id,
                tekst=o.tekst,
                ordklasse=o.ordklasse,
                relasjon_type=relasjon_type,
                kilde=kilde,
            )
            for o, relasjon_type, kilde in rader
        ],
    )
