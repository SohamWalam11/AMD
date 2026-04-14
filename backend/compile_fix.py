from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List


def _suggest_fixes(stderr: str) -> List[str]:
    suggestions: List[str] = []
    text = stderr.lower()
    if "cuda_runtime.h" in text:
        suggestions.append("Replace #include <cuda_runtime.h> with #include <hip/hip_runtime.h>.")
    if "identifier \"cudamalloc\"" in text or "cudamalloc" in text:
        suggestions.append("Replace cudaMalloc/cudaMemcpy/cudaFree APIs with hipMalloc/hipMemcpy/hipFree.")
    if "undefined reference" in text:
        suggestions.append("Check missing HIP runtime symbols and ensure hipcc is used for linking.")
    if "no such file or directory" in text:
        suggestions.append("Verify include/library paths and ROCm installation in environment.")
    if not suggestions:
        suggestions.append("Review compiler diagnostics and apply HIP porting guide fixes.")
    return suggestions


def _apply_basic_patch(code: str) -> str:
    patched = code
    patched = patched.replace("#include <cuda_runtime.h>", "#include <hip/hip_runtime.h>")
    patched = patched.replace("cudaMalloc", "hipMalloc")
    patched = patched.replace("cudaMemcpy", "hipMemcpy")
    patched = patched.replace("cudaFree", "hipFree")
    return patched


def run_compile_fix_loop(hip_code: str, max_attempts: int = 2) -> Dict[str, Any]:
    code = hip_code
    attempts: List[Dict[str, Any]] = []

    try:
        for attempt in range(1, max_attempts + 1):
            with tempfile.TemporaryDirectory(prefix="hip_fix_") as tmp_dir:
                src = Path(tmp_dir) / "kernel.hip"
                out = Path(tmp_dir) / "kernel"
                src.write_text(code, encoding="utf-8")

                proc = subprocess.run(
                    ["hipcc", str(src), "-O2", "-o", str(out)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if proc.returncode == 0:
                    attempts.append(
                        {
                            "attempt": attempt,
                            "compiled": True,
                            "stderr": proc.stderr,
                            "stdout": proc.stdout,
                        }
                    )
                    return {
                        "compiled": True,
                        "attempts": attempts,
                        "fixed_code": code,
                        "suggested_patches": [],
                    }

                suggestions = _suggest_fixes(proc.stderr)
                attempts.append(
                    {
                        "attempt": attempt,
                        "compiled": False,
                        "stderr": proc.stderr,
                        "stdout": proc.stdout,
                        "suggestions": suggestions,
                    }
                )

                code = _apply_basic_patch(code)

    except FileNotFoundError as exc:
        attempts.append(
            {
                "attempt": 1,
                "compiled": False,
                "stderr": str(exc),
                "stdout": "",
                "suggestions": ["Install ROCm HIP toolchain and ensure hipcc is in PATH."],
            }
        )
        return {
            "compiled": False,
            "attempts": attempts,
            "fixed_code": code,
            "suggested_patches": ["Install ROCm HIP toolchain and ensure hipcc is in PATH."],
        }
    except Exception as exc:
        attempts.append(
            {
                "attempt": 1,
                "compiled": False,
                "stderr": str(exc),
                "stdout": "",
                "suggestions": ["Unexpected compile-fix failure. Inspect diagnostics and retry."],
            }
        )
        return {
            "compiled": False,
            "attempts": attempts,
            "fixed_code": code,
            "suggested_patches": ["Unexpected compile-fix failure. Inspect diagnostics and retry."],
        }

    all_suggestions: List[str] = []
    for item in attempts:
        all_suggestions.extend(item.get("suggestions", []))

    unique = list(dict.fromkeys(all_suggestions))
    return {
        "compiled": False,
        "attempts": attempts,
        "fixed_code": code,
        "suggested_patches": unique,
    }


def parse_compile_errors(stderr: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for line in stderr.splitlines():
        match = re.search(r"(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<msg>.+)", line)
        if match:
            issues.append(
                {
                    "file": match.group("file"),
                    "line": int(match.group("line")),
                    "column": int(match.group("col")),
                    "message": match.group("msg"),
                }
            )
    return issues
