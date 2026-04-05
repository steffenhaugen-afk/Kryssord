from .base import Base
from .kryssord import Kryssord, KryssordStatistikk
from .ord import Kategori, Ord, OrdKategori, Synonym

__all__ = [
    "Base",
    "Ord", "Synonym", "Kategori", "OrdKategori",
    "Kryssord", "KryssordStatistikk",
]
