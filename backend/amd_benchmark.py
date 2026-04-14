from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict


class BenchmarkError(RuntimeError):
    pass


def parse_timing(output: str) -> float:
    match = re.search(r"execution_time_ms\s*[:=]\s*([0-9]*\.?[0-9]+)", output)
    if match:
        return float(match.group(1))

    generic = re.search(r"([0-9]*\.?[0-9]+)\s*ms", output)
    if generic:
        return float(generic.group(1))

    raise BenchmarkError("Unable to parse execution time from benchmark output")


def benchmark_on_mi300x(hip_code: str) -> Dict:
    """
    Compile and execute HIP code on a host with ROCm/hipcc installed.
    Returns metrics and compiler/runtime outputs.
    """
    with tempfile.TemporaryDirectory(prefix="hip_bench_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_file = tmp_path / "test_kernel.hip"
        binary_file = tmp_path / "test_kernel"
        source_file.write_text(hip_code, encoding="utf-8")

        compile_result = subprocess.run(
            ["hipcc", str(source_file), "-O2", "-o", str(binary_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if compile_result.returncode != 0:
            return {
                "compiled": False,
                "error": "Compilation failed",
                "details": compile_result.stderr,
                "stdout": compile_result.stdout,
            }

        run_result = subprocess.run(
            [str(binary_file)],
            capture_output=True,
            text=True,
            timeout=120,
        )

        try:
            execution_time = parse_timing(run_result.stdout + "\n" + run_result.stderr)
        except BenchmarkError:
            execution_time = -1.0

        return {
            "compiled": True,
            "execution_time_ms": execution_time,
            "return_code": run_result.returncode,
            "stdout": run_result.stdout,
            "stderr": run_result.stderr,
        }
