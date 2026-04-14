from hip_generator import add_inline_annotations, convert_cuda_to_hip


def test_convert_cuda_to_hip_replaces_core_calls() -> None:
    cuda_code = "cudaMalloc(ptr, n); cudaMemcpy(dst, src, n, cudaMemcpyDefault);"
    hip_code = convert_cuda_to_hip(cuda_code, ["Potential warp-size mismatch"])

    assert "hipMalloc" in hip_code
    assert "hipMemcpy" in hip_code
    assert "WARNING" in hip_code


def test_add_inline_annotations_injects_tip() -> None:
    code = "__global__ void kernel() { __syncthreads(); }"
    annotated = add_inline_annotations(code, ["Check occupancy"])
    assert "TIP" in annotated
    assert "Migration Issues Summary" in annotated
