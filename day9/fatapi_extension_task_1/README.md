# Day 9 - FastAPI Extension Task 1

Extensions A and B from the Day 9 middleware and observability demo.

## Goal

### Extension A - Rate-Limiting Middleware

Add a sliding-window rate limiter to the FastAPI service:

- Limit each client IP to `100` requests per minute by default.
- Return `429 Too Many Requests` when the client exceeds the limit.
- Include a `Retry-After` header on rate-limited responses.
- Track rate-limit hits with a Prometheus counter.

### Extension B - Correlation ID Propagation

Propagate request correlation IDs to downstream `httpx` calls:

- Store `X-Correlation-Id` in a request-scoped `contextvars.ContextVar`.
- Generate a correlation ID when the incoming request does not provide one.
- Return the correlation ID on every response.
- Inject `X-Correlation-Id` into outbound `httpx.AsyncClient` requests.
- Verify propagation with a mocked downstream request in tests.

## Run

```powershell
uvicorn app:app --reload
```

## Try It

```powershell
curl http://127.0.0.1:8000/health/ready
curl http://127.0.0.1:8000/correlation-id -H "X-Correlation-Id: demo-corr-001"
curl http://127.0.0.1:8000/metrics
```

For a quick demo, lower the limit with environment variables:

```powershell
$env:RATE_LIMIT_MAX_REQUESTS = "3"
$env:RATE_LIMIT_WINDOW_SECONDS = "60"
uvicorn app:app --reload
```

## Test

```powershell
python -m pytest tests
```
