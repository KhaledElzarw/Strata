// sm86/lab/pool_replay_bench.cpp - the CPU expert pool on a recorded decode: the CPU jobs of a STRATA_ROUTE_DUMP file
// (every layer-window's misses, res 0, with its token count) run through the engine's own ExpertPool::run_split_multi_native,
// on each layer's real formats (the pack's native_experts.txt), with synthetic ggml-quantized weights in cold DRAM.  No GPU.
// Per layer it prints the pool's phases (gate/up, the host quantization, down) in microseconds and the weight GB/s, and a
// hash of every output row, so a pool variant (an env switch, --tasks) can be timed against the default and checked bit
// for bit in a few minutes.  Between layers the host spins --gap-us (the GPU's part of a layer; the workers spin with it).
//
//     pool_replay_bench <route dump> [--pack <checkout>/packs/iq3_xxs] [--windows 2000] [--skip 200] [--gap-us 230]
//                       [--workers 15] [--tasks 0] [--slots 128] [--reps 1] [--uniq 1]
//
// --slots: blobs per layer (expert e uses slot e % slots), 128 = ~11 GB, far past the L3; --uniq: distinct weight sets a
// format (copied over the slots; the values do not change the time, and ggml's i-quant quantizers are slow); --skip: windows
// dropped from the start (the warm-up request).  A job is at most 8 tokens (MAXT), as in expert_source.cpp.
#include "strata/kernels/cpu/pool.hpp"
#include "strata/kernels/cpu/native_expert.hpp"
#include "strata/kernels/cpu/expert.hpp"
#include "strata/kernels/cpu/expert_layout.hpp"

#include "ggml.h"
#include "ggml-cpu.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <memory>
#include <random>
#include <sstream>
#include <string>
#include <vector>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#endif

namespace cpu = strata::kernels::cpu;

namespace {

constexpr int64_t kH = 2560, kFF = 640;

struct Job { int e, nt; };
struct LayerWindow { int layer; std::vector<Job> jobs; };

void make_blob(const cpu::NativeFmt& f, uint8_t* blob, std::mt19937& rng) {   // as kq_cpu_bench: valid scales
    std::normal_distribution<float> nd(0.f, 0.02f);
    std::vector<float> row((size_t) std::max(kH, kFF));
    const std::vector<float> imatrix((size_t) std::max(kH, kFF), 1.0f);
    auto quant = [&](int type, uint8_t* dst, int64_t n) {
        ggml_quantize_chunk((ggml_type) type, row.data(), dst, 0, 1, n,
                            ggml_quantize_requires_imatrix((ggml_type) type) ? imatrix.data() : nullptr);
    };
    for (int64_t r = 0; r < 2 * kFF; ++r) {
        for (int64_t i = 0; i < kH; ++i) row[(size_t) i] = nd(rng);
        quant(f.gu_type, blob + (r < kFF ? (size_t) r * f.gu_row : f.up_off + (size_t) (r - kFF) * f.gu_row), kH);
    }
    for (int64_t r = 0; r < kH; ++r) {
        for (int64_t i = 0; i < kFF; ++i) row[(size_t) i] = nd(rng);
        quant(f.d_type, blob + f.down_off + (size_t) r * f.d_row, kFF);
    }
}

}  // namespace

