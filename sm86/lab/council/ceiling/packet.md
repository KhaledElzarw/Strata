# Council question: how far can this engine go on this machine?

You are a senior GPU / inference-systems engineer giving an independent, evidence-based estimate. Read-only: no edits,
no builds, no benchmarks. Use the evidence below (and, if you have the checkout C:\src\Strata, its code) and show your
arithmetic. Be calibrated: a confident number with no arithmetic behind it is worth nothing here.

## The questions
1. Your confidence (0-100%) that **200 tok/s** median decode over replayed real agent turns is reachable on this
   machine under the quality rules below (bit-identical or rounding-level changes only, no lossy changes).
2. The same for **250 tok/s**.
3. The **absolute ceiling** for decode on this hardware and model under the same rules: a theoretical bound (name the
   bounding resource and do the byte / time arithmetic per verify window) and the practical ceiling you think an
   excellent engine could actually reach. Say how far today's number is from each.
4. **Prefill**: what bounds today's cold-prompt and warm-turn prompt times (measured below), the floor for each, and
   the top 1-3 changes toward it with predicted gains.

## Answer format (findings only, no praise)
```
CONFIDENCE 200: n% - why, with the 2-5 changes that would get there, each with a predicted saving in ms per window
                ON THE CRITICAL PATH (see the concurrency evidence) and why that prediction would hold in the engine
CONFIDENCE 250: n% - same
CEILING: theoretical N tok/s (bound + arithmetic); practical M tok/s (what limits it); today = x% / y% of them
PREFILL: cold now / floor (bound + arithmetic); warm turn now / floor; top changes with predicted gains
WHAT WOULD CHANGE MY MIND: the measurement that would move your numbers most
UNCERTAIN: what you could not verify, and the evidence that would settle it
```

## Goal and rules (the owner, word for word where quoted)
- Goal: the abliterated Qwen3.8-Flash-Next (SC117 GSQ-RCO IQ3_XXS GGUF) on the Strata engine (C++/CUDA fork, local
  branch) on one RTX 3090 at 175-200 tok/s median decode over real agent turns (175 is the floor), context 262,144,
  "no quality loss"; prefill counts too (the median prompt time per real agent turn).
- "use whatever method as long as it doesn't impact quality"
- Quality tiers: A = bit-identical (kernel hashes + whole-engine forced-text logits identical) -> keep if faster.
  B = rounding-level (same math and precision, another summation order) -> keep if faster AND a crossed, slot-pinned
  force_check passes. C = lossy (requantization, skipping work, lower precision KV, route-tail skipping) -> not allowed
  without the owner's decision; treat it as out of scope here.
- GPU core at or below 75-78 C (390 W power cap today; the 3090 sits at the cap under load).
- Adoption rule for a change: an A/B on replayed real turns with a >= 2% paired gain whose CI excludes 1.

## Machine
- RTX 3090 (GA102, sm_86, 82 SMs, 936 GB/s GDDR6X, 6 MB L2, 24 GB; Windows WDDM caps one process at ~23,556 MiB),
  Ryzen 9 9950X (Zen 5, 16 cores, AVX-512), 125 GB DDR5 (~60 GB/s measured for the expert pool), PCIe 4.0 x16
  (26.8 GB/s host->device measured by the engine's probe), Windows 11, large pages on for the 40 GiB expert arena.
- Measured cold plain-read floor on this card: a 6.55 MB read takes 10.2 us (645 GB/s) in a simple probe kernel.

## Model and engine facts (from the engine's own startup log, this build)
- 48 layers: 36 gated-delta-net (linear attention) layers and 12 QSA (sparse attention) layers; hidden 2560;
  hyper-connections with 4 streams (D = 10240, low rank 320): two HC reads per layer plus one final (97 reads per
  verify window), each reading W_down 320x10240 + W_up 10240x320 in BF16 (13.1 MB per read).
- MoE: 512 routed experts per layer (10 active) + a shared expert. 24,576 routed experts, expert arena 39.97 GiB in
  pinned host RAM (largest blob 2.33 MB; mean ~1.66 MiB per expert), IQ3_XXS-class weights.
- Dense weights on the GPU: 1466 MiB from the pack (HC BF16 weights, router, norms) + 300 native projection matrices
  2069 MiB (attention / GDN projections, shared experts, LM head). Token embedding IQ3_S in mapped host memory.
- VRAM expert cache: 9,504 slots (15.40 GiB), filled from a ranked profile, adaptive; decode hit rate ~91-97% of
  routed (token, expert) pairs; misses run on a CPU pool (15 workers + the host thread, AVX-512) or are copied over PCIe
  (the "PCIe share", ~0.5 entries a layer-window).
- KV: 32,768 of 262,144 cells per QSA layer in VRAM, the rest of the K/V in 3.09 GiB of pinned RAM (streamed).
- Decode = speculative verify windows: a DFlash2 block drafter (591 MiB of Q4_0 weights in VRAM, a 106,299-token
  draft head) proposes tokens; the target model verifies a window of up to 8 tokens in one pass (CUDA graphs, one
  graph per window size). --draft-conf 0.65 (0.5 measured -1.9%). The draft policy picks windows by measured round
  times, so window sizes vary run to run.
- Per layer in a verify window: the GPU runs the layer's dense chain (HC read, GDN or attention, projections, HC read,
  router), publishes the routing to the host (a "doorbell" in mapped memory), the host plans which experts run where,
  the CPU pool computes its share while the GPU computes the VRAM hits and the shared expert (side streams), the GPU
  waits for the CPU's results (a flag in mapped memory, spun on by a 1-thread kernel), then combines and goes on.

