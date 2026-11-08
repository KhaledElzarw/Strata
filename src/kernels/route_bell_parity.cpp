// route_bell_parity - sm86 lab STRATA_ROUTE_BELL (#3): native_router_top10_bell against the two launches it replaces,
// native_router_top10 (one token) / native_router_top10_multi and doorbell_publish_res (ring incremented) /
// doorbell_publish_res_store (ring stored), bitwise: ids, weights, the mapped ids, the mapped MoE input and the ring.
// Every token count 1..8, the exact and the REDUX top-10, random and adversarial logits (ties, all equal, +-0, NaN,
// +-inf, all -inf), residency tables with no / some / all misses and none at all.  GPU, synthetic, no model.
#include "strata/kernels/elementwise.hpp"
#include "strata/kernels/native_router.hpp"

#include <cuda_runtime.h>

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <random>
#include <vector>

namespace k = strata::kernels;

#define CK(x) do { cudaError_t e_ = (x); if (e_ != cudaSuccess) { std::fprintf(stderr, "%s: %s\n", #x, cudaGetErrorString(e_)); std::exit(2); } } while (0)

namespace {
constexpr int NE = 512, KK = 10, N = 2560, MAXT = 8;

// pattern 0 random, 1 coarse ties, 2 all equal, 3 special values, 4 a token of -inf and one of +-0 only, 5 tiny spread
void fill_logits(std::vector<float>& lg, int n_tok, int pattern, std::mt19937& rng) {
    std::normal_distribution<float> nd(0.f, 2.f);
    std::uniform_int_distribution<int> pick(0, NE - 1);
    const float inf = std::numeric_limits<float>::infinity(), nan = std::numeric_limits<float>::quiet_NaN();
    for (int t = 0; t < n_tok; ++t) {
        float* l = lg.data() + (size_t) t * NE;
        for (int e = 0; e < NE; ++e) {
            const float v = nd(rng);
            switch (pattern) {
                case 1: l[e] = std::round(v * 2.f) / 2.f; break;
                case 2: l[e] = 0.75f; break;
                case 5: l[e] = 1.0f + v * 1.e-6f; break;
                default: l[e] = v;
            }
        }
        if (pattern == 3) {
            for (int q = 0; q < 6; ++q) l[pick(rng)] = -0.0f;
            for (int q = 0; q < 6; ++q) l[pick(rng)] = 0.0f;
            if (t % 4 == 1) l[pick(rng)] = nan;
            if (t % 4 == 2) l[pick(rng)] = inf;
            for (int q = 0; q < 20; ++q) l[pick(rng)] = -inf;
            if (t % 4 == 3) { l[pick(rng)] = -nan; l[pick(rng)] = inf; l[pick(rng)] = inf; }
        }
        if (pattern == 4) {
            if (t % 2 == 0) for (int e = 0; e < NE; ++e) l[e] = -inf;
            else for (int e = 0; e < NE; ++e) l[e] = (e % 3 == 0) ? -0.0f : 0.0f;
        }
    }
}
}  // namespace

