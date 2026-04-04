from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from .base import Base


class Word(Base):
    __tablename__ = "words"

    id = Column(Integer, primary_key=True)
    word = Column(String, nullable=False, unique=True, index=True)
    length = Column(Integer, nullable=False)
    frequency = Column(Float, default=0.0)
    category = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
