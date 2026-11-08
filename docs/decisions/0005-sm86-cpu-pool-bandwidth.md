# 0005: CPU expert pool bandwidth (sm86-decode, issue #2)

Date: 2026-11-09. Status: decided by the chair (Claude Code); every change is an opt-in switch.

## Problem
In decode the CPU pool (15 workers + the host, Ryzen 9 9950X, 2 x 64 GB DDR5-5600) computes about 10% of the routed
experts: 2.77 a layer-window, 232 MB of weights a window. The GPU waits on it 27-31 us a layer (1.3-1.5 ms of an 18.9 ms
window). The pool's gate/up phase reads its weights at about 44 GB/s and its down phase at about 54 GB/s, against a
read ceiling of 60-64 GB/s on this machine (sm86/lab/bwbench.cpp). Hard constraint: no quality loss (tier A first).

## Council (design mode, one round; packet ~/.claude/squad/local_ai/briefs/cpu-bw-1.md)
- Chair, written first: measure the kernels per format; prefetch the likely CPU experts into L3 (#18); ring the
  doorbell earlier (#3).
- Gemini (gemini-4-argon-high): one-token gate/up falls through to ggml-cpu's AVX2 dot (true: `x512_one` needs
  `iq512_gather_on()`, which is Intel-only, and types 18/21), modelled at 33-38 GB/s against 56-58 GB/s for the
  multi-token kernels; build an AVX-512 one-token path for all five i-quants and IQ4_NL; fix the DAG's cut16 balance
  and its expert-order down claims. Estimate 0.74-1.11 ms a window. First test: STRATA_IQ_MT_MIN=1.
- Codex Sol (gpt-6.1-sol, xhigh): warm the caches with the experts the previous window missed, during the 230 us the
  pool idles; estimate 0.3-0.9 ms a window; kill it if the prediction misses the expensive jobs.

## Measurements
- Repeat rate (STRATA_ROUTE_DUMP on the 57 recorded turns, sm86/lab/routestats.py): the previous window's misses
  cover 20.0% of a layer's miss bytes; the last 16 windows cover 51.5% with a 47.6 MB set a layer. Sol's priming and
  #18 are dead on these numbers (#18 closed).
- Kernels (kq_cpu_bench, synthetic ggml-quantized weights): one core computes 5.0-6.5 GB/s of weights cache-resident
  at one token. STRATA_IQ_MT_MIN=1 is slower or equal at one token on every format (Gemini's own kill rule).
  STRATA_IQ_GATHER=1 is bit-identical (cpu_dispatch_dump, 485 hashes) but mixed: IQ3_S faster, IQ3_XXS slower.
  From DRAM, 15 threads pinned one per physical core reach 55-59 GB/s at one token and 52-57 GB/s at two
  (89-95% of 62): the one-token ggml path is not slow, so Gemini's model is declined. Unpinned, the same threads
  reach 41-53 GB/s (the engine pins: pool.cpp, issue #40).
- The pool itself (new sm86/lab/pool_replay_bench.cpp: the dump's CPU jobs through the engine's ExpertPool, real
  per-layer formats, cold DRAM, 230 us between layers): 4.54-4.62 ms of pool calls a window (the engine measures
  4.95), gate/up 49 GB/s, down 52 GB/s, 4.2 experts and 5.7 token rows a call, 74.5% of the jobs one token.
  The gap to the kernels' 57 GB/s is the per-call structure (two phases, two barriers, short tasks), not the kernels.

- Pool variants in the replay bench, 3 interleaved rounds over 600 windows (other sessions load this machine, single
  runs drift up to 15%), median ms of pool calls a window, every arm the same output hash (bit-identical):

  | arm | median | vs base |
  |---|---|---|
  | base (two phases a call) | 5.197 | |
  | STRATA_POOL_DAG=1 (decision 0003) | 4.834 | -7.0% |
  | STRATA_POOL_DAG=2 (new: down slots in gate/up completion order) | 4.788 | -7.9% |
  | DAG=2 + --pool-tasks 96 | 4.939 | -5.0% |
  | DAG=2 + STRATA_POOL_PF=2 (first 4 KB of each row stream) | 4.981 | -4.2% |
  | DAG=2 + STRATA_POOL_PF=1 (a task's rows into L2) | 5.097 | -1.9% |
  | STRATA_POOL_PF=1 alone | 5.716 | +10% |

  Software prefetch hurts (it competes with the hardware prefetcher and the other cores' demand reads). DAG 1 and 2
  are within each other's noise; 2 never waits on an unfinished expert while another's down rows are ready, so it is
  the one tested in the engine.

## Decision
Not adopted: `STRATA_POOL_DAG=2` stays an opt-in switch (off by default), like DAG 1 (0003: 0.997 [95% 0.980-1.014]).

- Engine A/B pool2 (3 interleaved rounds x 57 real turns: q3, q3 + `POOL_DAG=2`, q3 + `POOL_DAG=2` + `SMALL_UNR=3`;
  sm86/lab/runs/ab/pool2.*): another session's game and editor ran on the GPU during it. Contended turns by round:
  q3 23 / 56 / 13, DAG2 47 / 56 / 0, DAG2 + SMALL_UNR 0 / 10 / 0 of 56-57, which inflated the last arm to a paired
  geo-mean of 1.079. On the pairs with no other GPU program listed (sm86/lab/ab_clean.py): DAG2 1.027 [0.998-1.063]
  (n = 43), DAG2 + SMALL_UNR 1.031 [1.008-1.056] (n = 76).
- On that result the engine part had its code review: Codex Sol (gpt-6.1-sol, xhigh) 9/10 and Gemini
  (gemini-4-argon-high) 9/10, no findings.
- Confirmation A/B conf1 (4 interleaved rounds x 57 turns; replay.py waits before each timed turn until no other
  program has used >= 5% of the SMs for 30 s, and an `nvidia-smi pmon` log drops the turns still overlapped): q3
  against `POOL_DAG=2` + `SMALL_UNR=3` + `ROUTE_BELL=2` (0006); 6 of 449 timed turns overlapped. Clean pairs:
  median 1.022, geo-mean 1.011 [0.997-1.025] (n = 216); all pairs 1.010 [0.996-1.024] (n = 222). Round medians
  160.0 / 163.2 / 165.4 / 160.8 -> 169.9 / 163.8 / 163.9 / 166.7 tok/s; prompt time 1.003 [0.991-1.018].
- Below the adoption bar (>= 2%, CI excluding 1). The pool2 gain did not reproduce under the gate: its filter saw only
  which programs held a GPU context, and nothing logged the CPU load the same programs put on the pool's cores (#24).
  The replay bench's 0.41 ms fewer pool milliseconds a window (7.9%) would be about 2% if all of it reached the
  window; the bundle, with all three changes, measured 1.1%.
