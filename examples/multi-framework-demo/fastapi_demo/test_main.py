from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"route": "health-check", "status": "online"}

def test_public_route():
    response = client.get("/public/")
    assert response.status_code == 200
    assert response.json() == {"route": "public", "message": "This route is exempt from Adiuvare inspection."}

def test_protected_route():
    response = client.get("/protected/")
    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "protected"
    assert data["message"] == "This stricter route passed Adiuvare inspection."
    assert "verdict" in data
    assert "score" in data

def test_review_route():
    response = client.post("/review/", json={"message": "normal search text"})
    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "review"
    assert data["message"] == "Payload review route reached the FastAPI view."
    assert data["received"] == {"message": "normal search text"}
    assert "verdict" in data

def test_hard_stop_route():
    response = client.post("/hard-stop/", json={"comment": "<script>alert(1)</script> UNION SELECT password FROM users"})
    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "hard-stop"
    assert data["message"] == "If Adiuvare allows the request, this fallback response is returned."
    assert "verdict" in data
    assert "score" in data

def test_explicit_exempt_route():
    response = client.get("/api/v1/explicit-exempt/")
    assert response.status_code == 200
    assert response.json() == {"route": "explicit-exempt", "message": "Bypassed via direct per-endpoint decorator."}

def test_advanced_policy_route():
    response = client.post("/api/v1/advanced-policy/", json={"data_stream": "override_core_state", "client_entropy": 0.97})
    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "advanced-payload-review"
    assert "final_adiuvare_verdict" in data
    assert "final_adiuvare_score" in data

def test_global_policy_override_route():
    response = client.get("/api/v1/global-policy-override/")
    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "global-policy-override"
    assert data["message"] == "Overrode global policy using @guard.policy decorator."
    assert "verdict" in data
    assert "score" in data

def test_global_protect_override_route():
    response = client.get("/api/v1/global-protect-override/")
    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "global-protect-override"
    assert data["message"] == "Overrode global protect rule using @guard.protect decorator."
    assert "verdict" in data
    assert "score" in data
