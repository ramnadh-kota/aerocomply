def test_liveness(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_checks_database(client):
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["database"] == "reachable"
