from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import relationship

from .base import Base


class Kryssord(Base):
    __tablename__ = "kryssord"

    id                = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    tittel            = Column(Text, nullable=False)
    vanskelighetsgrad = Column(String(20), nullable=False, default="middels")
    grid_storrelse    = Column(Integer, nullable=False)
    grid_json         = Column(JSONB, nullable=False, default={})
    ledetrad_json     = Column(JSONB, nullable=False, default={})
    opprettet_dato    = Column(TIMESTAMP(timezone=True), server_default=func.now())
    publisert         = Column(Boolean, nullable=False, default=False)

    statistikk = relationship("KryssordStatistikk", back_populates="kryssord", uselist=False)


class KryssordStatistikk(Base):
    __tablename__ = "kryssord_statistikk"

    id               = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    kryssord_id      = Column(UUID(as_uuid=True), ForeignKey("kryssord.id", ondelete="CASCADE"), nullable=False, unique=True)
    antall_fullfort  = Column(Integer, nullable=False, default=0)
    antall_forsok    = Column(Integer, nullable=False, default=0)

    kryssord = relationship("Kryssord", back_populates="statistikk")
