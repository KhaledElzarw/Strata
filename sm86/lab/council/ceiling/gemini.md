```
CONFIDENCE 200: 35% - Reaching 200 tok/s median over replayed agent turns at today's yield (3.245 kept tokens/window at T ~ 3.92, lines 73-83) requires shrinking the window from 18.87 ms (q3tim, 171.9 tok/s) or ~19.37 ms (full A/B median ~167.5 tok/s, lines 68-69) to 16.23 ms/window: a net reduction of 2.65 to 3.15 ms/window (-14.0% to -16.3%) strictly on the critical path. Because the dense chain (11.98 ms) is already near the RTX 3090's measured 645 GB/s cold-read floor on native GEMVs, and the 48 expert regions (5.30 ms host/CPU path) overlap with 4.23 ms of GPU MoE work (88.1 us/layer vs 105.2 us/layer CPU flag, leaving only 17.1 us/layer = 0.82 ms/window before GPU MoE becomes the new blocker, lines 105-107), getting 2.65-3.15 ms in-engine requires landing all four changes below simultaneously:

  1. Expert region co-optimization: fold shared+quant into the MoE launch + cut CPU expert tail & throttle mid-decode VRAM swaps (src/core/verify.cpp, src/kernels/cuda/iq_kernels.cu, src/kernels/cpu/pool.cpp) -> predicted saving: 0.75-1.10 ms/window on the critical path.
     - Arithmetic & why it holds: In the expert region (110.3 us/layer nsys, ~110.4 us/layer un-inflated), the CPU pool finishes at 105.2 us while GPU MoE work (VRAM hits 3.37 ms + shared+quant 1.20 ms + PCIe grp 0.30 ms serialized = 4.87 ms serialized, 88.1 us/layer = 4.23 ms/window overlapped) finishes only 17.1 us earlier (0.82 ms/window, line 106). Speeding up the CPU alone caps out at 0.82 ms/window. However, shared+quant takes 1.20 ms serialized vs a 0.18 ms DRAM floor (line 90, 95) because it quantizes activations separately and contends across ~1,000 graph streams; folding the shared expert into the routed expert kernel grid (as slot 11 of 10+1 active experts reusing the same q8 input) drops GPU MoE time by ~0.55-0.70 ms/window. Simultaneously, lines 79 & 82 show 20.88-22.18 adaptive VRAM cache swaps/window (21.5 * 1.66 MiB = 35.7 MiB = 37.4 MB/window), which consumes 1.40 ms/window of PCIe 4.0 x16 bandwidth (at 26.8 GB/s, line 43) and steals pinned DDR5 bandwidth from the CPU pool while hit rate is already 91-97%. Deferring/capping swaps during verify + shifting ~0.5-0.7 expert misses/layer from CPU DDR5 (60 GB/s) to the underutilized PCIe share (currently only 0.53 entries/layer = 0.30 ms/window) + grouping multi-token CPU hits (3.98 entries / 2.78 unique experts = 1.43 tokens/expert) cuts CPU wait + GPU MoE ceiling together by 0.75-1.10 ms/window.

  2. Fuse router BF16 GEMV + block_topk + system doorbell write into one kernel (src/kernels/cuda/ + src/core/verify.cpp) -> predicted saving: 0.45-0.60 ms/window on the critical path.
     - Arithmetic & why it holds: Every microsecond before layer l's doorbell directly delays the host thread in gpu_reach_wait (10.97-11.07 ms/window, lines 75, 81) and therefore shifts the start of the CPU expert pool 1-for-1 on the critical path. Router BF16 weights are only 48 * 512 * 2560 * 2 B = 125.8 MB/window (DRAM floor 0.14 ms at 936 GB/s, 0.20 ms at 645 GB/s, line 95), yet router+plan+bell (0.84 ms) + scores+topk (0.11 ms) costs 0.95 ms serialized (line 90-91) and 11.5 + 6.7 + 4.2 = 22.4 us/layer (1.08 ms/window) in nsys (lines 103-104). Fusing the 512-row BF16 GEMV, warp/cooperative top-10 selection, and mapped-memory doorbell store into one kernel removes 96 kernel launches + L2 round-trips per window and moves doorbell publication ~10-12 us earlier per layer.

  3. Fuse hc_norm (gr_norm_split) into HC up/down & unify gr_up75 + gr_up_wide (src/kernels/cuda/fused_gr.cu) -> predicted saving: 0.35-0.50 ms/window on the critical path.
     - Arithmetic & why it holds: hc_norm operates on a 4 x 2560 = 10,240-element vector per token (<= 80 KB for T=4, purely L2-resident), yet costs 0.57 ms/window serialized (line 90) and 6.9 us/layer in nsys (line 104) as separate launches, while HC up splits across gr_up75 (14.3 us) and gr_up_wide (10.3 us). Fusing the norm into the HC epilogue/prologue on the main stream removes 96 launches and L2 barrier gaps directly on the dense critical path.

  4. Eliminate main-stream dense-chain idle bubbles (32.0 us/layer in nsys) by fusing GDN micro-kernels (gdn_ab, z, conv, gdn_step_norm) and QSA KV-prep (src/core/verify.cpp, src/kernels/cuda/) -> predicted saving: 0.45-0.70 ms/window on the critical path.
     - Arithmetic & why it holds: Line 102 shows the main stream is idle for 32.0 us per layer (1.54 ms/window nsys-inflated, ~1.15 ms un-inflated) inside combine(l-1) .. doorbell(l) due to tiny sequential launches (gdn_step_norm 7.3 us, gdn_ab 5.6 us, small mmvq 5.1 us, conv 0.13 ms, k/v+norm-rope 0.21 ms, kv-resolve 0.16 ms, kv+idx append 0.03 ms, lines 90-92, 103-104) and graph event dependencies. Merging the GDN state-prep kernels and tightening intra-layer stream events recovers ~10-15 us/layer on the main stream.

  5. DFlash2 draft pass + target LM head tuning / overlap (src/kernels/cuda/native_mmvq.cu, src/core/verify.cpp) -> predicted saving: 0.25-0.40 ms/window on the critical path.
     - Arithmetic & why it holds: Draft takes 1.50 ms/window (lines 78, 81) for 591 MiB (620 MB) of Q4_0 weights (0.66 ms floor at 936 GB/s, 0.96 ms at 645 GB/s), and target head takes 0.67 ms (line 90) for ~150-200 MB (~0.30 ms floor). Both execute entirely on the critical path outside the layer loop.

CONFIDENCE 250: 2% - Reaching 250 tok/s at 3.245 kept tokens/window requires 12.98 ms/window: removing 5.89 ms/window from q3tim (18.87 ms) or 6.39 ms/window from the full turn median (19.37 ms), a ~32% wall-time cut. Even if every weight-read kernel in the engine ran at 100% of this RTX 3090's measured cold plain-read bandwidth floor (645 GB/s, line 44) with zero dequantization ALU cost and zero kernel-launch gaps, the mandatory sequential critical path still sums to ~12.7-13.5 ms/window (see CEILING arithmetic below). Under Tier A/B rules (no requantization, no route-tail skipping, no retraining a higher-acceptance drafter), 250 tok/s exceeds the practical physical floor of one 390W-capped RTX 3090 + 60 GB/s DDR5 host.

CEILING:
  - Theoretical: 433-471 tok/s (pure GPU GDDR6X 936 GB/s bound: 6.89-7.50 ms/window) or 355 tok/s if CPU DDR5 expert share is unchanged (9.13 ms/window);
  - Practical: 235-250 tok/s (13.0-13.8 ms/window, bounded by the card's 645 GB/s sustained read rate at the 390W cap, 48 host-GPU doorbell/flag synchronizations, and concurrent DDR5/PCIe expert miss latency);
  - Today (168 tok/s median across q3/q3tim arms; 172 tok/s in q3tim): 37% of the 450 tok/s pure GDDR6X ceiling (47% of the 355 tok/s hybrid GDDR6X+DDR5 bound), and 70% of the ~240 tok/s practical ceiling.

  - Byte & time arithmetic per verify window (T ~ 3.92 verified, 3.245 kept tokens/window):
    1. Mandatory GPU DRAM bytes read per window:
       - HC BF16 weights: 96 sublayers * 2 matrices (W_down 320x10240 + W_up 10240x320) * 6.5536 MB + 1 final read (6.5536 MB) = 1,264.8 MB (1,206.3 MiB of the 1,466 MiB dense pack, lines 48-49, 52).
       - Router BF16 weights: 48 * 512 * 2560 * 2 B = 125.8 MB (120.0 MiB).
       - Dense quantized projections + 48 shared experts + LM head: 2,069 MiB = 2,169.5 MB (line 52; corresponds to line 94-95 DRAM floors at 936 GB/s: q8+qkv/q 1.40 ms + out-proj 0.89 ms + shared 0.18 ms + q8+kv-idx ~0.15 ms + head ~0.25 ms = 2.87 ms).
       - VRAM routed expert hits: 32.39 hit entries/layer across 48 layers (~23.6 unique experts/layer after multi-token coalescing * 48 * 1.66 MiB) = 1,919 MB (line 94 DRAM floor: 2.05 ms at 936 GB/s).
       - QSA KV cache + GDN recurrent state + activations: ~350 MB (~0.37 ms at 936 GB/s).
       - DFlash2 block drafter: 591 MiB = 619.7 MB (line 58; 0.66 ms at 936 GB/s).
       - Total GPU DRAM bytes/window = 1,265 + 126 + 2,170 + 1,919 + 350 + 620 = 6,450 MB/window (6.15 GiB/window).
    2. Theoretical bound (936 GB/s GDDR6X peak + 60 GB/s DDR5 + 26.8 GB/s PCIe):
       - Pure GPU DRAM time = 6,450 MB / 936 GB/s = 6.89 ms/window (or summing line 94-95 component floors + head/KV/draft = 7.49 ms/window) -> 3.245 / 0.00689..0.00749 s = 433-471 tok/s.
       - Concurrent MoE miss bound: 2.78 unique CPU experts/layer * 48 * 1.66 MiB = 221.5 MiB = 232.3 MB/window. On DDR5 alone at 60 GB/s (line 42), reading 232.3 MB takes 3.87 ms/window vs the 2.23 ms GPU MoE floor (2.05 ms hits + 0.18 ms shared), adding 1.64 ms (7.49 + 1.64 = 9.13 ms -> 355 tok/s) unless PCIe (26.8 GB/s) takes ~30% of misses concurrently (232.3 MB / (60 + 26.8 GB/s) = 2.68 ms, adding only 0.45 ms -> 7.94 ms -> 409 tok/s).
    3. Practical ceiling (645 GB/s measured cold plain-read floor at 390W cap, line 44):
       - Dense main-stream weight reads + state + head: (1,265 MB HC + 126 MB router + 2,001 MB dense/head + 350 MB KV/GDN) / 645 GB/s = 5.80 ms pure read + ~1.20 ms IQ3_XXS dequant/compute/attention + ~0.80 ms irreducible launch/norm/combine + ~0.50 ms across 48 graph/doorbell transitions = 8.30 ms.
       - 48 expert regions: max(GPU MoE 2,087 MB / 645 GB/s + dequant ~ 3.45 ms, DDR5+PCIe miss read + AVX-512 + barrier ~ 3.60 ms) = 3.60 ms.
       - Draft pass: 620 MB / 645 GB/s + draft layers/head = 1.10 ms.
       - Total practical floor = 8.30 + 3.60 + 1.10 = 13.00 ms/window (13.0-13.8 ms/window) -> 3.245 / 0.0130..0.0138 s = 235-250 tok/s.

PREFILL:
  - Cold prompt now:
    - 4K: 1,956-2,219 tok/s (1.85-2.09 s, mean 1.97 s); 16K: 2,882-2,931 tok/s (5.64 s); 32K: 2,878-2,946 tok/s (11.25 s); 64K: 3,119-3,125 tok/s (21.0 s) (line 126).
    - What bounds cold prompt today (arithmetic): Fitting the measured cold times from 4K (1.97 s) to 32K (11.25 s) yields:
      T_cold(N) = 0.64 s fixed per chunk + 0.324 ms/token (3,089 tok/s asymptotic slope).
      At N >= 4,096 tokens (10 experts/token = 40,960 routes/layer across 512 experts), >90% of all 24,576 experts (39.97 GiB) are activated. Because the prompt path borrows 8,211 of the 9,504 VRAM cache slots (13.27 GiB of 15.40 GiB, line 124), ~37.8 GiB of experts are uncached during prefill and must stream from pinned RAM over PCIe 4.0 x16 (26.8 GB/s) into the 384-slot ring: 37.8 GiB (40.6 GB) / 26.8 GB/s = 1.51 s of raw PCIe transfers per full expert sweep (~0.64-0.90 s un-overlapped penalty at 4K), while the 0.324 ms/tok slope is bounded by GPU IQ3_XXS dequant + grouped MoE GEMM (~5.2B active params/tok = ~10.5 GFLOP/tok at ~50-55 TFLOPS under the 390W cap + QSA sparse attention + streaming 87.5% of QSA KV cells [3.09 GiB] to pinned RAM).
    - Cold prompt floor:
      - 4K floor: 1.10-1.25 s (3,280-3,720 tok/s), bounded by max(PCIe streaming of ~22-24 GB truly uncached experts at 26.8 GB/s = 0.82-0.90 s when the 15.40 GiB VRAM cache is NOT evicted, GPU 4K compute = 1.05 s) + ~0.15 s non-overlapped prologue/epilogue.
      - 16K-64K floor: 3,800-4,100 tok/s (0.24-0.26 ms/tok -> 16.0-17.2 s at 64K vs 21.0 s today), bounded by 390W-capped GA102 Tensor Core + IQ3_XXS dequant throughput and PCIe KV streaming.

  - Warm turn prompt now:
    - Median: 842 ms; linear fit: 505 ms fixed + 0.404 ms per new token ( implying median N_new ~ (842 - 505) / 0.404 = 834 new tokens on a 6-9K prompt, lines 127-128).
    - What bounds warm turn today (arithmetic):
      1. The 505 ms fixed intercept (60% of the entire 842 ms median warm prompt!) is bounded by PCIe 4.0 x16 traffic from borrowing and restoring 8,211 VRAM expert cache slots (13.27 GiB = 14.25 GB) sized for `prompt chunk auto: 32768 tokens` (lines 123-124) plus conversation-cache unparking/parking: 13.27 GiB (14.25 GB) / 26.8 GB/s = 532 ms!
      2. The 0.404 ms/new-token slope (25% slower than cold 64K's 0.320 ms/tok) occurs because evicting 8,211 of 9,504 VRAM expert slots leaves only 1,293 slots (13.6% of cache) resident during prefill, forcing the ~834 new tokens to stream/CPU-compute experts that were already in VRAM a moment earlier.
    - Warm turn floor:
      - 240-280 ms median (~50 ms fixed + 0.24-0.27 ms per new token), bounded by restoring only the active conversation's GDN state + dynamically borrowing <= 1.5 GiB for N_new <= 2,048 tokens (~50 ms) and executing the ~834 new tokens against the intact 88-91% VRAM expert cache (~200-225 ms).

  - Top 3 prefill changes with predicted gains:
    1. Dynamic prefill scratch sizing in src/prefill/prefill.cpp (borrow slots proportional to actual N_new instead of fixed 32,768-token chunk borrowing 8,211 slots / 13.27 GiB):
       - Predicted gain: -320 to -420 ms on median warm turns (cutting 842 ms -> ~420-520 ms, a 38-50% reduction) and -0.4 to -0.6 s on 4K cold prompts (+25-35% tok/s at 4K). Keeping ~8,300-8,700 expert slots in VRAM during warm turns eliminates ~11-12 GiB of PCIe cache restore (saving ~350 ms of the 505 ms fixed cost) and raises warm-prefill VRAM hit rate from ~15% to ~88% (cutting the per-token slope from 0.404 to ~0.28 ms/tok).
    2. Disable/fix the lossy CPU expert share on prompt chunks <= 3,072 tokens and double-buffer the 384-slot PCIe expert ring per layer (src/prefill/prefill.cpp):
       - Predicted gain: Eliminates the Tier-C quality violation (mean KL 0.004-0.011 vs GPU-only path, line 125) and saves ~60-100 ms on warm turns / ~0.25 s on 4K cold prompts by keeping prefill MoE on GPU Tensor Cores with lookahead PCIe prefetch from layer l+1's routing.
    3. Fuse IQ3_XXS dequantization into the grouped MoE GEMM epilogue/tile loader and batch QSA KV pinned-RAM streaming (src/prefill/prefill.cpp, src/kernels/cuda/iq_kernels.cu):
       - Predicted gain: +12-18% cold throughput at 16K-64K (2,910 -> ~3,350 tok/s at 32K; 21.0 s -> ~18.0 s at 64K) and -30 to -50 ms on warm turns.

WHAT WOULD CHANGE MY MIND:
  - For 200 / 250 tok/s decode: A non-inflated per-layer hardware timestamp breakdown in verify.cpp measuring the exact distribution of (t_cpu_flag_ready - t_gpu_moe_done) across all 48 layers and all 57 replayed turns when the 21-22 VRAM cache swaps/window are paused. If GPU MoE side-stream work actually finishes in <= 65 us/layer (~3.1 ms/window) instead of 88.1 us/layer (4.23 ms/window) when nsys tracing and cache swaps are off, then CPU/PCIe expert optimizations can yield up to 2.0 ms/window instead of hitting a wall at 0.82 ms/window, raising CONFIDENCE 200 from 35% to ~70%. Conversely, if a lossless draft-policy/tree change in draft_policy.hpp raises kept tokens/window from 3.25 to >= 3.85 at the same T ~ 4.5 verify cost, CONFIDENCE 200 rises above 80% and CONFIDENCE 250 rises to ~20%.
  - For prefill: A profile breakdown of the 505 ms warm-turn fixed cost into (a) CUDA0 expert-cache slot eviction/re-population bytes transferred over PCIe, (b) conversation-cache GDN/KV unpark/park time, and (c) prompt setup/graph launch overhead.

UNCERTAIN:
  - Whether the 20.88-22.18 VRAM cache swaps/window (lines 79, 82) execute synchronously inside the verify window (competing with PCIe grp and DDR5 CPU expert reads) or between windows, and whether freezing adaptive swaps after warmup hurts hit rate on long turns. Evidence to settle: A/B replay with adaptive cache updates disabled after turn 1 (or throttled to <= 2 swaps/window during idle draft/head gaps).
  - Why shared+quant takes 1.20 ms serialized vs a 0.18 ms DRAM floor (line 90, 95) and how much of its 1.20 ms is L2 contention with VRAM expert hits during unserialized verify. Evidence to settle: Nsight Compute / per-kernel cycle timer on shared+quant inside the captured CUDA graph vs standalone.
  - How much of the 505 ms fixed warm-turn prefill cost is VRAM expert cache re-upload after borrowing 8,211 slots vs conversation-cache state unparking. Evidence to settle: Timing `prefill.cpp` with `prompt chunk auto` capped at 2,048 tokens (borrowing ~512 slots instead of 8,211 slots) on the warm-turn benchmark.
```

