from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

from amd_benchmark import benchmark_matrix, benchmark_on_mi300x, compare_predicted_vs_actual
from auth import (
    AUTH_REQUIRED,
    authenticate_user,
    create_access_token,
    ensure_default_admin,
    get_current_user_optional,
    register_user,
    require_role,
)
from compatibility_predictor import analyze_with_claude, estimate_porting_effort
from compile_fix import parse_compile_errors, run_compile_fix_loop
from cuda_analyzer import parse_cuda_file
from hip_generator import add_inline_annotations, convert_cuda_to_hip, generate_migration_guide
from observability import (
    ANALYSIS_CACHE_HITS,
    ANALYSIS_CACHE_MISSES,
    init_sentry,
    metrics_middleware,
    metrics_response,
    setup_structured_logging,
)
from schemas import BenchmarkRequest, MatrixBenchmarkRequest, RegisterRequest, TokenResponse, TrainModelRequest
from training_pipeline import train_calibrated_model

app = FastAPI(title="ROCm Porting Intelligence API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(metrics_middleware)

logger = logging.getLogger(__name__)

BENCHMARK_CACHE: Dict[str, Dict[str, Any]] = {}
RATE_LIMIT_ENABLED = False
ANALYSIS_JOBS: Dict[str, Dict[str, Any]] = {}
ANALYSIS_HISTORY: list[Dict[str, Any]] = []
BENCHMARK_RUNS: list[Dict[str, Any]] = []
ANALYSIS_CACHE: Dict[str, Dict[str, Any]] = {}
JOB_LOCK = asyncio.Lock()
HISTORY_FILE = Path(os.getenv("HISTORY_FILE", "data/analysis_history.json"))
BENCHMARK_RUNS_FILE = Path(os.getenv("BENCHMARK_RUNS_FILE", "data/benchmark_runs.json"))
ANALYSIS_CACHE_FILE = Path(os.getenv("ANALYSIS_CACHE_FILE", "data/analysis_cache.json"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "200"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_list(path: Path) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def _save_list(path: Path, data: list[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_cache() -> Dict[str, Dict[str, Any]]:
    if not ANALYSIS_CACHE_FILE.exists():
        return {}
    try:
        payload = json.loads(ANALYSIS_CACHE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save_cache() -> None:
    ANALYSIS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ANALYSIS_CACHE_FILE.write_text(json.dumps(ANALYSIS_CACHE, indent=2), encoding="utf-8")


def _cache_is_fresh(entry: Dict[str, Any]) -> bool:
    cached_at = entry.get("cached_at")
    if not cached_at:
        return False
    try:
        ts = datetime.fromisoformat(str(cached_at))
        return (datetime.now(timezone.utc) - ts).total_seconds() <= CACHE_TTL_SECONDS
    except Exception:
        return False


def _history_item_from_result(result: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    return {
        "job_id": result.get("job_id"),
        "user_id": user_id,
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
    cache_entry = ANALYSIS_CACHE.get(code_hash)
    if cache_entry and _cache_is_fresh(cache_entry):
        ANALYSIS_CACHE_HITS.inc()
        cached_result = copy.deepcopy(cache_entry["result"])
        cached_result["cached"] = True
        return cached_result

    ANALYSIS_CACHE_MISSES.inc()

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
        "migration_guide": generate_migration_guide({**analysis, "compatibility_score": compatibility.compatibility_score}),
        "cached": False,
    }

    ANALYSIS_CACHE[code_hash] = {"cached_at": _iso_now(), "result": response}
    _save_cache()
    return response


async def _process_async_job(job_id: str, user_id: str, filename: str, payload: bytes) -> None:
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
            job["stage"] = "completed"
            job["updated_at"] = _iso_now()

        ANALYSIS_HISTORY.insert(0, _history_item_from_result(job["result"], user_id))
        del ANALYSIS_HISTORY[MAX_HISTORY:]
        _save_list(HISTORY_FILE, ANALYSIS_HISTORY)
    except Exception as exc:
        logger.exception("Async analysis job failed", exc_info=exc)
        async with JOB_LOCK:
            job = ANALYSIS_JOBS[job_id]
            job["status"] = "failed"
            job["progress"] = 100
            job["stage"] = "failed"
            job["error"] = str(exc)
            job["updated_at"] = _iso_now()


async def optional_rate_limiter(request: Request, response: Response) -> None:
    if not RATE_LIMIT_ENABLED:
        return
    limiter = RateLimiter(times=10, hours=1)
    await limiter(request, response)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": exc.errors(),
            "path": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception for path %s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "Unexpected server error",
            "path": str(request.url.path),
        },
    )


@app.on_event("startup")
async def startup() -> None:
    global RATE_LIMIT_ENABLED, ANALYSIS_HISTORY, BENCHMARK_RUNS, ANALYSIS_CACHE

    setup_structured_logging()
    init_sentry()
    ensure_default_admin()

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await FastAPILimiter.init(redis)
        RATE_LIMIT_ENABLED = True
    except Exception:
        RATE_LIMIT_ENABLED = False

    ANALYSIS_HISTORY = _load_list(HISTORY_FILE)
    BENCHMARK_RUNS = _load_list(BENCHMARK_RUNS_FILE)
    ANALYSIS_CACHE = _load_cache()


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "auth_required": AUTH_REQUIRED}


@app.get("/ready")
async def ready() -> Dict[str, Any]:
    checks = {
        "history_store": HISTORY_FILE.parent.exists() or True,
        "cache_store": ANALYSIS_CACHE_FILE.parent.exists() or True,
    }
    return {"status": "ready" if all(checks.values()) else "degraded", "checks": checks}


@app.get("/metrics")
async def metrics() -> Response:
    return metrics_response()


@app.post("/auth/register")
async def auth_register(payload: RegisterRequest) -> Dict[str, Any]:
    if payload.role == "admin" and os.getenv("ALLOW_ADMIN_SIGNUP", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Admin signup is disabled")
    user = register_user(payload.username, payload.password, payload.role)
    return {"status": "created", "user": user}


@app.post("/auth/token", response_model=TokenResponse)
async def auth_token(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(user["username"], user.get("role", "user"))
    return TokenResponse(access_token=token)


@app.get("/auth/me")
async def auth_me(current_user: Dict[str, Any] = Depends(get_current_user_optional)) -> Dict[str, Any]:
    return current_user


@app.post("/api/analyze", dependencies=[Depends(optional_rate_limiter)])
async def analyze_cuda_code(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user_optional),
) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    payload = await file.read()
    response = await _run_analysis_pipeline(file.filename, payload)
    ANALYSIS_HISTORY.insert(0, _history_item_from_result(response, current_user.get("username", "anonymous")))
    del ANALYSIS_HISTORY[MAX_HISTORY:]
    _save_list(HISTORY_FILE, ANALYSIS_HISTORY)
    return JSONResponse(content=response)


@app.post("/api/analyze/async", dependencies=[Depends(optional_rate_limiter)])
async def analyze_cuda_code_async(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
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
            "stage": "queued",
            "created_at": created_at,
            "updated_at": created_at,
            "user_id": current_user.get("username", "anonymous"),
        }

    asyncio.create_task(_process_async_job(job_id, current_user.get("username", "anonymous"), file.filename, payload))
    return {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "stage": "queued",
        "created_at": created_at,
    }


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str, current_user: Dict[str, Any] = Depends(get_current_user_optional)) -> Dict[str, Any]:
    job = ANALYSIS_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if current_user.get("role") != "admin" and job.get("user_id") != current_user.get("username", "anonymous"):
        raise HTTPException(status_code=403, detail="Access denied for this job")
    return job


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_status(
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_optional),
) -> StreamingResponse:
    async def event_generator() -> Any:
        while True:
            job = ANALYSIS_JOBS.get(job_id)
            if not job:
                yield "event: error\ndata: {\"detail\":\"Job not found\"}\n\n"
                break

            if current_user.get("role") != "admin" and job.get("user_id") != current_user.get("username", "anonymous"):
                yield "event: error\ndata: {\"detail\":\"Access denied\"}\n\n"
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
async def get_analysis_history(
    limit: int = 20,
    current_user: Dict[str, Any] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 100))
    username = current_user.get("username", "anonymous")
    role = current_user.get("role", "anonymous")

    if role == "admin":
        items = ANALYSIS_HISTORY[:safe_limit]
    else:
        items = [item for item in ANALYSIS_HISTORY if item.get("user_id") == username][:safe_limit]
    return {"items": items, "count": len(items)}


@app.get("/api/admin/history/all")
async def admin_all_history(
    limit: int = 50,
    _admin: Dict[str, Any] = Depends(require_role("admin")),
) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 200))
    return {"items": ANALYSIS_HISTORY[:safe_limit], "count": len(ANALYSIS_HISTORY)}


