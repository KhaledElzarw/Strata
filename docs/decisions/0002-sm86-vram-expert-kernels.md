# 0002: VRAM expert kernels on the RTX 3090 (sm86-decode lab branch)

Date: 2026-11-08. Status: decided by the chair (Claude Code); reversible (a new per-format mode behind STRATA_EXP_MODE=9's
table and STRATA_EXP9_GU / STRATA_EXP9_DOWN).

## Problem
VRAM-resident routed experts cost 3.35 ms per decode window on real agent turns (DRAM floor ~2.05 ms): ~70 us per layer.
Hard constraint: bit-identical outputs (tier A); every layout must equal mode 0 bit for bit (native_expert_bench checks
each call).

## Evidence
- Nsight Compute (native_expert_bench, real SC117 rows): IQ2_XXS / IQ2_XS gate/up issue-bound (not-selected and
  math-pipe stalls, ~430 GB/s); Q2_0 down ~360 GB/s, latency-bound; IQ4_NL down long-scoreboard bound.
- Code (iq_kernels.cu): mode 8's native_gu_fused_kernel runs 32-lane warps over 80 items per row (third pass half idle,
  83% lane use) and calls DotG<TG, 1>::f inside the entry loop, so each entry re-decodes the weights; DotG's SG=1 sign
  path costs 4 DP4A per 8 weights instead of 2. IQ2_XS (type 17) is in neither fused_gu nor lds_gu, so
  STRATA_EXP9_GU=17:8 silently ran the unfused CUDA layout: the "IQ2_XS keeps mode 0 (8: 1.01-1.07)" note measured
  that, not a fused IQ2_XS kernel (Gemini found this; confirmed by reading lines 6395-6452).
- At real T (3.55 tokens), cap = T x 10 block rows and ~1.3 entries per VRAM group, so per-entry reuse of decoded
  weights pays little; lane use and instructions per item are what count.

## Council (design mode, one round; Hermes unavailable: gateway "service_disabled")
- Codex gpt-6.1-sol xhigh: two launches (gate/up + SwiGLU + q8_1, then down); decode signed weight bytes once per item
  and reuse across entries; 16-lane subwarps; planar activations; Q2_0 16-lane exact reduction with 2 rows per
  subwarp; IQ4_NL 8-lane with 2 rows; NC = 1 / 2 specializations; target 55-60 us/layer (2.6-4%).
- Gemini 4 Argon high: same two launches; 16-lane subwarps for gate/up with the exact split-chain tree (s over
  t, t+32, t+64; s16 over t+16, t+48; s + s16; xor 8..1); add IQ2_XS to the fused family; hoist decode out of the
  entry loop; sign-expanded bytes via (g ^ m) + (m & 0x01010101) (exact: every grid byte >= 1); __launch_bounds__(256, 4);
  grid-stride over groups. Target ~58 us/layer in the 24x2 bench.
- Chair (written before reading the members): signed-byte decode (fewer instructions per weight byte), more rows per
  warp for Q2_0, no gate/up + down fusion (the down needs the whole 640-wide h of an entry).

## Decision
1. New gate/up kernel (mode 10, per format through exp9_mode): 16-lane subwarps, two rows per subwarp, the exact
   split-chain tree, weights decoded once per item into signed int8x4 words then 2 DP4A per 8 weights per entry, the
   same integer post-processing and float expressions as DotG, mode 8's SwiGLU + q8_1 epilogue unchanged. All five
   formats including IQ2_XS. Adopt per format only where native_expert_bench shows bitwise equality and a speedup.
2. Down (after 1, by measurement): Q2_0 and IQ4_NL with narrower lane groups that fold the 32-lane tree in-lane
   (exact: the butterfly's upper levels become in-lane adds in the same order, keeping the +0.0 adds of idle lanes).
3. Not now: __launch_bounds__(256, 4) as a blanket rule (try it per kernel against spills); grid-stride over groups
   (the device-side group count is unknown at capture; measure the cost of empty block rows first).
Backlog (already on the branch, not this change): mode 5-8 kernels ignore L.tail_off (zero for this model; a layout with
tail scales would differ from mode 0, which the bench would show); native_gu_fused_kernel's SwiGLU product lacks
__fmul_rn (bitwise equal today per the bench; the new kernel uses __fmul_rn like the reference).

## Result (2026-11-08, native_expert_bench on all 48 layers, groups x entries 16x1 / 24x1 / 24x2, strata-lab runs/exp/m10-*)
- Gate/up as built (mode 0's 16-lane rows + decode-once, with the chunk's q8_1 activations staged in shared memory as
  planes): bitwise equal on every layer, but slower than the per-format layout EXP_MODE=9 already runs where it matters.
  Gate/up time against mode 8 at 24x1: IQ2_S 1.148, IQ2_XXS 1.070, IQ3_S 1.206, IQ3_XXS 1.130; only IQ2_XS gains
  (0.943 of mode 0's unfused gate/up at 24x1; the bench's gate/up phase does not run the engine's fused mode 0
  kernel, so the real gain is at most ~0.1% of a decode window). Dropped; the code is removed.
- Down Q2_0 at n_ff 640 (native_down_q2_sub4_kernel, STRATA_EXP9_DOWN=42:10): bitwise equal on all 30 Q2_0 layers in
  every shape; down time against mode 8 (EXP_MODE=9's Q2_0 default) 0.947 / 0.955 / 0.663, against mode 0
  0.776 / 0.726 / 0.519; after the review fixes, at 8 groups x 3 / 4 / 5 / 8 entries (chunks of 3 and 4, 4 + 1, two
  chunks): 0.683 / 0.676 / 0.658 / 0.470, bitwise equal. Whole-engine identity (strata-lab idcheck sweep15): IDENTICAL.
  Real-turn A/B (strata-lab runs/ab/dag1-analysis.txt, 3 rounds x 57 turns): over the POOL_DAG arm paired geo-mean
  1.020 [95% 1.004-1.036], over the base 1.016 [1.000-1.033]. Adopted (STRATA_EXP9_DOWN=42:10).
- IQ4_NL down (mode 0 today): not built yet; the next candidate of point 2.
- Review, full tier (Hermes unavailable). L1: Codex gpt-6.1-sol 9/10, gpt-6-luna 9/10, Gemini 4 Argon 8/10. Taken:
  [P2, Gemini] a global STRATA_EXP_MODE=10 left gate/up on the unfused fallback (gs_layout now accepts mode 10).
  Declined: [P2, Gemini] strided group calls keep em_call 0 (the reference layout) by design; backlog: per-format
  layouts for the PCIe groups. Chair P3: static_assert(GRP_NC == 4).
  L2 (fixes only): Sol 9/10, Luna 10/10, Gemini 10/10, no findings. Post-fix whole-engine identity (idcheck sweep16,
  base + Q2_0 kernel, + POOL_DAG, + FUSE_WAIT=2, + VERIFY_DEVICE_PLAN=1): IDENTICAL.