## Measured decode, adopted stack "q3" (all bit-identical changes so far)
A/B round medians on 16-57 replayed Hermes agent turns: 162.8-169.6 tok/s (A/B tier5: 162.8 / 167.7 / 162.2;
A/B res, q3 arm: 164.5 / 165.1 / 169.4; prof8, q3tim arm: 169.6 / 166.1). Live agent suite on an older stack: 151.8.

### Per-window split, STRATA_DECODE_TIMING (no serialization), prof8, 2 rounds x 16 turns
```
q3tim-r0   window: T 3.95, 3.25 tokens/window, 18.86 ms/window -> 172.5 tok/s
q3tim-r0   verify             17.27 ms  ( 91.6%)
q3tim-r0     gpu_reach_wait     10.97 ms  ( 58.2%)     <- the host waiting for the GPU to reach each layer's doorbell
q3tim-r0     per_layer_host      5.35 ms  ( 28.4%)     <- the host's per-layer work
q3tim-r0       cpu                 5.01 ms  ( 26.6%)   <- of which the CPU expert pool
q3tim-r0   draft               1.49 ms  (  7.9%)
q3tim-r0   per layer-window: CPU experts 2.87 (4.11 entries), VRAM hits 32.44, PCIe 0.55; 22.18 swaps/window
q3tim-r1   window: T 3.90, 3.24 tokens/window, 18.89 ms/window -> 171.3 tok/s
q3tim-r1   verify             17.29 ms; gpu_reach_wait 11.07; per_layer_host 5.26 (cpu 4.91); draft 1.51
q3tim-r1   per layer-window: CPU experts 2.69 (3.84 entries), VRAM hits 32.34, PCIe 0.51; 20.88 swaps/window
```
(T = tokens verified per window; "tokens/window" = tokens kept per window; acceptance ~0.77 per drafted token.)

### Serialized stage profile, STRATA_VERIFY_PROFILE=1 (every stage timed alone, so no overlap), ms per window
```
T 3.75  tok/win 3.06  ms/window 20.20  verify 17.69  gpu-reach wait 11.98  per-layer host 4.72  draft 2.43
stages: TOTAL 17.47  VRAM hits 3.37  q8+qkv/q-idx gemv 1.71  waitCPU 1.53  hc down 1.50  hc up 1.31  out-proj 1.25
  shared+quant 1.20  router+plan+bell 0.84  head 0.67  hc norm 0.57  q8+kv-idx 0.53  copy+combine 0.50  attention 0.48
  rec 0.42  PCIe grp 0.30  waitA 0.26  waitB 0.25  k/v+norm-rope 0.21  kv-resolve 0.16  conv 0.13  scores+topk 0.11
  (gap) 0.05  kv+idx append 0.03  ab 0.03  z 0.03
```
DRAM-floor estimates per stage made earlier (phase-2 stack, T 3.55): HC 1.4, VRAM expert hits 2.05, q8+qkv/q gemv 1.4,
out-proj 0.89, shared expert + quantize 0.18, router + plan 0.14.

