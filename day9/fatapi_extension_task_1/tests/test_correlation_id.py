import asyncio
import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import (
    CORRELATION_ID_HEADER,
    correlation_id_var,
    create_app,
    create_downstream_client,
)


def test_returns_inbound_correlation_id_header():
    client = TestClient(create_app())

    response = client.get(
        "/correlation-id",
        headers={CORRELATION_ID_HEADER: "payment-flow-123"},
    )

    assert response.status_code == 200
    assert response.headers[CORRELATION_ID_HEADER] == "payment-flow-123"
    assert response.json()["correlation_id"] == "payment-flow-123"


def test_generates_correlation_id_when_header_is_missing():
    client = TestClient(create_app())

    response = client.get("/correlation-id")

    assert response.status_code == 200
    assert response.headers[CORRELATION_ID_HEADER]
    assert response.json()["correlation_id"] == response.headers[CORRELATION_ID_HEADER]


async def capture_downstream_request(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json={"correlation_id": request.headers.get(CORRELATION_ID_HEADER)},
    )


def test_injects_correlation_id_into_outbound_httpx_calls():
    async def make_request():
        token = correlation_id_var.set("payment-flow-456")
        try:
            transport = httpx.MockTransport(capture_downstream_request)
            async with create_downstream_client(transport=transport) as client:
                return await client.get("https://fraud.example.test/check")
        finally:
            correlation_id_var.reset(token)

    response = asyncio.run(make_request())

    assert response.status_code == 200
    assert response.json()["correlation_id"] == "payment-flow-456"


def test_correlation_middleware_clears_context_after_request():
    client = TestClient(create_app())

    response = client.get(
        "/correlation-id",
        headers={CORRELATION_ID_HEADER: "payment-flow-789"},
    )

    assert response.status_code == 200
    assert correlation_id_var.get() is None


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__]))
