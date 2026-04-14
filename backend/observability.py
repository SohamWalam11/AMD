from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from fastapi import Request, Response
from fastapi.responses import Response as FastAPIResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter("api_requests_total", "Total API requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("api_request_duration_seconds", "API request latency", ["method", "endpoint"])
ANALYSIS_CACHE_HITS = Counter("analysis_cache_hits_total", "Analysis cache hits")
ANALYSIS_CACHE_MISSES = Counter("analysis_cache_misses_total", "Analysis cache misses")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_structured_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    for handler in root.handlers:
        handler.setFormatter(JsonFormatter())

    if not root.handlers:
        stream = logging.StreamHandler()
        stream.setFormatter(JsonFormatter())
        root.addHandler(stream)


def init_sentry() -> None:
    try:
        import os

        dsn = os.getenv("SENTRY_DSN", "")
        if not dsn:
            return

        import sentry_sdk

        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.2)
    except Exception:
        return


async def metrics_middleware(request: Request, call_next: Callable[[Request], Any]) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    endpoint = request.url.path
    REQUEST_LATENCY.labels(request.method, endpoint).observe(duration)
    REQUEST_COUNT.labels(request.method, endpoint, str(response.status_code)).inc()
    return response


def metrics_response() -> FastAPIResponse:
    return FastAPIResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
