from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: Literal["user", "admin"] = "user"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BenchmarkRequest(BaseModel):
    hip_code: str = Field(min_length=1)
    predicted_performance: Optional[str] = None


class MatrixBenchmarkRequest(BaseModel):
    hip_code: str = Field(min_length=1)
    devices: List[str] = Field(default_factory=lambda: ["MI210", "MI250", "MI300"])
    input_sizes: List[int] = Field(default_factory=lambda: [256, 512, 1024])
    predicted_performance: Optional[str] = None


class TrainModelRequest(BaseModel):
    dataset_path: Optional[str] = None
    output_path: str = "data/model_artifacts/calibrated_model.joblib"
