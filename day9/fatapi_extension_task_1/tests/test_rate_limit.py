import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import RateLimitMiddleware, SlidingWindowRateLimiter


def build_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(
        RateLimitMiddleware,
        limiter=SlidingWindowRateLimiter(max_requests=2, window_seconds=60),
    )

    @test_app.get("/ping")
    async def ping():
        return {"ok": True}

    return test_app


def test_allows_requests_inside_limit():
    client = TestClient(build_test_app())

    first = client.get("/ping")
    second = client.get("/ping")

    assert first.status_code == 200
    assert second.status_code == 200


def test_rejects_requests_over_limit_with_retry_after_header():
    client = TestClient(build_test_app())

    client.get("/ping")
    client.get("/ping")
    response = client.get("/ping")

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many requests"
    assert int(response.headers["Retry-After"]) > 0


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__]))
