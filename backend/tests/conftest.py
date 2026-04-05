"""
Sett opp testmiljø med minimale environment-variabler
slik at app kan importeres uten .env-fil.
"""
import os

# Sett disse FØR app importeres
# Fake URL — engine er lazy, kobler ikke til før en faktisk query.
# get_db overrides i test_api.py bruker SQLite i stedet.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("API_SECRET_KEY", "test-secret")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