---

### Concrete Defects (Severity, Packet Path/Line, Trigger, and Reasoning)

1. **[HIGH] Unconditional borrowing of 8,211 VRAM expert cache slots (13.27 GiB) on warm prompts causes a ~505 ms fixed prefill penalty**
   - **Packet Path/Line**: `review-packet.md:123-124`, `review-packet.md:127-129` (`src/prefill/prefill.cpp`)
   - **Trigger**: Any warm agent turn (typical prompt 6–9K tokens with ~834 new tokens, well below the 32,768-token auto chunk size).
   - **Reasoning**: Line 123–124 shows prefill configures `prompt chunk auto: 32768 tokens` and borrows 8,211 CUDA0 expert cache slots (13.27 GiB out of 15.40 GiB), regardless of how many new tokens actually need to be prefilled. Evicting and restoring up to 13.27 GiB (14.25 GB) over PCIe 4.0 x16 at 26.8 GB/s requires up to $14.25\text{ GB} / 26.8\text{ GB/s} = 532\text{ ms}$, which directly explains the measured **505 ms fixed overhead** per warm turn (60% of the 842 ms median warm prompt time) and degrades the warm per-new-token slope to 0.404 ms/tok (vs 0.320 ms/tok on cold 64K) by stripping the VRAM expert cache down to 1,293 slots during prefill.

