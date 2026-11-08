# 0003: CPU expert pool per-layer schedule (sm86-decode lab branch)

Date: 2026-11-08. Status: decided by the chair (Claude Code); reversible (opt-in STRATA_POOL_DAG=1).

## Problem
About 10% of routed experts per decode window run on the CPU pool (15 workers + the host thread, Ryzen 9 9950X). The
GPU waits ~1.1 ms per window for the CPU share. Hard constraint: bit-identical outputs.

## Evidence
- "strata decode pool" (STRATA_DECODE_TIMING, forced text): gate/up phase 74-158 us per layer, host quantize 1.0-2.3 us,
  down phase 37-76 us. ~6.9 MB of expert weights per layer at ~54 GB/s against ~60 GB/s measured DRAM bandwidth.
- pool.cpp: run_split_multi_native = run_phase(5) (gate/up rows of all experts, 48 equal tasks), host-serial
  native_quant_h per (expert, token), run_phase(6) (down rows). Each phase ends with wait_done + wait_parked, so every
  worker idles through the slowest gate/up task (~26 us per task at 48 tasks: 53 row pairs of ~1.7 KB at ~3.4 GB/s per
  thread) before any down row starts. --pool-tasks 96 (shorter tasks, shorter tail) measured +0.9% on real turns.
- Workers spin (pause / UMWAIT) between phases during decode, so publish -> claim is a cache-line transfer.

## Council (design mode, one round; Hermes unavailable)
- Codex gpt-6.1-sol xhigh: one epoch per layer as a task graph; CCD-local queues with stealing; per-expert gate/up
  completion counter whose last finisher runs the unchanged native_quant_h and release-publishes that expert's down
  tiles; host publishes completion before worker quiescence; estimate 5-12 us per layer; measure first.
- Gemini 4 Argon high: the same fused single epoch with per-expert quantize; CCD-affine expert slices with stealing;
  cache-line-aligned chunks; drop the post-drain wait_parked; skip actq for tokens with no CPU entry; estimate 24-33 us
  per layer (most of it from a claimed 54 -> 63-66 GB/s from CCD affinity).
- Chair (before reading the members): the same per-expert dataflow; keep workers spinning; claim down tasks of the
  expert whose gate/up finished first; measure first.

## Decision
1. STRATA_POOL_DAG=1 (opt-in, numa_n_ == 0 only): one batch per layer of gate/up tasks for every expert followed by
   down tasks ordered by expert. A per-expert counter's last gate/up finisher runs native_quant_h / act_quant_any for that
   expert's tokens (the same function on the same rows: the same bits) and release-stores the expert's ready flag
   (cleared before each batch); a down task acquires it (pausing if its expert is not ready). Down tasks are claimed in
   expert order, not "whose gate/up finished first" (the chair's design-time idea): never later than the old barrier. The phase-5 tail is filled with ready down work and
   the host's serial quantize and one publish / wake disappear.
2. Task boundaries on multiples of 16 rows (64 B of fp32 output) in the DAG mode: no output line shared by two tasks.
3. Not now: CCD-affine queues (the 54 -> 63-66 GB/s claim is unmeasured and the DRAM is already ~90% used), dropping
   the post-phase wait_parked (it guards the descriptors' lifetime; its cost after wait_done is one claim miss + one
   counter RMW), Codex's early host publication (needs the GPU flag protocol reworked).
4. Measure: ms per window of the pool (gate/up + quantize + down vs the DAG's single span) and the GPU's waitCPU, then
   real-turn A/B. Exactness: whole-engine idcheck (forced text, logits identical).

## Result (2026-11-08)
- Whole-engine identity (strata-lab idcheck sweep15, 48 and 96 tasks): IDENTICAL. Pool time per window in forced
  decode 7.19 -> 6.75 ms (-6%).
- Real-turn A/B (strata-lab runs/ab/dag1-analysis.txt, 3 rounds x 57 turns): paired geo-mean 0.997 [95% 0.980-1.014]
  against the base: neutral. On real turns the CPU share is smaller (~2.4 experts a layer) than in forced decode, so the
  saved barrier is rarely on the critical path. Not adopted; stays opt-in for when the CPU side is the bottleneck.
- Review, full tier (Hermes unavailable). L1: Codex gpt-6.1-sol 9/10, gpt-6-luna 9/10, Gemini 4 Argon 8/10. Taken:
  [P2 Sol, P3 Luna + Gemini] `ready` compared with the 32-bit batch epoch and never reset (a stale value could match
  after a wrap): now a per-batch flag cleared with gu_left while the workers are parked. Declined: [P2 Gemini]
  head-of-line spinning in the expert-major down order (a heuristic; never later than the old barrier; follow-up: a
  ready queue if the DAG is ever adopted).
  L2 (fixes only): Sol 9/10, Luna 10/10, Gemini 10/10, no findings. Post-fix whole-engine identity with the Q2_0 down
  kernel (idcheck sweep16): IDENTICAL.
