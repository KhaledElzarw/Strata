# 0004: Tier-5 switches and the resident HC read (sm86-decode lab branch)

Date: 2026-11-08. Status: decided by the chair (Claude Code); reversible (every change is an opt-in switch).

## Problem
After 0001 the hyper-connection read (norm, down 324 x 10240, up 10240 x 320, BF16) still cost 30.7-45.5 us at
T = 1..8 (fused_gr_bench, cold weights), against a plain-read floor of 20.5 us for W_down + W_up (fused_gr_bw_probe:
6.55 MB cold in 10.2 us, 641 GB/s, for four grid shapes). 96 reads a decode window, T averaging ~3.5 on real agent
turns. Hard constraint: bit-identical outputs (tier A).

## Evidence gathered before deciding
- Prefetching the next phase's weights into L2 (STRATA_GR_PF: W_up during the down, W_down tiles during the norm, the
  down's own share): bits identical, never faster (the down slowed 1-3 us). The down is not DRAM-bound.
- gr_up9 (unpack once a batch, warp_sum4, loads up front; half the instructions): no faster than UP_PL at T 3-6.
  The up is not issue-bound either; its time is the W_up stream after the down's last tile.
- gr_down87 (D87=8: per-thread cp.async addresses precomputed): -0.4..-1 us at T >= 4. UP_PL (lo in two float4
  planes): small gain. Both kept.
- ND86 (norm and down in one launch, 4T + 80 blocks): slower; 4T + 80 blocks at one a SM run as a second wave.

## Council (design mode, round 2, "HC read vs the plain-read floor"; Hermes unavailable: gateway "service_disabled")
- Codex gpt-6.1-sol xhigh: one resident kernel, 80 CTAs, W_up held in registers through the down phase, three grid
  barriers; probe the structure first. Expected 24-27 us at T 3-4.
- Gemini 4 Argon high: the norm inside the down launch (W_down's tile 0 out first, the norm on the first 4T CTAs),
  and up75 with a cp.async pipeline for occupancy. Expected 25.5-27 us.
- Chair (written before reading the members): up75 on a forked graph branch polling a counter the down's groups bump.

## Decision
Build Sol's resident kernel (STRATA_GR_RES=1) with Gemini's ordering inside it: W_down's first ring stages go out
before the norm, and the norm's CTAs load their W_up share after the norm. The chair's side-stream design is
superseded (the same overlap plus a co-residency gamble). Declined: Gemini's up75 occupancy argument (the plain-read
probe at the same 160 x 256 grid reaches the floor).

## What was built (src/kernels/cuda/fused_gr.cu, gr_res_kernel)
80 CTAs x 544 threads, one CTA a multiprocessor (82 on the 3090), phases joined by device counters (g_res_ctr, each
reset by its wait's last reader) and DOWN86's own election:
norm loads out -> W_down stages 0-1 -> the other CTAs load W_up into registers -> the norm (R_out, rs, xn) -> every CTA
waits for the norms -> DOWN86's ring -> partials and the group election (the last CTA of a group sums its rows, lo and
inject) -> the norm CTAs load W_up -> every CTA waits for the 20 groups -> lo in PL planes -> up9-style sums
(warp_sum4) from the held registers -> epilogue -> mixed. The same operations in the same order as the 3-kernel read.
Lessons from the phase profile (STRATA_GR_RES_PROF=1, %globaltimer per phase):
- Register W_up loads fill a multiprocessor's request queue for ~7 us; any global read on it then waits ~3.5 us
  (counter polls included). So the norm CTAs send their own loads first and take W_up last.
- The up's token loop: 17 warps cap a thread at 96 registers; a full unroll spilled (88-648 B at T 4-8) and the
  phase stamps held ~14 registers in every thread. Fixed: 2-way unroll beyond T 3, stamps in shared memory.
- What is left of the up phase (4-6.5 us at T 4-8) is shared-memory and shuffle throughput (each warp re-reads lo
  for its two row batches), not DRAM.
Removed after measuring: STRATA_GR_PF, UP9, UP320, ND86 (never committed).

## Result
- hcbench (fused_gr_bench, cold weights, us at T 1..8), every cell IDENTICAL (apply 0/1, inject 0/1):
  adopted stack 30.6 / 32.2 / 33.3 / 34.6 / 37.9 / 40.4 / 42.0 / 45.4;
  STRATA_GR_RES=1 26.0 / 26.9 / 28.7 / 31.2 / 34.1 / 35.4 / 37.0 / 38.3.
