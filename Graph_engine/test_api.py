from fastapi.testclient import TestClient
from cge.api.server import app


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_and_query_node():
    r1 = client.post(
        "/nodes",
        json={"label": "payment_gateway", "confidence": 0.95, "source_type": "human_verified"},
    )
    assert r1.status_code == 201
    nid = r1.json()["id"]

    r2 = client.get("/query", params={"q": "payment", "exact": False, "min_confidence": 0.9})
    assert r2.status_code == 200
    data = r2.json()
    assert len(data) == 1
    assert data[0]["node_id"] == nid
