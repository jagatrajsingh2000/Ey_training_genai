import os
import time
import uuid
from collections import defaultdict, deque
from contextvars import ContextVar
from dataclasses import dataclass, field

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware


CORRELATION_ID_HEADER = "X-Correlation-Id"
correlation_id_var: ContextVar[str | None] = ContextVar(
    "correlation_id",
    default=None,
)

RATE_LIMIT_HITS = Counter(
    "rate_limit_hits_total",
    "Total number of requests rejected by the rate limiter",
    ["client_ip"],
)


@dataclass
class SlidingWindowRateLimiter:
    max_requests: int = 100
    window_seconds: int = 60
    requests_by_client: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(deque)
    )

    def check(self, client_id: str, now: float | None = None) -> tuple[bool, int]:
        current_time = now if now is not None else time.time()
        request_times = self.requests_by_client[client_id]
        window_start = current_time - self.window_seconds

        while request_times and request_times[0] <= window_start:
            request_times.popleft()

        if len(request_times) >= self.max_requests:
            retry_after = max(1, int(request_times[0] + self.window_seconds - current_time))
            return False, retry_after

        request_times.append(current_time)
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        limiter: SlidingWindowRateLimiter,
        excluded_paths: set[str] | None = None,
    ):
        super().__init__(app)
        self.limiter = limiter
        self.excluded_paths = excluded_paths or set()

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = self.limiter.check(client_ip)

        if not allowed:
            RATE_LIMIT_HITS.labels(client_ip=client_ip).inc()
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(CORRELATION_ID_HEADER, str(uuid.uuid4()))
        token = correlation_id_var.set(correlation_id)

        try:
            response = await call_next(request)
            response.headers[CORRELATION_ID_HEADER] = correlation_id
            return response
        finally:
            correlation_id_var.reset(token)


async def add_correlation_id_header(request: httpx.Request) -> None:
    correlation_id = correlation_id_var.get()
    if correlation_id:
        request.headers[CORRELATION_ID_HEADER] = correlation_id


def create_downstream_client(**kwargs) -> httpx.AsyncClient:
    event_hooks = kwargs.pop("event_hooks", {})
    request_hooks = list(event_hooks.get("request", []))
    request_hooks.append(add_correlation_id_header)
    event_hooks["request"] = request_hooks
    return httpx.AsyncClient(event_hooks=event_hooks, **kwargs)


def create_app() -> FastAPI:
    max_requests = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))
    window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    api = FastAPI(title="EY Payment API - Rate Limiting", version="1.0.0")
    api.add_middleware(
        RateLimitMiddleware,
        limiter=SlidingWindowRateLimiter(
            max_requests=max_requests,
            window_seconds=window_seconds,
        ),
        excluded_paths={"/metrics"},
    )
    api.add_middleware(CorrelationIdMiddleware)

    @api.get("/health/live")
    async def liveness():
        return {"status": "alive"}

    @api.get("/health/ready")
    async def readiness():
        return {"status": "ready", "db": "ok", "mq": "ok"}

    @api.post("/payments")
    async def create_payment(payment: dict):
        return {"status": "accepted", **payment}

    @api.get("/correlation-id")
    async def current_correlation_id():
        return {"correlation_id": correlation_id_var.get()}

    @api.get("/metrics")
    async def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return api


app = create_app()