int main(int argc, char** argv) {
    setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc < 2) { std::fprintf(stderr, "usage: pool_replay_bench <route dump> [--pack dir] [--windows N] [--skip N] [--gap-us N] [--workers N] [--tasks N] [--slots N] [--reps N]\n"); return 2; }
    std::string dump = argv[1], pack = "packs/iq3_xxs";
    int windows = 2000, skip = 200, gap_us = 230, workers = 15, tasks = 0, slots = 128, reps = 1, uniq_n = 1;
    for (int i = 2; i + 1 < argc; i += 2) {
        const std::string a = argv[i];
        const int v = std::atoi(argv[i + 1]);
        if (a == "--pack") pack = argv[i + 1];
        else if (a == "--windows") windows = v;
        else if (a == "--skip") skip = v;
        else if (a == "--gap-us") gap_us = v;
        else if (a == "--workers") workers = v;
        else if (a == "--tasks") tasks = v;
        else if (a == "--slots") slots = std::max(1, v);
        else if (a == "--reps") reps = std::max(1, v);
        else if (a == "--uniq") uniq_n = std::max(1, v);
        else { std::fprintf(stderr, "unknown option %s\n", a.c_str()); return 2; }
    }
    ggml_cpu_init();
    // the layers' formats
    std::map<int, std::pair<int, int>> types;
    {
        std::ifstream in(pack + "/native_experts.txt");
        std::string line;
        while (std::getline(in, line)) {
            if (line.empty() || line[0] == '#') continue;
            std::istringstream ss(line);
            int l, gu, d;
            if (ss >> l >> gu >> d) types[l] = {gu, d};
        }
    }
    if (types.empty()) { std::fprintf(stderr, "no layers in %s/native_experts.txt\n", pack.c_str()); return 1; }
    // the recorded CPU jobs: windows break where the layer index stops increasing (routestats.py)
    std::vector<std::vector<LayerWindow>> W;
    {
        std::ifstream in(dump);
        std::string line;
        std::vector<LayerWindow> cur;
        int last = -1;
        while (std::getline(in, line)) {
            const size_t bar = line.find('|');
            if (bar == std::string::npos) continue;
            std::istringstream hs(line.substr(0, bar));
            int layer, ntok, nd, nmiss;
            if (!(hs >> layer >> ntok >> nd >> nmiss)) continue;
            if (last >= 0 && layer <= last && !cur.empty()) {
                W.push_back(std::move(cur));
                cur.clear();
                if ((int) W.size() >= skip + windows) break;
            }
            last = layer;
            LayerWindow lw{layer, {}};
            std::istringstream ts(line.substr(bar + 1));
            std::string tok;
            while (ts >> tok) {
                int e, rows, res;
                if (std::sscanf(tok.c_str(), "%d:%d:%d", &e, &rows, &res) != 3 || res != 0) continue;
                for (int left = rows; left > 0; left -= cpu::MAXT) lw.jobs.push_back({e, std::min(left, cpu::MAXT)});
            }
            cur.push_back(std::move(lw));
        }
        if (!cur.empty() && (int) W.size() < skip + windows) W.push_back(std::move(cur));
    }
    if ((int) W.size() <= skip) { std::fprintf(stderr, "only %zu windows in the dump\n", W.size()); return 1; }
    W.erase(W.begin(), W.begin() + skip);
    // formats, blobs (slots per layer, 4 distinct per type pair, copied), activations per type pair
    std::map<std::pair<int, int>, cpu::NativeFmt> fmts;
    std::map<std::pair<int, int>, std::vector<uint8_t>> uniq;
    std::map<std::pair<int, int>, std::vector<std::vector<uint8_t>>> nacts;
    std::vector<cpu::ActQ> qact(cpu::MAXT);
    std::mt19937 rng(4242);
    std::normal_distribution<float> nd(0.f, 1.f);
    std::vector<std::vector<float>> xs(cpu::MAXT, std::vector<float>(kH));
    for (auto& x : xs) for (auto& v : x) v = nd(rng);
    for (int t = 0; t < cpu::MAXT; ++t) cpu::act_quant_any(xs[t].data(), (int) kH, qact[t]);
    for (const auto& [l, td] : types) {
        if (fmts.count(td)) continue;
        cpu::NativeFmt f;
        std::string err;
        if (!cpu::native_fmt(td.first, td.second, kH, kFF, f, err)) { std::fprintf(stderr, "layer %d: %s\n", l, err.c_str()); return 1; }
        ggml_quantize_init((ggml_type) td.first);
        ggml_quantize_init((ggml_type) td.second);
        std::vector<uint8_t> u((size_t) uniq_n * f.bytes);
        for (int k = 0; k < uniq_n; ++k) make_blob(f, u.data() + (size_t) k * f.bytes, rng);
        uniq[td] = std::move(u);
        auto& na = nacts[td];
        na.assign(cpu::MAXT, std::vector<uint8_t>(cpu::kNativeActBytes));
        for (int t = 0; t < cpu::MAXT; ++t) cpu::native_quant_act(f, xs[t].data(), na[t].data());
        fmts[td] = f;
    }
    std::map<int, uint8_t*> base;
    std::vector<std::unique_ptr<uint8_t[]>> mem;
    double total_mb = 0;
    for (const auto& [l, td] : types) {
        const cpu::NativeFmt& f = fmts[td];
        mem.emplace_back(new uint8_t[(size_t) slots * f.bytes + 4096]);
        uint8_t* b = (uint8_t*) (((uintptr_t) mem.back().get() + 4095) & ~(uintptr_t) 4095);
        for (int s = 0; s < slots; ++s) std::memcpy(b + (size_t) s * f.bytes, uniq[td].data() + (size_t) (s % uniq_n) * f.bytes, f.bytes);
        base[l] = b;
        total_mb += (double) slots * f.bytes / 1e6;
    }
#ifdef _WIN32
    const int host = cpu::planned_host_core(cpu::PoolAffinity::All);
    if (host >= 0 && host < 64) SetThreadAffinityMask(GetCurrentThread(), (DWORD_PTR) 1 << host);
