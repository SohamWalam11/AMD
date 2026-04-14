from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Warning:
    code: str
    severity: str
    message: str
    doc_url: str


@dataclass(slots=True)
class KernelInfo:
    name: str
    complexity_score: int
    shared_memory_usage: str
    warp_operations: List[str]
    dynamic_parallelism: bool
    incompatible_patterns: List[Warning]
    lines: int
    loops: int
    branches: int


def _read_file(filepath: str) -> str:
    path = Path(filepath)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"CUDA file not found: {filepath}")
    return path.read_text(encoding="utf-8", errors="ignore")


def calculate_complexity(ast_node: Any) -> int:
    """Calculate a normalized 0-100 complexity score from kernel statistics."""
    if isinstance(ast_node, dict):
        lines = int(ast_node.get("lines", 0))
        loops = int(ast_node.get("loops", 0))
        branches = int(ast_node.get("branches", 0))
    else:
        lines = getattr(ast_node, "lines", 0)
        loops = getattr(ast_node, "loops", 0)
        branches = getattr(ast_node, "branches", 0)

    score = min(100, int(lines * 0.8 + loops * 8 + branches * 6))
    return max(score, 0)


def detect_incompatibilities(kernel_info: KernelInfo) -> List[Warning]:
    issues: List[Warning] = []
    if kernel_info.dynamic_parallelism:
        issues.append(
            Warning(
                code="DYN_PARALLEL",
                severity="high",
                message="Dynamic parallelism may require redesign on ROCm/HIP.",
                doc_url="https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/hip_porting_guide.html",
            )
        )

    has_legacy_shuffle = any(op in {"__shfl", "__shfl_down", "__shfl_up"} for op in kernel_info.warp_operations)
    if has_legacy_shuffle:
        issues.append(
            Warning(
                code="LEGACY_WARP_OP",
                severity="medium",
                message="Legacy warp shuffle APIs should be migrated to sync variants.",
                doc_url="https://rocm.docs.amd.com/projects/HIP/en/latest/reference/kernel_language.html",
            )
        )

    if kernel_info.complexity_score > 80:
        issues.append(
            Warning(
                code="HIGH_COMPLEXITY",
                severity="medium",
                message="High kernel complexity may increase migration risk and effort.",
                doc_url="https://rocm.docs.amd.com/en/latest/conceptual/gpu-arch/mi300.html",
            )
        )

    return issues


def extract_kernel_info(ast_node: Dict[str, Any]) -> KernelInfo:
    kernel = KernelInfo(
        name=ast_node["name"],
        complexity_score=calculate_complexity(ast_node),
        shared_memory_usage=ast_node.get("shared_memory_usage", "0 bytes"),
        warp_operations=ast_node.get("warp_operations", []),
        dynamic_parallelism=ast_node.get("dynamic_parallelism", False),
        incompatible_patterns=[],
        lines=ast_node.get("lines", 0),
        loops=ast_node.get("loops", 0),
        branches=ast_node.get("branches", 0),
    )
    kernel.incompatible_patterns = detect_incompatibilities(kernel)
    return kernel


def _extract_api_calls(code: str) -> Dict[str, List[str]]:
    memory_calls = sorted(set(re.findall(r"\b(cudaMalloc|cudaMemcpy|cudaFree|cudaMemset)\b", code)))
    stream_calls = sorted(set(re.findall(r"\b(cudaStreamCreate|cudaStreamDestroy|cudaStreamSynchronize)\b", code)))
    has_kernel_launch = bool(re.search(r"<<<[^>]+>>>", code))
    execution_calls = ["kernel<<<>>>"] if has_kernel_launch else []

    return {
        "memory": memory_calls,
        "execution": execution_calls,
        "streams": stream_calls,
    }


