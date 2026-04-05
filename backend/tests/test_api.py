"""
Integrasjonstester for FastAPI-endepunktene.
Bruker TestClient med mockede DB-sessions — ingen ekte database nødvendig.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.database import get_db
from app.models.kryssord import Kryssord, KryssordStatistikk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _lag_kryssord(**kwargs) -> Kryssord:
    defaults = dict(
        id=uuid.uuid4(),
        tittel="Testkryssord",
        vanskelighetsgrad="lett",
        grid_storrelse=9,
        grid_json={"celler": [["a", "#"], ["#", "b"]], "storrelse": 2},
        ledetrad_json={"across": {}, "down": {}},
        opprettet_dato=datetime.now(timezone.utc),
        publisert=True,
        statistikk=None,
    )
    defaults.update(kwargs)
    k = MagicMock(spec=Kryssord)
    for key, val in defaults.items():
        setattr(k, key, val)
    return k


def _mock_db(scalar_result=None, scalars_result=None, scalar_for_count=None):
    db = MagicMock()
    db.scalar.return_value = scalar_result
    if scalars_result is not None:
        db.scalars.return_value.all.return_value = scalars_result
    return db


# ---------------------------------------------------------------------------
# Klient-fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tester
# ---------------------------------------------------------------------------
class TestHelse:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestDagligKryssord:
    def test_ingen_kryssord_gir_404(self, client):
        db = _mock_db(scalar_result=None)

        def override():
            yield db

        app.dependency_overrides[get_db] = override
        resp = client.get("/api/kryssord/daglig")
        app.dependency_overrides.clear()
        assert resp.status_code == 404

    def test_returnerer_publisert_kryssord(self, client):
        k = _lag_kryssord()
        db = _mock_db(scalar_result=k)

        def override():
            yield db

        app.dependency_overrides[get_db] = override
        resp = client.get("/api/kryssord/daglig")
        app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["tittel"] == "Testkryssord"


class TestHentKryssord:
    def test_ukjent_id_gir_404(self, client):
        db = MagicMock()
        db.get.return_value = None

        def override():
            yield db

        app.dependency_overrides[get_db] = override
        resp = client.get(f"/api/kryssord/{uuid.uuid4()}")
        app.dependency_overrides.clear()
        assert resp.status_code == 404

    def test_henter_publisert_kryssord(self, client):
        k = _lag_kryssord()
        db = MagicMock()
        db.get.return_value = k

        def override():
            yield db

        app.dependency_overrides[get_db] = override
        resp = client.get(f"/api/kryssord/{k.id}")
        app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["tittel"] == "Testkryssord"


class TestArkiv:
    def test_tomt_arkiv(self, client):
        db = MagicMock()
        db.scalar.return_value = 0
        db.scalars.return_value.all.return_value = []

        def override():
            yield db

        app.dependency_overrides[get_db] = override
        resp = client.get("/api/kryssord/arkiv")
        app.dependency_overrides.clear()
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalt"] == 0
        assert data["kryssord"] == []


class TestGenerer:
    def test_manglende_admin_key_gir_403(self, client):
        resp = client.post("/api/kryssord/generer", json={"storrelse": 9})
        assert resp.status_code == 403

    def test_feil_admin_key_gir_403(self, client):
        resp = client.post(
            "/api/kryssord/generer",
            json={"storrelse": 9},
            headers={"X-Admin-Key": "feil-nokkel"},
        )
        assert resp.status_code == 403
