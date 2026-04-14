import asyncio

from fastapi.testclient import TestClient

import main
from main import app


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_async_analyze_and_history(monkeypatch) -> None:
    client = TestClient(app)

    async def fake_pipeline(filename: str, payload: bytes):
        return {
            "code_hash": "abc123",
            "compatibility_score": 91,
            "performance_prediction": "+12%",
            "effort_hours": 9,
            "warnings": ["Mock warning"],
            "warning_details": [
                {
                    "code": "MOCK",
                    "severity": "medium",
                    "message": "Mock warning",
                    "doc_url": "https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/hip_porting_guide.html",
                }
            ],
            "recommendations": ["Mock recommendation"],
            "explainability": [],
            "kernel_risks": [],
            "analysis": {"complexity": 10, "kernels": []},
            "hip_code": "// hip code",
            "migration_guide": "guide",
        }

    monkeypatch.setattr(main, "_run_analysis_pipeline", fake_pipeline)
    monkeypatch.setattr(main, "_save_history", lambda: None)
    main.ANALYSIS_HISTORY.clear()
    main.ANALYSIS_JOBS.clear()

    enqueue_response = client.post(
        "/api/analyze/async",
        files={"file": ("sample.cu", b"__global__ void k() {}", "text/plain")},
    )
    assert enqueue_response.status_code == 200
    job_id = enqueue_response.json()["job_id"]

    asyncio.run(main._process_async_job(job_id, "sample.cu", b"__global__ void k() {}"))

    status_response = client.get(f"/api/jobs/{job_id}")
    assert status_response.status_code == 200
    final_status = status_response.json()

    assert final_status is not None
    assert final_status["status"] == "completed"
    assert final_status["result"]["compatibility_score"] == 91

    history_response = client.get("/api/history?limit=5")
    assert history_response.status_code == 200
    items = history_response.json()["items"]
    assert len(items) >= 1
    assert items[0]["code_hash"] == "abc123"