- Whole-engine identity (strata-lab idcheck sweep19, 1363 forced tokens): IDENTICAL.
- Tier-5 switches (STRATA_DOORBELL_STORE, STRATA_FUSE_HITS, STRATA_ACTQ_SKIP, STRATA_GR_UP_PL, STRATA_GR_D87=8):
  each and all together IDENTICAL (sweep18); A/B tier5 (3 x 57 real turns): paired median 1.040, geo-mean 1.047
  [1.027, 1.068]; round medians 158.9 / 163.4 / 152.6 -> 162.8 / 167.7 / 162.2 tok/s. Adopted.
- STRATA_GR_RES=1 A/B (strata-lab ab.py res, 3 rounds x 57 replayed real agent turns, q3 vs q3 + RES): paired-turn
  median 1.005, geo-mean 1.006 [0.990, 1.021] (n = 168); round medians 164.5 / 165.1 / 169.4 -> 160.5 / 167.5 /
  166.4 tok/s; prompt time 0.997. Below the adoption bar (>= 2%, CI excluding 1): NOT adopted; RES stays an opt-in
  lab switch. The read is ~4 us faster in isolation (~0.4 ms a window expected); in the engine that gain did not show.
- Review, full tier (Hermes unavailable: gateway "service_disabled", $0). L1: Codex gpt-6.1-sol 5/10, gpt-6-luna
  4/10, Gemini 4 Argon 7/10. Taken: [P1, all three] RES skipped DOWN82/86's exclusion of STRATA_PIPED_CONCURRENT /
  STRATA_PIPED_MTP (two reads of a device at once share the scratch and counters); [P1, Sol] ld.acquire and __nanosleep
  need sm_70 (the experimental sm_60 build): volatile load + fence and no sleep below 7.0; [P1, Sol] Metal links
  verify.cpp without a stub for doorbell_publish_res_store: the call is under the file's CUDA-only guard; [P1, Luna +
  Gemini] the occupancy check describes an idle card: RES is now a cooperative launch (the driver starts it only with
  every CTA resident; STRATA_GR_RES_COOP=0 = plain, same time in hcbench); [P2] the bench probe's residency check and
  per-device state; [P2, Gemini] RES counted in the dispatch stats. Declined: the norm counter firing before its loads
  drain (a measured speed heuristic, no correctness dependency); STRATA_ACT_DUMP=0 (a file prefix, so "0" dumps);
  the probe barrier's plain reset store (write-through to L2, fenced).
- After the fixes: hcbench hc28 40/40 IDENTICAL, cooperative = plain launch time; idcheck sweep20 IDENTICAL for
  q3 + RES (cooperative, captured in the window graphs) and for q3.
- L2 (fixes only): Sol 7/10, Luna 6/10, Gemini no score. Taken: [Sol] STRATA_PIPED_CONCURRENT is parsed with atoi
  ("01" turns piping on), so RES's exclusion checks both the first character and atoi; [Sol] the bench probe printed
  "ok" when it had skipped (it now returns false and the bench says why); [Gemini] the probe buffer is cleared with
  cudaMemsetAsync on the probe's stream; the sm_6x wait fences once after its loop, not on every poll; the launch
  attribute is zero-initialized; a failed eager launch marks the device unusable (ok = -1) instead of retrying each
  read. Declined: [Luna] polling with atomicAdd(ctr, 0) on sm_6x (unreachable: RES needs >= 80 SMs and no sm_6x part
  has more than 60; sm_70+ takes ld.acquire); MPS / MIG replay failures and a cooperative probe launch (bench-only,
  residency-checked); a capture-invalidating cooperative failure (fails loudly; never wrong bits).
- Where the 4 us went (strata-lab prof8, 2 rounds x 16 replayed turns, q3 vs q3 + RES): with STRATA_DECODE_TIMING,
  RES's windows were 0.9 ms shorter (17.95 vs 18.88 ms) but verified fewer tokens (T 3.6 vs 3.9, 2.96 vs 3.25
  tokens a window), so the per-layer host time fell with fewer CPU expert entries (4.55 vs 5.30 ms) while the
  GPU-reach wait fell only 0.17 ms (10.85 vs 11.02); the draft phase was the same (1.51 vs 1.50 ms), so RES does not
  starve the drafter. With STRATA_VERIFY_PROFILE (serialized stages) the HC reads total ~3.23 ms a window with RES vs
  3.38 without, ~0.15 ms, not the ~0.4 ms hcbench predicts. (RES's profile stamps are back to back; when they tie,
  the FFN-side read is counted in "router+plan+bell", which then reads ~1.95 instead of 0.84 ms.)
- Process lesson (2026-11-08): RES won in isolation and was neutral in the engine because the design packet held no
  concurrency data (what runs beside the HC read). Design packets now carry the engine's timing and concurrency
  evidence and ask for ms per window; code review runs only on changes that win their A/B.
