"""API endpoint tests."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.anyio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.anyio
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data


@pytest.mark.anyio
async def test_chat_endpoint_validation(client: AsyncClient):
    """Test chat endpoint input validation."""
    # Empty message should fail
    response = await client.post(
        "/api/v1/chat",
        json={"message": "", "language": "en"}
    )
    assert response.status_code == 422

    # Invalid language should fail
    response = await client.post(
        "/api/v1/chat",
        json={"message": "test", "language": "invalid"}
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_document_list_endpoint(client: AsyncClient):
    """Test document list endpoint."""
    response = await client.get("/api/v1/documents")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
    assert "total" in data


@pytest.mark.anyio
async def test_source_search_requires_query(client: AsyncClient):
    """Test source search requires query parameter."""
    response = await client.get("/api/v1/sources/search")
    assert response.status_code == 422
