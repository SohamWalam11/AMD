from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
from sklearn.ensemble import RandomForestClassifier


@dataclass(slots=True)
class CompatibilityReport:
    compatibility_score: int
    performance_prediction: str
    confidence: str
    challenges: List[str]
    recommendations: List[str]
    explainability: List[Dict[str, Any]]
    warning_details: List[Dict[str, str]]


def _train_default_model() -> RandomForestClassifier:
    features = np.array(
        [
            [20, 0, 2],
            [35, 1, 3],
            [50, 1, 5],
            [65, 2, 6],
            [80, 3, 7],
            [90, 4, 8],
            [30, 0, 1],
            [45, 1, 4],
            [75, 3, 6],
        ]
    )
    targets = np.array([2, 2, 1, 1, 0, 0, 2, 1, 0])

    model = RandomForestClassifier(n_estimators=64, random_state=42)
    model.fit(features, targets)
    return model


_MODEL = _train_default_model()


def _build_features(cuda_patterns: Dict[str, Any]) -> np.ndarray:
    complexity = int(cuda_patterns.get("complexity", 0))
    memory_patterns = cuda_patterns.get("memory_patterns", {})
    memory_score = int(sum(1 for value in memory_patterns.values() if value))
    api_usage = int(sum(len(v) for v in cuda_patterns.get("api_calls", {}).values()))
    return np.array([complexity, memory_score, api_usage])


def predict_compatibility_ml(features: np.ndarray) -> float:
    """Predict compatibility score using a light ML fallback model."""
    reshaped = np.asarray(features, dtype=float).reshape(1, -1)
    proba = _MODEL.predict_proba(reshaped)[0]

    category_score = {
        0: 45.0,
        1: 70.0,
        2: 88.0,
    }

    weighted = 0.0
    for class_idx, class_proba in enumerate(proba):
        weighted += category_score.get(class_idx, 60.0) * float(class_proba)
    return round(weighted, 2)


def estimate_porting_effort(compatibility: float, complexity: int) -> int:
    risk_factor = max(0.1, (100.0 - compatibility) / 100.0)
    effort = int(4 + complexity * 0.35 + 40 * risk_factor)
    return max(2, effort)


def _build_explainability(cuda_patterns: Dict[str, Any], score: float) -> List[Dict[str, Any]]:
    complexity = int(cuda_patterns.get("complexity", 0))
    memory_patterns = cuda_patterns.get("memory_patterns", {})
    api_calls = cuda_patterns.get("api_calls", {})
    dynamic_parallelism = bool(cuda_patterns.get("dynamic_parallelism", False))
    texture_surface = bool(cuda_patterns.get("texture_surface_ops", []))

    factors: List[Dict[str, Any]] = [
        {
            "name": "Kernel complexity",
            "value": complexity,
            "impact": "negative" if complexity > 70 else "neutral",
            "reason": "Higher control-flow/loop density generally increases migration tuning effort.",
        },
        {
            "name": "Memory pattern diversity",
            "value": int(sum(1 for value in memory_patterns.values() if value)),
            "impact": "neutral",
            "reason": "Mixed memory usage requires architecture-specific validation on ROCm.",
        },
        {
            "name": "CUDA API surface",
            "value": int(sum(len(v) for v in api_calls.values())),
            "impact": "negative" if int(sum(len(v) for v in api_calls.values())) > 5 else "neutral",
            "reason": "More CUDA runtime usage increases migration touchpoints.",
        },
    ]

    if dynamic_parallelism:
        factors.append(
            {
                "name": "Dynamic parallelism",
                "value": 1,
                "impact": "negative",
                "reason": "Device-side launch patterns often need redesign for best ROCm support.",
            }
        )

    if texture_surface:
        factors.append(
            {
                "name": "Texture/surface usage",
                "value": 1,
                "impact": "negative",
                "reason": "Texture/surface APIs typically require manual adaptation.",
            }
        )

    factors.append(
        {
            "name": "Predicted compatibility",
            "value": round(score, 2),
            "impact": "positive" if score >= 80 else "neutral",
            "reason": "Aggregate model score based on complexity, memory patterns, and API usage.",
        }
    )
    return factors


