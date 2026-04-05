from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OrdUt(BaseModel):
    id:            UUID
    tekst:         str
    ordklasse:     str | None
    bokstavlengde: int
    frekvens:      float

    model_config = ConfigDict(from_attributes=True)


class OrdSokResultat(BaseModel):
    totalt:    int
    side:      int
    per_side:  int
    resultater: list[OrdUt]


class SynonymUt(BaseModel):
    id:           UUID
    tekst:        str
    ordklasse:    str | None
    relasjon_type: str
    kilde:        str | None

    model_config = ConfigDict(from_attributes=True)


class SynonymerUt(BaseModel):
    ord:       str
    synonymer: list[SynonymUt]
