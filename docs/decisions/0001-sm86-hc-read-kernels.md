# 0001: HC read kernels on the RTX 3090 (sm86-decode lab branch)

Date: 2026-11-08. Status: decided by the chair (Claude Code); reversible (every change is an opt-in switch).

## Problem
One hyper-connection read (norm, down 324 x 10240, up 10240 x 320, BF16) costs 30.8-60.4 us at T = 1..8 on the 3090
(fused_gr_bench, cold weights) against a ~15 us DRAM floor; 97 reads per decode window = 3.81 ms of ~18.9 ms on real
agent turns. Hard constraint: bit-identical outputs (tier A).

## Evidence gathered before deciding
- Nsight Compute at T = 4: norm 4.6 us (16 blocks); gr_down82 19.1 us, 44% of DRAM peak, 80 x 136 threads,
  136 regs, achieved occupancy 10.9%, ~10 cycles per issued instruction (latency-bound on ~4 warps per SM);
  gr_up_wide 17.8 us, 48% of DRAM, occupancy 88%, short-scoreboard (shuffle) and long-scoreboard stalls.
- Code (fused_gr.cu): DOWN82 stages all 8 activation tiles (cp_async_wait0 + barrier) before its first FMA, and
  set_staged_attr forces a 100% shared carveout (28 KB L1) at every T; launch_multi tests UP_WIDE before UP75, so
  UP_WIDE runs at every T when on; every up kernel reloads R, bo_prev, inj_prev, w_norm, rs per token to rebuild xn.
- hcbench (bits identical in every arm): UP75 beats UP_WIDE by 4-6 us per read at T >= 4; gr_up8 is no better than
  UP_WIDE; the staged NW = 4 down is 1.5x slower than DOWN82; GR_NORM_FAST saves ~0.3 us per read.

## Council (design mode, one round; Hermes/Claude Opus unavailable: gateway "service_disabled")
- Codex gpt-6.1-sol xhigh: fast norm that also stores R_out; up consumes xn; down as 324 blocks (one row each) whose
  warps compute the 40 chunk dots into shared memory and warp 0 folds them in ascending order; up as 320 blocks with
  4 rows per warp and float4 chunk planes for lo; keep WIDE at T 1-2 and UP75 at T >= 3. Estimate 25/29/39 us at
  T 1/4/8. Flagged its own down's cost: ~4x the activation L2 traffic.
- Gemini 4 Argon high: same norm/xn idea; "gr_down81" (81 x 128: inject rows in their own block, ring 3, split the
  activation cp.async so compute starts after tile 0, no forced carveout at T <= 4, warp_sum8 in the last block);
  up = gr_up8 consuming xn. Estimate 22/27/35 us. Also flagged UP_WIDE shadowing UP75 (HIGH), and a counter reset
  in DOWN82's last block without a barrier.
- Chair (written before reading the members): T-hybrid; up with w_up staged in shared memory and warp_sum8;
  down with token-parallel owner threads.

## Decision
1. T-hybrid now: UP75 for T >= 3 when UP_WIDE is on (both existing, exact). All three agreed.
2. Norm stores R' and up consumes xn (Codex + Gemini): exact because the norm already computes R' and
   (R' * w_norm) * rs with the same expressions the up epilogue repeats; removes the up's per-token gathers.
3. Down: one new kernel on DOWN82's partition (same per-lane chunk sets, same g_d82_part + last-block butterfly +
   silu), combining Gemini's fixes (per-tile activation commit groups, carveout sized to T, inject rows not costing a
   partial warp in every block, barrier before the counter reset) with more warps per SM (token-parallel owners
   reading the weight tiles from a cp.async shared ring), because the profile says DOWN82 is latency-bound at ~4 warps
   per SM and Gemini's 128-thread block keeps that.
   Not now: Codex's one-row-per-block down (4x activation L2 traffic at T >= 3); kept as the T = 1 candidate if T = 1
   stays far from the floor.
4. Up structure beyond the hybrid (smem-staged w_up + warp_sum8 vs Codex's 320-block float4-plane layout): after 1-3,
   by measurement.
Declined: "DOWN82 counter race wedges the group" - consecutive launches on one stream are ordered by the kernel
boundary and DOWN82 is documented one-launch-at-a-time; whole-engine idcheck is identical. The new kernel adds the
barrier anyway. Backlog: gr_down_staged's token-group truncation when tg does not divide ct (not on this path).

## Result (2026-11-08)
Adopted on the lab stack: STRATA_GR_UP_WIDE=1 + STRATA_GR_UP_HYB=3 + STRATA_GR_XN=1 + STRATA_GR_DOWN86=1.
- hcbench (fused_gr_bench hashes, T 1..8, apply 0/1, inject 0/1, ring S 3 and 4): identical in every arm.
- Review, full tier (Hermes unavailable: gateway "service_disabled"). L1: Codex gpt-6.1-sol 7/10, gpt-6-luna 8/10,
  Gemini 4 Argon 8/10. Taken: [P1, Sol] the generic sentinel under STRATA_NO_MULTI_GR selected the exact T = 8 up
  instantiation (illegal access at T = 4); [P2, Sol + Luna + Gemini] DOWN86 requested its whole ring where the card's
  per-block shared memory cannot hold it (now 4 stages only where they fit with the static 256 B, else 3, else the
  next path). Declined: [P3, Gemini] UP_WIDE shadowing UP8 predates this change and every arm is exact.
  L2 (fixes only): Sol 9/10, Luna 9/10, Gemini 10/10, no findings.
- Whole-engine identity (strata-lab idcheck sweep15, forced text, 10 items, 1363 scored positions): IDENTICAL.
- A/B (strata-lab ab.py hc86, 3 rounds x 57 replayed real agent turns, arms alternating): paired median ratio 1.023,
  bootstrap 95% CI [1.015, 1.042]; round medians 156.6 / 161.0 / 158.8 -> 165.5 / 166.0 / 164.1 tok/s.
