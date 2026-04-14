#include <cuda_runtime.h>
#include <stdio.h>

__global__ void matrixMulKernel(const float* A, const float* B, float* C, int N) {
    __shared__ float tileA[16][16];
    __shared__ float tileB[16][16];

    int row = blockIdx.y * blockDim.y + threadIdx.y;
    int col = blockIdx.x * blockDim.x + threadIdx.x;
    float sum = 0.0f;

    for (int t = 0; t < N / 16; ++t) {
        tileA[threadIdx.y][threadIdx.x] = A[row * N + t * 16 + threadIdx.x];
        tileB[threadIdx.y][threadIdx.x] = B[(t * 16 + threadIdx.y) * N + col];
        __syncthreads();

        for (int k = 0; k < 16; ++k) {
            sum += tileA[threadIdx.y][k] * tileB[k][threadIdx.x];
        }
        __syncthreads();
    }

    C[row * N + col] = sum;
}