### Concurrency, Nsight Systems timeline of q3 (3 real turns, 479 windows; tracing inflates the window to ~24 ms)
- One main stream runs the dense chain; side work (shared expert, VRAM hits split over streams, PCIe copies, spin
  kernels) runs on ~1,000 graph-internal streams. GPU-idle gaps of 3 us-1 ms inside decode total ~0.4 ms a window:
  the GPU is almost never empty, but spin kernels (1 thread waiting on a host flag) fill part of it.
- Per layer (means over 23,011 layers, us, nsys-inflated):
  GPU chain, combine of layer l-1 .. doorbell of layer l: 181.0 us (main stream idle inside it 32.0 us); top kernels
  gr_down87 28.6, native_mmvq_multi 18.6, gr_up75 14.3, router bf16 GEMV 11.5, gr_up_wide 10.3, attention 7.8,
  gdn_step_norm 7.3, gr_norm_split 6.9, block_topk 6.7, gdn_ab 5.6, small mmvq 5.1, doorbell 4.2.
  Expert region, doorbell .. combine: 110.3 us = main-stream work 37.4 + main idle 72.9; other streams' work inside it
  85.2 us; the GPU work that started before the CPU's flag ends at 88.1 us, the flag (last spin kernel) ends at 105.2
  us, so the GPU waits ~17 us a layer on the CPU; flag -> combine 5.1 us.
- So: the dense chain is on the critical path every layer; the expert region is bounded by the CPU pool.

### History (each step measured by A/B on replayed real turns)
- Stock tuned config live ~124-133 tok/s -> free VRAM + a bigger expert cache + DFlash2 pack: 151.8 live.
- Phase 2 (stream priorities, fork of the PCIe copy, interleaved GEMV, CPU-pool and checkpoint changes): +6.0%.
- New bit-exact HC read kernels (DOWN86 ring, up T-hybrid): +2.3% paired. Tier 5 (doorbell stored instead of a
  read-modify-write over PCIe, hits folded into the combine, skipping the CPU activation of tokens with no CPU entry,
  HC up plane layout, DOWN87): +4.0% paired.
- A resident one-kernel HC read (80 CTAs, cooperative launch) ~4 us a read faster in isolation (0.4 ms a window
  predicted) was neutral on real turns (1.005, CI 0.990-1.021): in the engine it saved ~0.15 ms a window.
- Ruled out (measured): device-side expert planning -3.0%; another expert-decode kernel family -3.0%; another HC read
  variant -3..-6%; a learned expert profile: no hit-rate gain (adaptive tier already ~91%); draft-conf 0.5: -1.9%;
  Windows large pages: +0.7% (noise); a one-batch-per-layer CPU pool: neutral; STRATA_HC_Q8 (lossy: KL 0.025).

## Measured prefill, same stack (2026-11-08)
- Cold prompts (fresh code text, nothing reused; engine "prompt chunk auto: 32768 tokens, a 384-slot ring"; "the
  prompt path borrows 8211 CUDA0 cache slots (13.27 GiB)"; the CPU takes a share of the experts for chunks up to 3,072
  tokens, a stock default with mean KL ~0.004-0.011 vs the GPU-only path):
  4K: 1,956-2,219 tok/s (1.8-2.1 s); 16K: 2,882-2,931 tok/s; 32K: 2,878-2,946 tok/s; 64K: 3,119-3,125 tok/s (21.0 s).
- Real agent turns (mostly warm: conversation cache, ~6-9K-token prompts of which a few hundred to a few thousand are
  new): median prompt time 842 ms; a fit over warm turns gives 505 ms fixed + 0.404 ms per new token. Earlier: 957 ->
  866 ms after phase 2 (a park-gain setting for the conversation cache gave -13.8% prompt time).

## Code (if you can read C:\src\Strata)
src/core/verify.cpp (verify windows, per-layer loop, doorbell, CPU wait, combine, profile stamps),
src/kernels/cuda/fused_gr.cu (HC reads), src/kernels/cuda/native_mmvq.cu (dense quantized GEMV, LM head),
src/kernels/cuda/iq_kernels.cu (GPU experts), src/kernels/cpu/native_expert.cpp + iq_avx512.cpp + pool.cpp (CPU
experts), src/prefill/prefill.cpp (prompt path), include/strata/spec/draft_policy.hpp (window policy),
src/program/generate.cpp (serve loop), src/core/nv_defaults.cpp (per-arch defaults).
