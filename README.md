# ROCm Porting Intelligence Platform

AI-powered CUDA-to-ROCm migration prediction platform for AMD Slingshot hackathon.

## What it does

- Parses `.cu` files with a layered strategy: **Clang/LLVM -> Tree-sitter -> regex fallback**
- Predicts ROCm migration success with:
  - Compatibility score (0-100)
  - Performance delta prediction vs NVIDIA
  - Estimated porting effort (hours)
- Generates HIP code with inline warnings/tips and AMD doc links
- Provides a React dashboard with upload, charts, code comparison, and export
- Supports benchmark execution flow for MI300X-ready HIP binaries

## Repository Structure

```text
rocm-porting-intelligence/
├── backend/
│   ├── cuda_analyzer.py
│   ├── compatibility_predictor.py
│   ├── hip_generator.py
│   ├── amd_benchmark.py
│   ├── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── FileUploadZone.tsx
│   │   │   ├── AnalysisDashboard.tsx
│   │   │   ├── CodeComparisonView.tsx
│   │   │   └── ReportExport.tsx
│   │   ├── App.tsx
│   │   └── index.tsx
│   ├── package.json
│   ├── tailwind.config.js
│   └── Dockerfile
├── database/
│   └── schema.sql
├── demo/
│   ├── sample_cuda_kernels/
│   └── benchmark_results/
├── docker-compose.yml
└── README.md
```

## Quick Start (Docker)

1. Create env file:

```bash
cp .env.example .env
```

2. Add your key in `.env`:

```bash
CLAUDE_API_KEY=your_key_here
```

3. Run stack:

```bash
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000/docs`

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate  # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

- `POST /auth/register` - Register JWT user (`user` or `admin` role)
- `POST /auth/token` - OAuth2 password login, returns JWT access token
- `GET /auth/me` - Current user and role from token
- `POST /api/analyze` - Upload CUDA `.cu` file for full analysis + HIP conversion
- `POST /api/analyze/async` - Enqueue async analysis job with progress tracking
- `GET /api/jobs/{job_id}` - Fetch async job status and result payload
- `GET /api/jobs/{job_id}/stream` - SSE stream for live job progress events
- `GET /api/history?limit=5` - Fetch recent completed analysis history
- `GET /api/admin/history/all` - Admin-only access to all users history
- `POST /api/benchmark` - Run benchmark on submitted HIP code
- `POST /api/benchmark/matrix` - Benchmark matrix across devices and input sizes
- `GET /api/benchmark/{code_hash}` - Fetch benchmark result cache
- `GET /api/benchmark/runs` - Fetch predicted-vs-actual benchmark run history
- `POST /api/compile-fix` - Run HIP compile-fix loop and parse diagnostics
- `POST /api/model/train` - Admin-only calibrated model training pipeline
- `GET /health` - Service health
- `GET /ready` - Readiness probe
- `GET /metrics` - Prometheus metrics endpoint

## Phase Mapping

- **Phase 1**: `backend/cuda_analyzer.py`
- **Phase 2**: `backend/compatibility_predictor.py`
- **Phase 3**: `backend/hip_generator.py`
- **Phase 4**: `frontend/src/components/*`
- **Phase 5**: `backend/main.py`
- **Phase 6**: `database/schema.sql`
- **Phase 7**: `backend/amd_benchmark.py`

## Demo Script

1. Upload `demo/sample_cuda_kernels/matrix_mul.cu`
2. Show compatibility score (demo target: `88/100`)
3. Show generated HIP code in comparison view
4. Show performance prediction (demo target: `+15%`)
5. Export PDF report

## Testing

```bash
cd backend
pytest -q
```

## Continuous Integration

GitHub Actions workflow: `.github/workflows/ci.yml`

It runs on every push and pull request and includes:

- Backend tests (Python 3.11 + `pytest`)
- Frontend production build (`npm ci` + `npm run build`)
- Docker quality checks:
  - Dockerfile linting with Hadolint
  - Docker image build validation for backend and frontend

Release workflow: `.github/workflows/release-ghcr.yml`

- Builds and pushes backend/frontend images to GHCR
- Triggered by version tags (`v*`) or manual dispatch

## Deployment (Helm)

Chart path: `deploy/helm/rocm-porting-intelligence`

- Base values: `values.yaml`
- Staging overlay: `environments/staging-values.yaml`
- Production overlay: `environments/prod-values.yaml`

Example:

```bash
helm upgrade --install rocm-intel deploy/helm/rocm-porting-intelligence \
  -f deploy/helm/rocm-porting-intelligence/values.yaml \
  -f deploy/helm/rocm-porting-intelligence/environments/staging-values.yaml
```

## Branch Protection

Checklist: `docs/branch-protection-checklist.md`

## Notes

- Claude API is optional. If unavailable, ML fallback scoring is used.
- Redis rate limiting activates automatically when Redis is reachable.
- MI300X benchmarking requires ROCm runtime + `hipcc` on target host.
- JWT auth can be toggled with `AUTH_REQUIRED=true`.
- Sentry activates when `SENTRY_DSN` is set.