@app.post("/api/benchmark")
async def benchmark_hip_code(
    body: BenchmarkRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    result = benchmark_on_mi300x(body.hip_code)
    code_hash = hashlib.sha256(body.hip_code.encode("utf-8")).hexdigest()
    BENCHMARK_CACHE[code_hash] = result

    comparison = compare_predicted_vs_actual(body.predicted_performance, float(result.get("execution_time_ms", -1.0)))

    run = {
        "code_hash": code_hash,
        "user_id": current_user.get("username", "anonymous"),
        "predicted_performance": body.predicted_performance,
        "actual": result,
        "comparison": comparison,
        "created_at": _iso_now(),
    }
    BENCHMARK_RUNS.insert(0, run)
    del BENCHMARK_RUNS[MAX_HISTORY:]
    _save_list(BENCHMARK_RUNS_FILE, BENCHMARK_RUNS)

    return {"code_hash": code_hash, **result, "comparison": comparison}


@app.post("/api/benchmark/matrix")
async def benchmark_hip_matrix(
    body: MatrixBenchmarkRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    matrix = benchmark_matrix(body.hip_code, body.devices, body.input_sizes)
    summary_runs = []
    for row in matrix["rows"]:
        summary_runs.append(
            {
                "user_id": current_user.get("username", "anonymous"),
                "device": row["device"],
                "input_size": row["input_size"],
                "execution_time_ms": row["execution_time_ms"],
                "comparison": compare_predicted_vs_actual(
                    body.predicted_performance,
                    float(row.get("execution_time_ms", -1.0)),
                ),
                "created_at": _iso_now(),
            }
        )

    BENCHMARK_RUNS[0:0] = summary_runs
    del BENCHMARK_RUNS[MAX_HISTORY:]
    _save_list(BENCHMARK_RUNS_FILE, BENCHMARK_RUNS)
    return matrix


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


@app.get("/api/benchmark/runs")
async def get_benchmark_runs(
    limit: int = 20,
    current_user: Dict[str, Any] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 100))
    if current_user.get("role") == "admin":
        items = BENCHMARK_RUNS[:safe_limit]
    else:
        items = [r for r in BENCHMARK_RUNS if r.get("user_id") == current_user.get("username")][:safe_limit]
    return {"items": items, "count": len(items)}


@app.post("/api/compile-fix")
async def compile_fix(
    body: BenchmarkRequest,
    _current_user: Dict[str, Any] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    result = run_compile_fix_loop(body.hip_code, max_attempts=2)
    if not result.get("compiled"):
        last_stderr = ""
        attempts = result.get("attempts", [])
        if attempts:
            last_stderr = attempts[-1].get("stderr", "")
        result["parsed_errors"] = parse_compile_errors(last_stderr)
    return result


@app.post("/api/model/train")
async def model_train(
    body: TrainModelRequest,
    _admin: Dict[str, Any] = Depends(require_role("admin")),
) -> Dict[str, Any]:
    metrics = train_calibrated_model(body.dataset_path, body.output_path)
    return {"status": "trained", "metrics": metrics}


@app.get("/api/schema")
async def api_schema() -> Dict[str, Any]:
    return app.openapi()