int main(int argc, char** argv) {
    (void) argc; (void) argv;
    cudaStream_t s;
    CK(cudaStreamCreate(&s));
    float *dlog, *dx, *dwa, *dwb;
    int32_t *dia, *dib, *dres;
    CK(cudaMalloc((void**) &dlog, (size_t) MAXT * NE * 4));
    CK(cudaMalloc((void**) &dx, (size_t) MAXT * N * 4));
    CK(cudaMalloc((void**) &dwa, (size_t) MAXT * KK * 4));
    CK(cudaMalloc((void**) &dwb, (size_t) MAXT * KK * 4));
    CK(cudaMalloc((void**) &dia, (size_t) MAXT * KK * 4));
    CK(cudaMalloc((void**) &dib, (size_t) MAXT * KK * 4));
    CK(cudaMalloc((void**) &dres, NE * 4));
    // mapped outputs, one set per path: the MoE input, the ids, the ring
    float *hxa, *hxb, *mxa, *mxb;
    int32_t *hia, *hib, *mia, *mib;
    uint32_t *hsa, *hsb, *msa, *msb;
    CK(cudaHostAlloc((void**) &hxa, (size_t) MAXT * N * 4, cudaHostAllocMapped));
    CK(cudaHostAlloc((void**) &hxb, (size_t) MAXT * N * 4, cudaHostAllocMapped));
    CK(cudaHostAlloc((void**) &hia, (size_t) MAXT * KK * 4, cudaHostAllocMapped));
    CK(cudaHostAlloc((void**) &hib, (size_t) MAXT * KK * 4, cudaHostAllocMapped));
    CK(cudaHostAlloc((void**) &hsa, 64, cudaHostAllocMapped));
    CK(cudaHostAlloc((void**) &hsb, 64, cudaHostAllocMapped));
    CK(cudaHostGetDevicePointer((void**) &mxa, hxa, 0));
    CK(cudaHostGetDevicePointer((void**) &mxb, hxb, 0));
    CK(cudaHostGetDevicePointer((void**) &mia, hia, 0));
    CK(cudaHostGetDevicePointer((void**) &mib, hib, 0));
    CK(cudaHostGetDevicePointer((void**) &msa, hsa, 0));
    CK(cudaHostGetDevicePointer((void**) &msb, hsb, 0));

    std::mt19937 rng(20261109);
    std::normal_distribution<float> nd(0.f, 1.f);
    std::uniform_real_distribution<float> ud(0.f, 1.f);
    std::vector<float> lg((size_t) MAXT * NE), xh((size_t) MAXT * N);
    std::vector<int32_t> res(NE);
    size_t cases = 0, bad_cases = 0, values = 0;
    for (int fast = 0; fast < 2; ++fast)
    for (int n_tok = 1; n_tok <= MAXT; ++n_tok)
    for (int pattern = 0; pattern < 6; ++pattern)
    for (int rmode = 0; rmode < 4; ++rmode)      // 0 no table, 1 all resident, 2 some misses, 3 all misses
    for (int store = 0; store < 2; ++store)
    for (int rep = 0; rep < 3; ++rep) {
        fill_logits(lg, n_tok, pattern, rng);
        for (auto& v : xh) v = nd(rng);
        for (int e = 0; e < NE; ++e) res[e] = rmode == 1 ? e : rmode == 3 ? -1 : (ud(rng) < 0.3f ? -1 : e);
        CK(cudaMemcpy(dlog, lg.data(), (size_t) n_tok * NE * 4, cudaMemcpyHostToDevice));
        CK(cudaMemcpy(dx, xh.data(), (size_t) n_tok * N * 4, cudaMemcpyHostToDevice));
        CK(cudaMemcpy(dres, res.data(), NE * 4, cudaMemcpyHostToDevice));
        CK(cudaMemset(dia, 0x5a, (size_t) MAXT * KK * 4)); CK(cudaMemset(dib, 0x5a, (size_t) MAXT * KK * 4));
        CK(cudaMemset(dwa, 0x5a, (size_t) MAXT * KK * 4)); CK(cudaMemset(dwb, 0x5a, (size_t) MAXT * KK * 4));
        std::memset(hxa, 0x33, (size_t) MAXT * N * 4); std::memset(hxb, 0x33, (size_t) MAXT * N * 4);
        std::memset(hia, 0x33, (size_t) MAXT * KK * 4); std::memset(hib, 0x33, (size_t) MAXT * KK * 4);
        *hsa = *hsb = 41u;
        const int32_t* r = rmode == 0 ? nullptr : dres;
        const uint32_t value = store ? 7u + (uint32_t) rep : 0u;
        const int64_t n = (int64_t) n_tok * N, kk = (int64_t) n_tok * KK;
        // the two launches
        if (n_tok == 1) k::native_router_top10(dlog, dia, dwa, s);
        else k::native_router_top10_multi(dlog, dia, dwa, n_tok, s);
        if (store) k::doorbell_publish_res_store(dx, dia, r, NE, n, kk, mxa, mia, msa, value, s);
        else k::doorbell_publish_res(dx, dia, r, NE, n, kk, mxa, mia, msa, s);
        // the one
        if (!k::native_router_top10_bell(dlog, dib, dwb, n_tok, dx, r, NE, n, mxb, mib, msb, value, fast != 0, s)) {
            std::printf("FAIL native_router_top10_bell refused n_tok %d\n", n_tok);
            return 1;
        }
        CK(cudaStreamSynchronize(s));
        std::vector<uint32_t> a((size_t) MAXT * KK), b((size_t) MAXT * KK);
        size_t bad = 0;
        CK(cudaMemcpy(a.data(), dia, a.size() * 4, cudaMemcpyDeviceToHost));
        CK(cudaMemcpy(b.data(), dib, b.size() * 4, cudaMemcpyDeviceToHost));
        for (size_t i = 0; i < a.size(); ++i) bad += a[i] != b[i];
        CK(cudaMemcpy(a.data(), dwa, a.size() * 4, cudaMemcpyDeviceToHost));
        CK(cudaMemcpy(b.data(), dwb, b.size() * 4, cudaMemcpyDeviceToHost));
        for (size_t i = 0; i < a.size(); ++i) bad += a[i] != b[i];
        bad += std::memcmp(hia, hib, (size_t) MAXT * KK * 4) != 0;
        bad += std::memcmp(hxa, hxb, (size_t) MAXT * N * 4) != 0;
        bad += *hsa != *hsb;
        values += 2 * a.size() + MAXT * KK + MAXT * N + 1;
        ++cases;
        if (bad) {
            ++bad_cases;
            if (bad_cases <= 12)
                std::printf("FAIL fast %d n_tok %d pattern %d residency %d store %d rep %d: %zu differ (ring %u / %u)\n", fast,
                            n_tok, pattern, rmode, store, rep, bad, *hsa, *hsb);
        }
    }
    std::printf("route_bell_parity: %zu cases, %zu values compared, %zu cases differ\n", cases, values, bad_cases);
    return bad_cases ? 1 : 0;
}