#endif
    cpu::ExpertPool pool(workers, true, true, cpu::PoolAffinity::All, tasks);
    std::printf("pool_replay_bench: %s, %zu windows (skipped %d), %.0f MB of blobs (%d slots a layer), gap %d us, %s, tasks %d\n",
                cpu::cpu_name().c_str(), W.size(), skip, total_mb, slots, gap_us, pool.placement_line().c_str(), tasks);
    std::vector<cpu::ExpertJobMulti> jobs((size_t) cpu::ExpertPool::kMaxSplitMulti * 2);
    std::vector<float> out((size_t) jobs.size() * cpu::MAXT * kH);
    auto spin = [](int us) {
        const auto until = std::chrono::steady_clock::now() + std::chrono::microseconds(us);
        while (std::chrono::steady_clock::now() < until) {}
    };
    for (int rep = 0; rep < reps; ++rep) {
        const double gu0 = pool.ms_multi_gu, q0 = pool.ms_multi_q, d0 = pool.ms_multi_down, dag0 = pool.ms_multi_dag;
        double call_ms = 0, gu_bytes = 0, d_bytes = 0;
        int64_t calls = 0, njobs = 0, entries = 0, lw_total = 0;
        uint64_t fnv = 1469598103934665603ull;
        for (const auto& win : W) {
            for (const LayerWindow& lw : win) {
                ++lw_total;
                spin(gap_us);
                if (lw.jobs.empty()) continue;
                const auto td = types.at(lw.layer);
                const cpu::NativeFmt& f = fmts[td];
                const auto& na = nacts[td];
                const int n = (int) std::min<size_t>(lw.jobs.size(), jobs.size());
                for (int j = 0; j < n; ++j) {
                    cpu::ExpertJobMulti& jb = jobs[(size_t) j];
                    jb = cpu::ExpertJobMulti{};
                    jb.blob = base[lw.layer] + (size_t) (lw.jobs[(size_t) j].e % slots) * f.bytes;
                    jb.nt = lw.jobs[(size_t) j].nt;
                    for (int t = 0; t < jb.nt; ++t) {
                        jb.act[t] = &qact[(size_t) t];
                        jb.nact[t] = na[(size_t) t].data();
                        jb.out[t] = out.data() + ((size_t) j * cpu::MAXT + t) * kH;
                    }
                    entries += jb.nt;
                    gu_bytes += (double) f.down_off;
                    d_bytes += (double) (f.bytes - f.down_off);
                }
                const auto a = std::chrono::steady_clock::now();
                pool.run_split_multi_native(f, jobs.data(), n);
                call_ms += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - a).count();
                ++calls;
                njobs += n;
                for (int j = 0; j < n; ++j)
                    for (int t = 0; t < jobs[(size_t) j].nt; ++t) {
                        const uint8_t* p = reinterpret_cast<const uint8_t*>(jobs[(size_t) j].out[t]);
                        for (size_t i = 0; i < (size_t) kH * 4; i += 4) {   // every row's bits (4 bytes at a time)
                            uint32_t w;
                            std::memcpy(&w, p + i, 4);
                            fnv = (fnv ^ w) * 1099511628211ull;
                        }
                    }
            }
        }
        const double gu = pool.ms_multi_gu - gu0, q = pool.ms_multi_q - q0, dn = pool.ms_multi_down - d0, dag = pool.ms_multi_dag - dag0;
        const double nw = (double) W.size(), c = (double) std::max<int64_t>(calls, 1);
        std::printf("rep %d: %lld layer calls of %lld layer-windows, %.2f experts and %.2f entries a call\n", rep, (long long) calls,
                    (long long) lw_total, njobs / c, entries / c);
        std::printf("  per call: total %.1f us = gate/up %.1f + quantize %.2f + down %.1f%s (us)\n", 1e3 * call_ms / c, 1e3 * gu / c,
                    1e3 * q / c, 1e3 * dn / c, dag > 0 ? (" + dag " + std::to_string(1e3 * dag / c)).c_str() : "");
        if (gu > 0 && dn > 0)
            std::printf("  gate/up %.1f GB/s, down %.1f GB/s; whole call %.1f GB/s\n", gu_bytes / (gu * 1e6), d_bytes / (dn * 1e6),
                        (gu_bytes + d_bytes) / (call_ms * 1e6));
        else
            std::printf("  whole call %.1f GB/s\n", (gu_bytes + d_bytes) / (call_ms * 1e6));
        std::printf("  per window: %.3f ms of pool calls (%.1f calls)\n", call_ms / nw, calls / nw);
        std::printf("  hash %016llx\n", (unsigned long long) fnv);
    }
    return 0;
}