def _build_warning_details(challenges: List[str]) -> List[Dict[str, str]]:
    details: List[Dict[str, str]] = []
    for challenge in challenges:
        severity = "high" if "dynamic" in challenge.lower() else "medium"
        details.append(
            {
                "code": "MIGRATION_CHALLENGE",
                "severity": severity,
                "message": challenge,
                "doc_url": "https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/hip_porting_guide.html",
            }
        )
    return details


async def analyze_with_claude(cuda_patterns: Dict[str, Any]) -> CompatibilityReport:
    """
    Analyze CUDA patterns using Claude Sonnet with ML fallback.
    Requires ANTHROPIC_API_KEY in environment for API mode.
    """
    api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

    prompt = (
        "You are an expert in CUDA and AMD ROCm/HIP migration. Analyze this CUDA code "
        "pattern and provide:\n"
        "1. Compatibility score (0-100) with AMD GPUs\n"
        "2. Performance prediction (% faster/slower than NVIDIA)\n"
        "3. Key migration challenges\n"
        "4. Recommended HIP equivalent patterns\n\n"
        f"CUDA Analysis:\n{json.dumps(cuda_patterns, indent=2)}\n\n"
        "Respond in JSON format with keys: compatibility_score, performance_prediction, "
        "confidence, challenges, recommendations."
    )

    if api_key:
        try:
            from anthropic import AsyncAnthropic  # type: ignore

            client = AsyncAnthropic(api_key=api_key)
            message = await client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=700,
                temperature=0.1,
                system="Return only valid JSON.",
                messages=[{"role": "user", "content": prompt}],
            )
            text_chunks = [
                block.text for block in message.content if hasattr(block, "text")
            ]
            content = "\n".join(text_chunks).strip()
            payload = _extract_json(content)
            return CompatibilityReport(
                compatibility_score=int(payload.get("compatibility_score", 70)),
                performance_prediction=str(payload.get("performance_prediction", "0%")),
                confidence=str(payload.get("confidence", "medium")),
                challenges=list(payload.get("challenges", [])),
                recommendations=list(payload.get("recommendations", [])),
                explainability=list(payload.get("explainability", [])) or _build_explainability(
                    cuda_patterns, float(payload.get("compatibility_score", 70))
                ),
                warning_details=list(payload.get("warning_details", []))
                or _build_warning_details(list(payload.get("challenges", []))),
            )
        except Exception:
            pass

    features = _build_features(cuda_patterns)
    score = predict_compatibility_ml(features)
    complexity = int(cuda_patterns.get("complexity", 0))
    perf_delta = int((score - 70) / 2 - max(0, complexity - 60) * 0.2)

    challenges = []
    if cuda_patterns.get("dynamic_parallelism"):
        challenges.append("Dynamic parallelism may not map efficiently to all AMD targets")
    if cuda_patterns.get("texture_surface_ops"):
        challenges.append("Texture/surface APIs need manual HIP adaptation")
    if complexity > 70:
        challenges.append("Kernel complexity suggests higher migration and tuning effort")

    if not challenges:
        challenges = ["Validate occupancy and LDS usage on target AMD architecture"]

    recommendations = [
        "Use HIP porting guide and hipify first pass",
        "Prefer sync warp intrinsics and validate lane assumptions for wavefront size",
        "Benchmark with rocprof and tune block size for MI300-class GPUs",
    ]

    return CompatibilityReport(
        compatibility_score=int(round(score)),
        performance_prediction=f"{perf_delta:+d}%",
        confidence="medium",
        challenges=challenges,
        recommendations=recommendations,
        explainability=_build_explainability(cuda_patterns, float(score)),
        warning_details=_build_warning_details(challenges),
    )


def _extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))
