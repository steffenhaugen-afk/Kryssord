"""
Kjør dette skriptet for å opprette alle databasetabeller.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from sqlalchemy import create_engine, inspect, text
from app.models.base import Base
from app.models.word import Word
from app.models.crossword import Crossword, Clue

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Feil: DATABASE_URL mangler i .env")
    sys.exit(1)

print(f"Kobler til: {DATABASE_URL.split('@')[-1]}")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
print("Tilkobling OK")

Base.metadata.create_all(engine)

inspector = inspect(engine)
tables = inspector.get_table_names()
print(f"\nOpprettede tabeller: {', '.join(tables)}")
for table in tables:
    cols = [c["name"] for c in inspector.get_columns(table)]
    print(f"  {table}: {', '.join(cols)}")

print("\nMigrasjon fullfort.")