2. **[HIGH] Stock prefill CPU expert share for chunks $\le 3,072$ tokens violates the owner's Tier A/B quality rule (`no quality loss`)**
   - **Packet Path/Line**: `review-packet.md:31-36`, `review-packet.md:124-125` (`src/prefill/prefill.cpp`)
   - **Trigger**: Any prompt or warm turn with chunk size $\le 3,072$ tokens (which includes almost all warm agent turns where new tokens are a few hundred to a few thousand, line 127–128).
   - **Reasoning**: Lines 31–36 strictly forbid Tier C (lossy) behavior (`KL > 0` beyond rounding-level summation order). Line 124–125 states that in the current stack, `"the CPU takes a share of the experts for chunks up to 3,072 tokens, a stock default with mean KL ~0.004-0.011 vs the GPU-only path"`. A mean KL divergence of 0.004–0.011 against the GPU-only path is well beyond FP16/BF16/FP32 rounding-order noise (for comparison, lossy `STRATA_HC_Q8` was rejected at KL 0.025 on line 120) and indicates either a lossy quantization/accumulation shortcut or a numerical defect in the batched CPU prefill expert path.

3. **[MEDIUM] Heavy adaptive VRAM expert cache swapping during decode (`20.88–22.18 swaps/window`) saturates PCIe and contends with DDR5 CPU expert reads**
   - **Packet Path/Line**: `review-packet.md:54-56`, `review-packet.md:79`, `review-packet.md:82` (`src/core/verify.cpp`)
   - **Trigger**: Normal speculative decode windows (`q3tim-r0` and `q3tim-r1`).
   - **Reasoning**: At 1.66 MiB ($1.74\text{ MB}$) mean per expert (line 51), 21.5 swaps/window transfers $37.4\text{ MB/window}$ from pinned host DDR5 over PCIe 4.0 x16 to GDDR6X. At the measured 26.8 GB/s PCIe bandwidth (line 43), $37.4\text{ MB}$ takes **1.40 ms/window** of PCIe occupancy (7.4% of the entire 18.87 ms window and 26% of the 5.30 ms `per_layer_host` window), while the direct `PCIe share` for active misses is only 0.51–0.55 entries/layer (0.30 ms/window). This swap traffic steals both PCIe bandwidth and host DDR5 bandwidth from the CPU expert pool even though cache hit rate is already steady at 91–97%.

