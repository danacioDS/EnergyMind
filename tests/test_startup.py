"""
Smoke tests for the ResourceManager warmup and startup flow.
These tests mock heavy ML/infra loading so they run fast (< 2s).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestResourceManager:
    """Unit tests for ResourceManager — no real ML or Qdrant needed."""

    @pytest.mark.asyncio
    async def test_warmup_sets_ready_event(self):
        """After warmup(), is_ready is True and wait_ready() returns."""
        from core.runtime.resource_manager import ResourceManager

        rm = ResourceManager()

        with patch.object(rm, "_load_embedder", return_value=None), \
             patch.object(rm, "_load_qdrant", new_callable=AsyncMock):
            await rm.warmup()

        assert rm.is_ready is True
        await rm.wait_ready(timeout=1.0)   # must not raise

    @pytest.mark.asyncio
    async def test_warmup_failure_unblocks_waiters(self):
        """If warmup fails, wait_ready() raises RuntimeError instead of hanging."""
        from core.runtime.resource_manager import ResourceManager

        rm = ResourceManager()

        async def failing_qdrant():
            raise ConnectionError("Qdrant unreachable")

        with patch.object(rm, "_load_embedder", return_value=None), \
             patch.object(rm, "_load_qdrant", side_effect=failing_qdrant):
            with pytest.raises(Exception):
                await rm.warmup()

        # wait_ready must raise, not hang
        with pytest.raises(RuntimeError, match="warmup failed"):
            await rm.wait_ready(timeout=1.0)

    @pytest.mark.asyncio
    async def test_wait_ready_timeout(self):
        """wait_ready() raises RuntimeError if warmup never completes."""
        from core.runtime.resource_manager import ResourceManager

        rm = ResourceManager()
        # Don't call warmup — event never set

        with pytest.raises(RuntimeError, match="timed out"):
            await rm.wait_ready(timeout=0.1)

    def test_embedder_raises_before_warmup(self):
        """Accessing embedder() before warmup raises RuntimeError."""
        from core.runtime.resource_manager import ResourceManager

        rm = ResourceManager()
        with pytest.raises(RuntimeError, match="not loaded"):
            rm.embedder()

    def test_qdrant_raises_before_warmup(self):
        """Accessing qdrant() before warmup raises RuntimeError."""
        from core.runtime.resource_manager import ResourceManager

        rm = ResourceManager()
        with pytest.raises(RuntimeError, match="not connected"):
            rm.qdrant()


class TestStartupEndpoints:
    """Integration smoke tests for the 503 → 200 warmup lifecycle."""

    def test_health_liveness_always_200(self):
        """GET /health returns 200 immediately — even before warmup."""
        from fastapi.testclient import TestClient
        from app.main import app

        # Don't use lifespan — test raw liveness
        with patch("app.main._background_init", new_callable=AsyncMock):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/health")
                assert resp.status_code == 200
                assert resp.json()["status"] == "alive"

    def test_query_returns_503_before_ready(self):
        """POST /query returns 503 when app.state.ready is False."""
        from fastapi.testclient import TestClient
        from app.main import app

        with patch("app.main._background_init", new_callable=AsyncMock):
            with TestClient(app, raise_server_exceptions=False) as client:
                # warmup never completes — ready stays False
                resp = client.post(
                    "/api/v1/query",
                    json={"question": "test", "use_agent": False},
                )
                assert resp.status_code == 503
                assert "warming up" in resp.json()["detail"].lower()

    def test_health_ready_returns_503_before_warmup(self):
        """GET /health/ready returns 503 when app.state.ready is False."""
        from fastapi.testclient import TestClient
        from app.main import app

        with patch("app.main._background_init", new_callable=AsyncMock):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/health/ready")
                assert resp.status_code == 503
