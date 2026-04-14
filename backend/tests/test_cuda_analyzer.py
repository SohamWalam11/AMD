from pathlib import Path

from cuda_analyzer import parse_cuda_file


def test_parse_cuda_file_detects_kernel_and_calls(tmp_path: Path) -> None:
    cuda_source = '''
#include <cuda_runtime.h>

__global__ void matrixMulKernel(float* a, float* b, float* c) {
    __shared__ float tile[16][16];
    int x = threadIdx.x;
    if (x < 16) {
        __syncthreads();
    }
}

int main() {
    float *d_a, *d_b;
    cudaMalloc(&d_a, 1024);
    cudaMemcpy(d_b, d_a, 1024, cudaMemcpyDeviceToDevice);
    return 0;
}
'''
    fp = tmp_path / "matrix_mul.cu"
    fp.write_text(cuda_source, encoding="utf-8")

    result = parse_cuda_file(str(fp))

    assert result["file"] == "matrix_mul.cu"
    assert result["kernels"]
    assert result["kernels"][0]["name"] == "matrixMulKernel"
    assert "cudaMalloc" in result["api_calls"]["memory"]