4. **[MEDIUM] Severe inefficiency in `shared+quant` (1.20 ms serialized vs 0.18 ms DRAM floor) and `router+plan+bell` (0.84 ms serialized vs 0.14 ms DRAM floor)**
   - **Packet Path/Line**: `review-packet.md:89-95`, `review-packet.md:102-107` (`src/core/verify.cpp`, `src/kernels/cuda/iq_kernels.cu`)
   - **Trigger**: Every verify window across all 48 layers.
   - **Reasoning**: `router+plan+bell` + `scores+topk` takes $0.84 + 0.11 = 0.95\text{ ms}$ serialized ($22.4\ \mu\text{s/layer}$ in nsys) on the main-stream critical path to read only 125.8 MB of BF16 router weights (0.14 ms DRAM floor), delaying the host doorbell wakeup every layer. Meanwhile, `shared+quant` takes 1.20 ms serialized (6.7x its 0.18 ms DRAM floor), inflating the GPU side-stream MoE duration to 88.1 us/layer so that it sits only 17.1 us/layer (0.82 ms/window) below the CPU spin-flag deadline (105.2 us/layer).

5. **[LOW] Packet unit/terminology ambiguity in HC read byte description (`review-packet.md:44` vs `review-packet.md:48-49` vs `review-packet.md:94`)**
   - **Packet Path/Line**: `review-packet.md:44`, `review-packet.md:48-49`, `review-packet.md:89`, `review-packet.md:94`
   - **Trigger**: Computing theoretical DRAM-floor bytes for the 97 HC reads per window.
   - **Reasoning**: Line 48–49 states `"two HC reads per layer plus one final (97 reads per verify window), each reading W_down 320x10240 + W_up 10240x320 in BF16 (13.1 MB per read)"`. A single $320 \times 10240$ BF16 matrix is $6,553,600\text{ B} = 6.55\text{ MB}$ (matching line 44's probe of a single matrix: `"a 6.55 MB read takes 10.2 us"`), whereas `W_down` + `W_up` together at each of the 96 sublayer sites is $13.11\text{ MB}$ (plus one final $6.55\text{ MB}$ read = $1,264.8\text{ MB}$ total, which at 936 GB/s gives $1.35\text{ ms}$, matching line 94's `HC 1.4 ms` DRAM floor). Treating the 97 sites as 97 single-matrix reads ($636\text{ MB}$) vs 96 `down+up` pairs + 1 final ($1,265\text{ MB}$) changes the HC byte total by 2x if not cross-checked against lines 52, 89, and 94.

