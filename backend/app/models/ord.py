from sqlalchemy import Column, Computed, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import relationship

from .base import Base


class Ord(Base):
    __tablename__ = "ord"

    id            = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    tekst         = Column(Text, nullable=False, unique=True)
    ordklasse     = Column(Text)
    bokstavlengde = Column(Computed("length(tekst)", persisted=True))
    frekvens      = Column(Numeric(10, 6), default=0.0)
    opprettet_dato = Column(TIMESTAMP(timezone=True), server_default=func.now())

    synonymer_som_ord     = relationship("Synonym", foreign_keys="Synonym.ord_id",     back_populates="ord",     lazy="select")
    synonymer_som_synonym = relationship("Synonym", foreign_keys="Synonym.synonym_id", back_populates="synonym", lazy="select")
    kategorier            = relationship("Kategori", secondary="ord_kategorier",        back_populates="ord")


class Synonym(Base):
    __tablename__ = "synonymer"

    id            = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    ord_id        = Column(UUID(as_uuid=True), ForeignKey("ord.id", ondelete="CASCADE"), nullable=False)
    synonym_id    = Column(UUID(as_uuid=True), ForeignKey("ord.id", ondelete="CASCADE"), nullable=False)
    relasjon_type = Column(Text, nullable=False, default="synonym")
    kilde         = Column(Text)

    ord     = relationship("Ord", foreign_keys=[ord_id],     back_populates="synonymer_som_ord")
    synonym = relationship("Ord", foreign_keys=[synonym_id], back_populates="synonymer_som_synonym")


class Kategori(Base):
    __tablename__ = "kategorier"

    id          = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    navn        = Column(Text, nullable=False, unique=True)
    beskrivelse = Column(Text)

    ord = relationship("Ord", secondary="ord_kategorier", back_populates="kategorier")


class OrdKategori(Base):
    __tablename__ = "ord_kategorier"

    ord_id      = Column(UUID(as_uuid=True), ForeignKey("ord.id",        ondelete="CASCADE"), primary_key=True)
    kategori_id = Column(UUID(as_uuid=True), ForeignKey("kategorier.id", ondelete="CASCADE"), primary_key=True)
