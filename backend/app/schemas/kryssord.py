from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StatistikkUt(BaseModel):
    antall_fullfort: int
    antall_forsok:   int

    model_config = ConfigDict(from_attributes=True)


class KryssordUt(BaseModel):
    id:                UUID
    tittel:            str
    vanskelighetsgrad: str
    grid_storrelse:    int
    grid_json:         dict
    ledetrad_json:     dict
    opprettet_dato:    datetime
    publisert:         bool
    statistikk:        StatistikkUt | None = None

    model_config = ConfigDict(from_attributes=True)


class KryssordListeElement(BaseModel):
    id:                UUID
    tittel:            str
    vanskelighetsgrad: str
    grid_storrelse:    int
    opprettet_dato:    datetime
    antall_fullfort:   int = 0

    model_config = ConfigDict(from_attributes=True)


class KryssordArkiv(BaseModel):
    totalt:     int
    side:       int
    per_side:   int
    kryssord:   list[KryssordListeElement]


class GenererRequest(BaseModel):
    storrelse:  int = Field(default=13, ge=5, le=21)
    publiser:   bool = Field(default=False)
    tittel:     str | None = None


class GenererRespons(BaseModel):
    id:             UUID
    tittel:         str
    grid_storrelse: int
    antall_ord:     int
    publisert:      bool
