from __future__ import annotations

from typing import Dict, List


def convert_cuda_to_hip(cuda_code: str, warnings: List[str]) -> str:
    """Basic CUDA-to-HIP conversion for common APIs and launch wrappers."""
    replacements = {
        "#include <cuda_runtime.h>": "#include <hip/hip_runtime.h>",
        "cudaMalloc": "hipMalloc",
        "cudaFree": "hipFree",
        "cudaMemcpy": "hipMemcpy",
        "cudaMemset": "hipMemset",
        "cudaDeviceSynchronize": "hipDeviceSynchronize",
        "cudaGetDeviceProperties": "hipGetDeviceProperties",
        "cudaDeviceProp": "hipDeviceProp_t",
        "cudaError_t": "hipError_t",
        "cudaSuccess": "hipSuccess",
        "cudaStream_t": "hipStream_t",
        "cudaStreamCreate": "hipStreamCreate",
        "cudaStreamDestroy": "hipStreamDestroy",
        "cudaStreamSynchronize": "hipStreamSynchronize",
    }

    hip_code = cuda_code
    for source, target in replacements.items():
        hip_code = hip_code.replace(source, target)

    if "hip/hip_runtime.h" not in hip_code:
        hip_code = '#include <hip/hip_runtime.h>\n' + hip_code

    issue_lines = [f"// ⚠️ WARNING: {warning}" for warning in warnings]
    banner = "\n".join(issue_lines)
    if banner:
        hip_code = f"{banner}\n{hip_code}"

    return hip_code


def add_inline_annotations(hip_code: str, issues: List[str]) -> str:
    """Inject inline migration guidance around kernels and synchronization points."""
    lines = hip_code.splitlines()
    annotated: List[str] = []

    kernel_tip_added = False
    for line in lines:
        stripped = line.strip()

        if not kernel_tip_added and "__global__" in stripped:
            annotated.append("// 💡 TIP: Use hipDeviceProp_t and query warpSize at runtime (AMD wavefront is often 64).")
            kernel_tip_added = True

        if "__syncthreads" in stripped:
            annotated.append("// 💡 TIP: Verify synchronization assumptions and occupancy on MI300 architecture.")

        if "texture" in stripped.lower() or "surface" in stripped.lower():
            annotated.append("// ⚠️ WARNING: Texture/surface behavior can differ; validate caches and addressing modes.")

        annotated.append(line)

    if issues:
        annotated.append("")
        annotated.append("// Migration Issues Summary")
        for issue in issues:
            annotated.append(f"// - {issue}")

    return "\n".join(annotated)


def generate_migration_guide(analysis: Dict) -> str:
    kernel_names = [k.get("name", "unknown") for k in analysis.get("kernels", [])]
    compatibility = analysis.get("compatibility_score", "n/a")

    return "\n".join(
        [
            "# ROCm Migration Guide",
            "",
            f"Compatibility Score: {compatibility}",
            f"Detected Kernels: {', '.join(kernel_names) if kernel_names else 'none'}",
            "",
            "## Recommended Workflow",
            "1. Run hipify for first-pass API conversion.",
            "2. Replace unsupported CUDA-specific patterns manually.",
            "3. Validate correctness with unit and numerical tests.",
            "4. Profile on AMD hardware and tune block size/LDS use.",
            "",
            "## AMD Documentation",
            "- HIP Porting Guide: https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/hip_porting_guide.html",
            "- HIP Kernel Language: https://rocm.docs.amd.com/projects/HIP/en/latest/reference/kernel_language.html",
            "- MI300 Architecture: https://rocm.docs.amd.com/en/latest/conceptual/gpu-arch/mi300.html",
        ]
    )