### Missing Context and Unverified Claims

- **Source code in `C:\src\Strata` not inspected**: Per boundary rules, only `review-packet.md` was read; none of the files listed on lines 131–136 (`src/core/verify.cpp`, `src/kernels/cuda/fused_gr.cu`, `src/prefill/prefill.cpp`, etc.) were read or tested.
- **Unverified claim on CPU prefill KL divergence source (line 125)**: The packet reports `mean KL ~0.004-0.011 vs the GPU-only path` when the CPU takes an expert share for prompt chunks $\le 3,072$ tokens, but does not establish whether this is caused by an intentional low-precision intermediate quantizer on CPU or an implementation bug in batched CPU expert execution.
- **Unverified overlap of the 21–22 VRAM cache swaps/window (lines 79, 82)**: The packet reports swap counts per window in `STRATA_DECODE_TIMING` but does not isolate swaps in the `STRATA_VERIFY_PROFILE=1` stage breakdown (lines 88–92) or specify which CUDA stream/phase executes the H2D swap copies.
- **Unverified composition of the 505 ms warm-turn fixed prefill cost (line 128)**: While 13.27 GiB of borrowed CUDA0 expert cache slots (line 124) over a 26.8 GB/s PCIe bus accounts for up to 532 ms if evicted and re-uploaded, the exact split between expert-cache restoration and conversation-cache (QSA KV / GDN recurrent state) park/unpark transfers cannot be verified without instrumentation in `src/prefill/prefill.cpp`.
