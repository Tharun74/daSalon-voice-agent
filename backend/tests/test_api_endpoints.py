from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ["ok", "degraded"]
    assert "connected" in data["mongodb"]


def test_list_salons_endpoint():
    resp = client.get("/salons")
    assert resp.status_code == 200
    salons = resp.json()
    assert len(salons) == 3
    slugs = [s["_id"] for s in salons]
    assert "glow-studio" in slugs
    assert "serenity-spa" in slugs
    assert "gentlemans-cut" in slugs


def test_salon_detail_endpoint():
    resp = client.get("/salons/glow-studio")
    assert resp.status_code == 200
    data = resp.json()
    assert data["salon"]["name"] == "Glow Studio"
    assert len(data["services"]) >= 6
    assert len(data["staff"]) >= 2
    assert len(data["offers"]) >= 1


def test_salon_not_found():
    resp = client.get("/salons/non-existent-salon")
    assert resp.status_code == 404


def test_admin_endpoints():
    # Admin conversations
    resp = client.get("/admin/conversations?salon_id=glow-studio")
    assert resp.status_code == 200

    # Admin handoffs
    resp = client.get("/admin/handoffs?salon_id=glow-studio")
    assert resp.status_code == 200

    # Admin unanswered questions
    resp = client.get("/admin/unanswered-questions?salon_id=glow-studio")
    assert resp.status_code == 200

    # Admin appointments
    resp = client.get("/admin/appointments?salon_id=glow-studio")
    assert resp.status_code == 200
