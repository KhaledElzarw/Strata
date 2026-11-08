// bwbench.cpp - DRAM read bandwidth: steady state, and in short per-layer bursts like the CPU expert pool's (N pinned
// threads split B bytes of memory no cache holds, spin barrier, optional 230 us idle gap like the GPU's dense chain of a
// layer, next burst). Threads are pinned to even logical CPUs, as the engine pins the pool (host 0, workers 2..30).
// Build (VS 2022 x64 developer prompt): cl /O2 /EHsc /arch:AVX512 bwbench.cpp     Run: bwbench.exe > runs/bw/NAME.txt
// Needs AVX-512 and 6 GiB of free RAM. Result on the test machine: runs/bw/bwbench-9950x-ddr5-5600.txt.
#include <immintrin.h>
#include <windows.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>

using clk = std::chrono::steady_clock;
static const size_t BUF = size_t(6) << 30;   // 6 GiB: every burst reads memory no cache holds
static char* g_buf = nullptr;

// Unaligned-safe loads; every range starts on a 256-byte boundary anyway (bursts are page multiples, slices 256-byte).
static inline __m512i read_range(const char* p, size_t n, __m512i acc) {
    for (size_t i = 0; i + 256 <= n; i += 256) {
        acc = _mm512_xor_si512(acc, _mm512_loadu_si512((const void*)(p + i)));
        acc = _mm512_xor_si512(acc, _mm512_loadu_si512((const void*)(p + i + 64)));
        acc = _mm512_xor_si512(acc, _mm512_loadu_si512((const void*)(p + i + 128)));
        acc = _mm512_xor_si512(acc, _mm512_loadu_si512((const void*)(p + i + 192)));
    }
    return acc;
}

struct Barrier {   // sense-reversing spin barrier (the pool's workers spin between phases in decode)
    std::atomic<int> count{0};
    std::atomic<int> sense{0};
    int n;
    explicit Barrier(int n_) : n(n_) {}
    void wait(int& local) {
        local ^= 1;
        if (count.fetch_add(1, std::memory_order_acq_rel) == n - 1) {
            count.store(0, std::memory_order_relaxed);
            sense.store(local, std::memory_order_release);
        } else {
            while (sense.load(std::memory_order_acquire) != local) _mm_pause();
        }
    }
};

static void spin_us(double us) {
    const auto end = clk::now() + std::chrono::nanoseconds(int64_t(us * 1000));
    while (clk::now() < end) _mm_pause();
}

// One configuration: threads pinned to cpus[], bursts of `burst` bytes (0 = one steady pass over the buffer).
static double run(const std::vector<int>& cpus, size_t burst, double gap_us, int bursts, double* burst_us_out) {
    const int n = (int)cpus.size();
    Barrier bar(n);
    std::atomic<uint64_t> sink{0};
    std::vector<double> busy(n, 0.0);
    double wall = 0.0;
    auto body = [&](int t) {
        SetThreadAffinityMask(GetCurrentThread(), DWORD_PTR(1) << cpus[t]);
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_HIGHEST);
        int sense = 0;
        __m512i acc = _mm512_setzero_si512();
        bar.wait(sense);
        if (burst == 0) {   // steady: each thread one contiguous slice of the whole buffer
            const size_t slice = (BUF / n) & ~size_t(4095);
            auto t0 = clk::now();
            acc = read_range(g_buf + t * slice, slice, acc);
            bar.wait(sense);
            if (t == 0) wall = std::chrono::duration<double, std::micro>(clk::now() - t0).count();
        } else {
            const size_t slice = (burst / n) & ~size_t(255);
            size_t base = 0;
            double in_bursts = 0.0;
            for (int b = 0; b < bursts; ++b) {
                if (base + burst > BUF) base = 0;
                auto t0 = clk::now();
                acc = read_range(g_buf + base + t * slice, slice, acc);
                bar.wait(sense);   // the layer's CPU step ends when the last thread is done
                if (t == 0) in_bursts += std::chrono::duration<double, std::micro>(clk::now() - t0).count();
                base += burst;
                if (gap_us > 0) spin_us(gap_us);   // the GPU's dense chain of the next layer: the pool idles
                bar.wait(sense);
            }
            if (t == 0) wall = in_bursts;
        }
        alignas(64) uint64_t lanes[8];
        _mm512_store_si512((void*)lanes, acc);
        sink.fetch_add(lanes[0] ^ lanes[7]);
    };
    std::vector<std::thread> th;
    for (int t = 1; t < n; ++t) th.emplace_back(body, t);
    body(0);
    for (auto& x : th) x.join();
    const double bytes = burst == 0 ? double((BUF / n) & ~size_t(4095)) * n : double((burst / n) & ~size_t(255)) * n * bursts;
    if (burst_us_out) *burst_us_out = burst == 0 ? wall : wall / bursts;
    return bytes / (wall * 1e3);   // GB/s
}

int main() {
    g_buf = (char*)VirtualAlloc(nullptr, BUF, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!g_buf) { std::printf("alloc failed\n"); return 1; }
    for (size_t i = 0; i < BUF; i += 4096) g_buf[i] = char(i >> 12);   // fault every page in
    struct Cfg { const char* name; std::vector<int> cpus; };
    auto even = [](int lo, int count) { std::vector<int> v; for (int i = 0; i < count; ++i) v.push_back(lo + 2 * i); return v; };
    std::vector<Cfg> cfgs = {
        {"1 core", {0}},
        {"4 cores CCD0", even(0, 4)},
        {"8 cores CCD0", even(0, 8)},
        {"8 cores CCD1", even(16, 8)},
        {"8 = 4+4 CCDs", {0, 2, 4, 6, 16, 18, 20, 22}},
        {"12 = 6+6", {0, 2, 4, 6, 8, 10, 16, 18, 20, 22, 24, 26}},
        {"16 = pool", even(0, 16)},   // host on 0 + 15 workers on 2..30, as the engine pins them
    };
    std::printf("%-14s %10s | %s\n", "threads", "steady", "bursts: size -> us per burst, GB/s (gap 0 | gap 230 us)");
    for (auto& c : cfgs) {
        run(c.cpus, 0, 0, 0, nullptr);   // warm
        double steady = 0; for (int r = 0; r < 2; ++r) { double g = run(c.cpus, 0, 0, 0, nullptr); if (g > steady) steady = g; }
        std::printf("%-14s %7.1f GB/s |", c.name, steady);
        for (size_t mb10 : {10, 25, 48, 70, 160}) {   // 1.0, 2.5, 4.8, 7.0, 16 MB
            const size_t burst = (mb10 * (size_t(1) << 20) / 10) & ~size_t(4095);   // a page multiple: every burst starts aligned
            double us0, us1;
            double g0 = run(c.cpus, burst, 0, 400, &us0);
            double g1 = run(c.cpus, burst, 230, 200, &us1);
            std::printf(" %4.1fMB %6.1f/%5.1f | %6.1f/%5.1f;", mb10 / 10.0, us0, g0, us1, g1);
        }
        std::printf("\n");
        std::fflush(stdout);
    }
    VirtualFree(g_buf, 0, MEM_RELEASE);
    return 0;
}
