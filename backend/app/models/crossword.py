from sqlalchemy import Column, Integer, String, JSON, DateTime
from sqlalchemy.sql import func
from .base import Base


class Crossword(Base):
    __tablename__ = "crosswords"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    grid = Column(JSON, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Clue(Base):
    __tablename__ = "clues"

    id = Column(Integer, primary_key=True)
    crossword_id = Column(Integer, nullable=False, index=True)
    word = Column(String, nullable=False)
    clue_text = Column(String, nullable=False)
    direction = Column(String, nullable=False)  # "across" or "down"
    position = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
