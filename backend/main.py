from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

from amd_benchmark import benchmark_on_mi300x
from compatibility_predictor import analyze_with_claude, estimate_porting_effort
from cuda_analyzer import parse_cuda_file
from hip_generator import add_inline_annotations, convert_cuda_to_hip, generate_migration_guide

app = FastAPI(title="ROCm Porting Intelligence API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BENCHMARK_CACHE: Dict[str, Dict[str, Any]] = {}
RATE_LIMIT_ENABLED = False


async def optional_rate_limiter(request: Request, response: Response) -> None:
    if not RATE_LIMIT_ENABLED:
        return
    limiter = RateLimiter(times=10, hours=1)
    await limiter(request, response)


@app.on_event("startup")
async def startup() -> None:
    global RATE_LIMIT_ENABLED
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await FastAPILimiter.init(redis)
        RATE_LIMIT_ENABLED = True
    except Exception:
        RATE_LIMIT_ENABLED = False


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", dependencies=[Depends(optional_rate_limiter)])
async def analyze_cuda_code(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.endswith(".cu"):
        raise HTTPException(status_code=400, detail="Only .cu files are supported")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    code_hash = hashlib.sha256(payload).hexdigest()
    cuda_code = payload.decode("utf-8", errors="ignore")

    with tempfile.TemporaryDirectory(prefix="cuda_upload_") as tmp_dir:
        tmp_path = Path(tmp_dir) / file.filename
        tmp_path.write_text(cuda_code, encoding="utf-8")

        analysis = parse_cuda_file(str(tmp_path))

    compatibility = await analyze_with_claude(analysis)
    warnings = compatibility.challenges

    hip_code = convert_cuda_to_hip(cuda_code, warnings)
    hip_code = add_inline_annotations(hip_code, warnings)

    effort = estimate_porting_effort(float(compatibility.compatibility_score), int(analysis.get("complexity", 0)))

    response = {
        "code_hash": code_hash,
        "compatibility_score": compatibility.compatibility_score,
        "performance_prediction": compatibility.performance_prediction,
        "confidence": compatibility.confidence,
        "effort_hours": effort,
        "warnings": warnings,
        "recommendations": compatibility.recommendations,
        "analysis": analysis,
        "hip_code": hip_code,
        "migration_guide": generate_migration_guide(
            {
                **analysis,
                "compatibility_score": compatibility.compatibility_score,
            }
        ),
    }

    return JSONResponse(content=response)


@app.post("/api/benchmark")
async def benchmark_hip_code(body: Dict[str, Any]) -> Dict[str, Any]:
    hip_code = body.get("hip_code")
    if not hip_code:
        raise HTTPException(status_code=400, detail="hip_code is required")

    result = benchmark_on_mi300x(str(hip_code))
    code_hash = hashlib.sha256(str(hip_code).encode("utf-8")).hexdigest()
    BENCHMARK_CACHE[code_hash] = result
    return {"code_hash": code_hash, **result}


@app.get("/api/benchmark/{code_hash}")
async def get_benchmark_results(code_hash: str) -> Dict[str, Any]:
    cached = BENCHMARK_CACHE.get(code_hash)
    if cached is not None:
        return cached

    return {
        "code_hash": code_hash,
        "status": "not_found",
        "message": "No benchmark results found in in-memory cache",
    }


@app.get("/api/schema")
async def api_schema() -> Dict[str, Any]:
    return app.openapi()
