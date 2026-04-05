from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.kryssord import Kryssord, KryssordStatistikk
from ..schemas.kryssord import (
    GenererRequest,
    GenererRespons,
    KryssordArkiv,
    KryssordListeElement,
    KryssordUt,
)

router = APIRouter(prefix="/api/kryssord", tags=["kryssord"])

PER_SIDE = 20


def _kryssord_ut(k: Kryssord) -> KryssordUt:
    return KryssordUt(
        id=k.id,
        tittel=k.tittel,
        vanskelighetsgrad=k.vanskelighetsgrad,
        grid_storrelse=k.grid_storrelse,
        grid_json=k.grid_json,
        ledetrad_json=k.ledetrad_json,
        opprettet_dato=k.opprettet_dato,
        publisert=k.publisert,
        statistikk=k.statistikk,
    )


@router.get("/daglig", response_model=KryssordUt, summary="Dagens kryssord")
def daglig_kryssord(db: Session = Depends(get_db)) -> KryssordUt:
    """
    Returnerer det siste publiserte kryssordet opprettet i dag.
    Faller tilbake på det nyeste publiserte kryssordet totalt.
    """
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)

    k = db.scalar(
        select(Kryssord)
        .where(Kryssord.publisert == True)  # noqa: E712
        .where(Kryssord.opprettet_dato >= today_start)
        .order_by(Kryssord.opprettet_dato.desc())
        .limit(1)
    )

    if k is None:
        k = db.scalar(
            select(Kryssord)
            .where(Kryssord.publisert == True)  # noqa: E712
            .order_by(Kryssord.opprettet_dato.desc())
            .limit(1)
        )

    if k is None:
        raise HTTPException(status_code=404, detail="Ingen publiserte kryssord funnet")

    return _kryssord_ut(k)


@router.get("/arkiv", response_model=KryssordArkiv, summary="Liste over publiserte kryssord")
def kryssord_arkiv(
    side:      int        = Query(1, ge=1),
    storrelse: int | None = Query(None, ge=5, le=21, description="Filtrer på grid-størrelse"),
    db:        Session    = Depends(get_db),
) -> KryssordArkiv:
    q = (
        select(Kryssord)
        .where(Kryssord.publisert == True)  # noqa: E712
    )
    if storrelse:
        q = q.where(Kryssord.grid_storrelse == storrelse)

    totalt = db.scalar(select(func.count()).select_from(q.subquery()))
    rader  = db.scalars(
        q.order_by(Kryssord.opprettet_dato.desc())
        .offset((side - 1) * PER_SIDE)
        .limit(PER_SIDE)
    ).all()

    elementer = []
    for k in rader:
        fullfort = k.statistikk.antall_fullfort if k.statistikk else 0
        elementer.append(
            KryssordListeElement(
                id=k.id,
                tittel=k.tittel,
                vanskelighetsgrad=k.vanskelighetsgrad,
                grid_storrelse=k.grid_storrelse,
                opprettet_dato=k.opprettet_dato,
                antall_fullfort=fullfort,
            )
        )

    return KryssordArkiv(
        totalt=totalt or 0,
        side=side,
        per_side=PER_SIDE,
        kryssord=elementer,
    )


@router.get("/{kryssord_id}", response_model=KryssordUt, summary="Hent spesifikt kryssord")
def hent_kryssord(
    kryssord_id: UUID,
    db: Session = Depends(get_db),
) -> KryssordUt:
    k = db.get(Kryssord, kryssord_id)
    if k is None or not k.publisert:
        raise HTTPException(status_code=404, detail="Kryssord ikke funnet")
    return _kryssord_ut(k)


@router.post("/generer", response_model=GenererRespons, summary="Generer nytt kryssord (admin)")
def generer_kryssord(
    body:        GenererRequest,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
    db:          Session    = Depends(get_db),
) -> GenererRespons:
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Ugyldig eller manglende X-Admin-Key")

    from ...generator import generer_og_lagre

    try:
        info = generer_og_lagre(
            database_url=settings.database_url,
            storrelse=body.storrelse,
            vanskelighetsgrad=_vanskelighetsgrad(body.storrelse),
            publiser=body.publiser,
            tittel=body.tittel,
            maks_tid=20.0,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    k = db.get(Kryssord, info["id"])
    if k is None:
        raise HTTPException(status_code=500, detail="Kryssord ikke funnet etter generering")

    return GenererRespons(
        id=k.id,
        tittel=k.tittel,
        grid_storrelse=k.grid_storrelse,
        antall_ord=info["antall_ord"],
        publisert=k.publisert,
    )


def _vanskelighetsgrad(storrelse: int) -> str:
    return {9: "lett", 13: "middels", 17: "vanskelig"}.get(storrelse, "middels")
