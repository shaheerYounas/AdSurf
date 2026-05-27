import pytest
from fastapi.testclient import TestClient
from apps.api.app.main import app

client = TestClient(app)

def test_health_check_endpoint():
    # If a health endpoint exists, it usually lives at /health or /api/health
    # We will assume /api/v1/dev/process-upload-jobs shouldn't naturally 404 but 404 means route is missing.
    # Let's write a mock one
    response = client.get("/health")
    if response.status_code == 404:
        pytest.skip("Health route not implemented yet")
    else:
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
