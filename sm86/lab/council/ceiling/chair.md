# Chair's own estimate (written before reading any member)

## Bytes a verify window must move (q3, T 3.93, 3.25 tokens a window; engine log + prof8)
- Dense weights read once a window: pack 1466 MiB (HC bf16 97 reads x 13.1 MB = 1.27 GB, router, norms) + 300 native
  projections 2069 MiB (attention / GDN projections, shared experts, LM head) = 3.45 GiB = 3.70 GB.
- VRAM expert hits: 32.4 entries a layer-window, ~0.7 distinct per entry (CPU ratio 2.78 / 3.98) -> ~22.6 experts x 48
  x 1.66 MiB (arena 39.97 GiB / 24,576) = 1.93 GB.
- CPU experts: 2.78 distinct a layer-window x 48 x 1.66 MiB = 232 MB (measured 4.96 ms -> 47 GB/s, ~78% of ~60 GB/s).
- Drafter: 591 MiB Q4_0 (~0.62 GB) a draft pass; measured draft 1.50 ms.

## Critical path model (nsys q3: per layer, GPU chain combine->doorbell, then an expert region the CPU bounds:
## GPU work in it ends at 88 us, the CPU flag at 105 us, nsys-inflated)
window = sum_l [chain_l + max(cpu_l, gpu_experts_l)] + head/sampling + draft
- Theoretical (936 GB/s, 60 GB/s CPU, no overheads): chain 3.5 GB -> 3.7 ms; expert region max(3.9, 2.3) = 3.9 ms;
  draft 0.7 ms -> 8.3 ms -> 3.25 / 8.3 ms = ~390 tok/s.
- Practical floor (GPU 80% of peak, CPU 85% of 60 GB/s, 8 us a layer of handoffs, draft 1.0): 4.7 + 4.6 + 0.4 + 0.2 +
  1.0 = 10.9 ms -> ~300 tok/s. Needs every kernel near the floor: not a realistic engineering target.
- Realistic with this architecture: chain 11.0 -> ~7 ms (fusion of the ~45 kernels a layer, router/plan/bell, HC),
  expert region ~5.3 -> ~4.8, draft 1.5 -> 1.2 -> ~13.6 ms -> ~240 tok/s.

## Today: 18.87 ms a window (DECODE_TIMING estimate 172 tok/s; A/B round medians 162-170 on real turns)
- 200 tok/s = 16.25 ms (-2.6 ms, -14%). Candidates on the critical path: router+plan+bell 0.84 -> ~0.3 (-0.5); HC 3.38
  -> ~2.8 in situ (-0.5; RES got only -0.15); kernel fusion in the GDN/attention/norm chain (-0.5..1.0); CPU share
  over CPU + PCIe in parallel (-0.5..1.0: the region is CPU-bound, 60 + 26.8 GB/s); per-layer handoffs (-0.3).
  Shared expert (1.2) and VRAM hits (3.4) sit in the CPU-bound region: faster kernels there gain ~0.
  My confidence: ~50% (history: hc86 -0.4 ms, tier5 -0.7 ms, RES -0.15 ms in situ; each step shrinks in the engine).
- 250 tok/s = 13.0 ms (-5.9 ms, -31%): needs nearly every item above at full value plus a CPU path below its
  bandwidth floor or more tokens a window (a better drafter). My confidence: ~10%.
- More tokens a window is the other lever: tokens/window scales tok/s 1:1 (window cost grows little with T).

## Prefill (to fill in with coldbench)
Measured (coldbench q3, 2026-11-08): cold 4K 1,956-2,219 tok/s; 16K 2,882-2,931; 32K 2,878-2,946; 64K 3,119-3,125.
Warm real turns: median 842 ms (505 ms fixed + 0.404 ms/new token).
FLOPs a token (GGUF dims: experts 10 x 3 x 2560 x 640, shared 640, GDN qkv 2560x10240 + gate 2560x6144 + out
6144x2560 on 36 layers, QSA q 2560x12288 + out 6144x2560 on 12, top-k 2048 attention, HC 97 x 6.55M MACs) ~13 GFLOP.
32K cold trace: GPU 10.88 s = experts 2.66 s (24%) + HC 1.98 (18%) + QSA 1.81 (17%) + GDN 1.58 (14.5%) + PCIe wait
0.45 (4%) + other -> ~40 TFLOPS effective vs 284 int8 / 71 bf16 TOPS peaks: compute- and kernel-bound, not PCIe.
- Cold long: practical floor ~5,500-6,500 tok/s (MMQ at ~45% of int8 peak, HC at ~70% of bf16); theoretical ~15K.
- Cold 4K: ~4,000 tok/s floor (one PCIe pass over the 26 GB of non-resident experts, ~1 s; compute ~0.7 s).
- Warm turn: ~0.40-0.45 s floor (the routed non-resident experts over PCIe + CPU in parallel, ~0.3 s, + compute).

## Correction after checking the RAM (2 x 64 GB DDR5-5600, dual channel = 89.6 GB/s theoretical, ~70-75 practical)
- The CPU pool moves 232 MB in 4.96 ms = 47 GB/s: ~55-65% of what the RAM can do, and it bounds the expert region.
  At 65 GB/s the region would fall from ~103 to ~75 us a layer, near the GPU's own work in it: -0.7..1.4 ms a window.
- Ceilings redone: theoretical (936 GB/s GPU, 89.6 CPU + 26.8 PCIe for misses, no overheads) ~7.0 ms a window ->
  ~460 tok/s; practical floor (85% GPU, 75 GB/s CPU, 0.7 ms overheads) ~8.6 ms -> ~380 tok/s; realistic for an
  excellent engine of this design (fused chain ~7 ms, region ~3.5-4, draft 1.2, 0.5 other) ~12.5 ms -> ~260 tok/s.
- Today (A/B medians ~166, DECODE_TIMING 172): ~36% of theoretical, ~45% of the practical floor, ~65% of realistic.