def _regex_kernels(code: str) -> List[Dict[str, Any]]:
    kernel_pattern = re.compile(
        r"__global__\s+void\s+(?P<name>\w+)\s*\([^)]*\)\s*\{(?P<body>[\s\S]*?)\n\}",
        re.MULTILINE,
    )

    kernels: List[Dict[str, Any]] = []
    for match in kernel_pattern.finditer(code):
        body = match.group("body")
        loops = len(re.findall(r"\b(for|while|do)\b", body))
        branches = len(re.findall(r"\b(if|else if|switch)\b", body))
        warp_ops = sorted(set(re.findall(r"\b(__shfl_sync|__shfl|__ballot_sync|__all_sync|__any_sync|__syncthreads)\b", body)))
        dynamic_parallelism = bool(re.search(r"<<<[^>]+>>>", body))
        shared_decl = re.findall(r"__shared__\s+[^;]+;", body)
        shared_bytes = 256 * len(shared_decl) if shared_decl else 0

        kernels.append(
            {
                "name": match.group("name"),
                "lines": len([line for line in body.splitlines() if line.strip()]),
                "loops": loops,
                "branches": branches,
                "warp_operations": warp_ops,
                "dynamic_parallelism": dynamic_parallelism,
                "shared_memory_usage": f"{shared_bytes} bytes",
            }
        )

    return kernels


def _parse_with_clang(filepath: str) -> Optional[List[Dict[str, Any]]]:
    try:
        from clang.cindex import CursorKind, Index  # type: ignore
    except Exception:
        return None

    try:
        index = Index.create()
        tu = index.parse(filepath, args=["-x", "cuda", "--cuda-gpu-arch=sm_80"])
    except Exception as exc:
        logger.warning("Clang parse failed: %s", exc)
        return None

    kernels: List[Dict[str, Any]] = []

    def visit(node: Any) -> None:
        if node.kind == CursorKind.FUNCTION_DECL:
            tokens = [t.spelling for t in node.get_tokens()]
            if "__global__" in tokens:
                body = " ".join(tokens)
                kernels.append(
                    {
                        "name": node.spelling,
                        "lines": max(1, (node.extent.end.line - node.extent.start.line)),
                        "loops": len(re.findall(r"\b(for|while|do)\b", body)),
                        "branches": len(re.findall(r"\b(if|switch)\b", body)),
                        "warp_operations": sorted(
                            set(re.findall(r"\b(__shfl_sync|__shfl|__ballot_sync|__all_sync|__any_sync|__syncthreads)\b", body))
                        ),
                        "dynamic_parallelism": bool(re.search(r"<<<[^>]+>>>", body)),
                        "shared_memory_usage": "unknown",
                    }
                )
        for child in node.get_children():
            visit(child)

    visit(tu.cursor)
    return kernels


def _parse_with_tree_sitter(code: str) -> Optional[List[Dict[str, Any]]]:
    try:
        from tree_sitter_languages import get_parser  # type: ignore
    except Exception:
        return None

    try:
        parser = get_parser("cuda")
        tree = parser.parse(code.encode("utf-8"))
    except Exception as exc:
        logger.warning("Tree-sitter parse failed: %s", exc)
        return None

    root_text = code
    captures = _regex_kernels(root_text)
    if captures:
        return captures

    logger.debug("Tree-sitter root node type: %s", tree.root_node.type)
    return []


def parse_cuda_file(filepath: str) -> Dict[str, Any]:
    """Parse CUDA file and return structured analysis JSON-compatible dict."""
    code = _read_file(filepath)

    kernels_raw = _parse_with_clang(filepath)
    parse_method = "clang"

    if kernels_raw is None:
        kernels_raw = _parse_with_tree_sitter(code)
        parse_method = "tree-sitter"

    if kernels_raw is None:
        kernels_raw = _regex_kernels(code)
        parse_method = "regex"

    kernels = [extract_kernel_info(kernel) for kernel in kernels_raw]

    api_calls = _extract_api_calls(code)
    texture_ops = sorted(set(re.findall(r"\b(tex\w+|surf\w+)\b", code)))
    uses_constant = bool(re.search(r"\b__constant__\b", code))
    uses_global = bool(re.search(r"\b__device__\b", code))

    result: Dict[str, Any] = {
        "file": Path(filepath).name,
        "parse_method": parse_method,
        "kernels": [
            {
                **asdict(kernel),
                "incompatible_patterns": [asdict(w) for w in kernel.incompatible_patterns],
            }
            for kernel in kernels
        ],
        "api_calls": api_calls,
        "memory_patterns": {
            "shared_memory": any(k.shared_memory_usage != "0 bytes" for k in kernels),
            "global_memory": uses_global,
            "constant_memory": uses_constant,
        },
        "texture_surface_ops": texture_ops,
        "dynamic_parallelism": any(k.dynamic_parallelism for k in kernels),
        "complexity": int(sum(k.complexity_score for k in kernels) / max(len(kernels), 1)),
    }

    json.dumps(result)
    return result
