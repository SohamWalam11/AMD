from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
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
ANALYSIS_JOBS: Dict[str, Dict[str, Any]] = {}
ANALYSIS_HISTORY: list[Dict[str, Any]] = []
JOB_LOCK = asyncio.Lock()
HISTORY_FILE = Path(os.getenv("HISTORY_FILE", "data/analysis_history.json"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "200"))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_history() -> None:
    global ANALYSIS_HISTORY
    if not HISTORY_FILE.exists():
        ANALYSIS_HISTORY = []
        return
    try:
        payload = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            ANALYSIS_HISTORY = payload[:MAX_HISTORY]
    except Exception:
        ANALYSIS_HISTORY = []


def _save_history() -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(ANALYSIS_HISTORY[:MAX_HISTORY], indent=2), encoding="utf-8")


def _history_item_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": result.get("job_id"),
        "code_hash": result.get("code_hash"),
        "compatibility_score": result.get("compatibility_score"),
        "performance_prediction": result.get("performance_prediction"),
        "effort_hours": result.get("effort_hours"),
        "warnings_count": len(result.get("warnings", [])),
        "created_at": result.get("created_at", _iso_now()),
        "completed_at": _iso_now(),
    }


def _build_kernel_risks(analysis: Dict[str, Any]) -> list[Dict[str, Any]]:
    kernel_risks = []
    for kernel in analysis.get("kernels", []):
        issues = kernel.get("incompatible_patterns", [])
        severity_rank = {"low": 1, "medium": 2, "high": 3}
        highest = "low"
        for issue in issues:
            current = str(issue.get("severity", "low"))
            if severity_rank.get(current, 1) > severity_rank.get(highest, 1):
                highest = current

        risk_score = int(min(100, kernel.get("complexity_score", 0) + (10 * len(issues))))
        kernel_risks.append(
            {
                "name": kernel.get("name", "unknown"),
                "complexity_score": kernel.get("complexity_score", 0),
                "risk_score": risk_score,
                "severity": highest,
                "issues": issues,
            }
        )
    return kernel_risks


async def _run_analysis_pipeline(filename: str, payload: bytes) -> Dict[str, Any]:
    if not filename.endswith(".cu"):
        raise HTTPException(status_code=400, detail="Only .cu files are supported")
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    code_hash = hashlib.sha256(payload).hexdigest()
    cuda_code = payload.decode("utf-8", errors="ignore")

    with tempfile.TemporaryDirectory(prefix="cuda_upload_") as tmp_dir:
        tmp_path = Path(tmp_dir) / filename
        tmp_path.write_text(cuda_code, encoding="utf-8")
        analysis = parse_cuda_file(str(tmp_path))

    compatibility = await analyze_with_claude(analysis)
    warnings = compatibility.challenges
    kernel_risks = _build_kernel_risks(analysis)

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
        "warning_details": compatibility.warning_details,
        "recommendations": compatibility.recommendations,
        "explainability": compatibility.explainability,
        "kernel_risks": kernel_risks,
        "analysis": analysis,
        "hip_code": hip_code,
        "migration_guide": generate_migration_guide(
            {
                **analysis,
                "compatibility_score": compatibility.compatibility_score,
            }
        ),
    }
    return response


async def _process_async_job(job_id: str, filename: str, payload: bytes) -> None:
    async with JOB_LOCK:
        job = ANALYSIS_JOBS[job_id]
        job["status"] = "running"
        job["progress"] = 10
        job["stage"] = "Parsing CUDA"

    try:
        await asyncio.sleep(0.05)
        result = await _run_analysis_pipeline(filename, payload)

        async with JOB_LOCK:
            job = ANALYSIS_JOBS[job_id]
            job["progress"] = 95
            job["stage"] = "Finalizing report"
            job["result"] = {**result, "job_id": job_id, "created_at": job.get("created_at")}
            job["status"] = "completed"
            job["progress"] = 100
            job["stage"] = "Completed"
            job["updated_at"] = _iso_now()

        ANALYSIS_HISTORY.insert(0, _history_item_from_result(job["result"]))
        del ANALYSIS_HISTORY[MAX_HISTORY:]
        _save_history()
    except Exception as exc:
        async with JOB_LOCK:
            job = ANALYSIS_JOBS[job_id]
            job["status"] = "failed"
            job["progress"] = 100
            job["stage"] = "Failed"
            job["error"] = str(exc)
            job["updated_at"] = _iso_now()


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
    _load_history()


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", dependencies=[Depends(optional_rate_limiter)])
async def analyze_cuda_code(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    payload = await file.read()
    response = await _run_analysis_pipeline(file.filename, payload)
    return JSONResponse(content=response)


@app.post("/api/analyze/async", dependencies=[Depends(optional_rate_limiter)])
async def analyze_cuda_code_async(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    payload = await file.read()
    if not file.filename.endswith(".cu"):
        raise HTTPException(status_code=400, detail="Only .cu files are supported")
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    job_id = str(uuid4())
    created_at = _iso_now()
    async with JOB_LOCK:
        ANALYSIS_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "stage": "Queued",
            "created_at": created_at,
            "updated_at": created_at,
        }

    asyncio.create_task(_process_async_job(job_id, file.filename, payload))
    return {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "stage": "Queued",
        "created_at": created_at,
    }


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str) -> Dict[str, Any]:
    job = ANALYSIS_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_status(job_id: str) -> StreamingResponse:
    async def event_generator() -> Any:
        while True:
            job = ANALYSIS_JOBS.get(job_id)
            if not job:
                yield "event: error\ndata: {\"detail\":\"Job not found\"}\n\n"
                break

            payload = json.dumps(
                {
                    "job_id": job.get("job_id"),
                    "status": job.get("status"),
                    "progress": job.get("progress"),
                    "stage": job.get("stage"),
                }
            )
            yield f"event: status\ndata: {payload}\n\n"

            if job.get("status") in {"completed", "failed"}:
                break

            await asyncio.sleep(0.75)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/history")
async def get_analysis_history(limit: int = 20) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 100))
    return {"items": ANALYSIS_HISTORY[:safe_limit], "count": len(ANALYSIS_HISTORY)}


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
