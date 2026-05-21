import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models.schemas import QueryRequest


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "LexEnergy Bolivia"


@pytest.mark.asyncio
async def test_query_endpoint_validation(client):
    response = await client.post(
        "/api/v1/query",
        json={"question": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_request_model():
    request = QueryRequest(
        question="What incentives exist for solar energy?",
        subsector="Solar",
    )
    assert request.question == "What incentives exist for solar energy?"
    assert request.subsector == "Solar"
    assert request.top_k is None


@pytest.mark.asyncio
async def test_query_request_with_all_fields():
    request = QueryRequest(
        question="Test question?",
        subsector="Solar",
        tipo_norma="Ley",
        vigente=True,
        top_k=10,
    )
    assert request.top_k == 10
    assert request.vigente is True
