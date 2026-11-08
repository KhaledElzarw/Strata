# 0006: The router chain, top-10 and doorbell (sm86-decode, issue #3)

Date: 2026-11-09. Status: draft (the chair, Claude Code); every change is an opt-in switch, pending its A/B.

## Problem
Every MoE layer starts with three kernels on the main stream: the router GEMV (BF16 512 x 2560, 2.62 MB), the top-10
(`route_multi`) and the doorbell (`doorbell_publish_res_kernel`: ids to mapped memory, residency check, the MoE input
copied over PCIe when an expert runs on the CPU, the ring). The chain sits before the layer forks into the CPU pool,
the VRAM experts and the shared expert, so it is on the critical path of all three. Hard constraint: no quality loss.

## Council (design mode, one round; packet strata-lab/council/router/packet.md)
- Chair, written first: one kernel for the chain (GEMV, top-10 and doorbell; the last block of the GEMV routes).
- Gemini (gemini-4-argon-high): fuse, and before that the zero-code `STRATA_SMALL_UNR=3` (the router-shaped
  constant-trip read is on only for sm_120 in `bw_dense_defaults.hpp`); several rows a block for the GEMV.
- Codex Sol (gpt-6.1-sol, xhigh): the CUDA graph already runs the three back to back; fusion alone saves little, each
  piece must get faster. Advancing the ring by d saves d once, not twice (a correction to the packet).

## Measurements (q3 Nsight trace: 23,011 chains, ~479 windows, us)
- Gaps between the three kernels: -0.06 and 0.06 (none to remove: Sol was right).
- Router GEMV by token count (grid 512; `STRATA_SMALL_UNR` off, the q3 default): 5.50 at 1 token, 6.89 / 7.39 /
  9.51 / 10.06 / 10.41 at 2-6, 18.37 at 7-8. The DRAM floor is 2.8. It grows ~1 us a token: each of the 512 blocks
  reads every token's activations again.
- Top-10: 4.1-4.7 at every token count (one warp a token; a 15-step scan and a 5-level butterfly per rank).
- Doorbell: ~3.0 when every routed expert is resident (p10 at every token count). With a CPU expert it copies the
  input: +0.55 a token (4.06 at 2 tokens, 5.66 at 6, 6.24 at 7-8), 10 KB a token at ~18.6 GB/s: PCIe-bound.
- `STRATA_LFUSE` (the shared expert's gate row in the router launch) needs `ar_on()`: inert in q3 (#22).

## Changes (each bitwise; tier A)
1. `STRATA_SMALL_UNR=3`: zero code; idcheck sweep23 IDENTICAL; an arm of the #2 A/B.
2. `STRATA_ROUTE_BELL=1`: the top-10 and the doorbell in one launch (`native_router_top10_bell`, native_router.cu):
   one block of 16 warps, warp t routes token t with route_multi's code, its lanes 0..9 publish the ids and check the
   residency table, then the doorbell's tail unchanged (input copy as float4, system fences by every writer, barrier,
   ring). `=2` adds the REDUX top-10: order-preserving integer keys, a 4-level tree per lane, `__reduce_max_sync` /
   `__reduce_min_sync` per rank; the same picks, the winner's own value, route_multi's sums. One token too, when
   `moe_route`'s projection is `bf16_gemv_fp32_mmvf`. Parity: `route_bell_parity` (every token count, ties, +-0,
   NaN, +-inf, residency with no / some / all misses, both ring modes).
3. `STRATA_MMVF_ROWS=1` (upstream S25, 4 rows a block): zero code; to measure on sm_86.

## Results (raw output in sm86/lab/runs/bell/)
- route_bell_parity: 2,304 cases (both top-10s, 1-8 tokens, 6 logit patterns, 4 residency modes, both ring modes,
  3 repeats), 47,741,184 values compared, 0 differ.
- idcheck sweep24 (1,363 forced tokens): `ROUTE_BELL=1` IDENTICAL, `=2` IDENTICAL, `POOL_DAG=2` + `SMALL_UNR=3` +
  `ROUTE_BELL=2` IDENTICAL. The dispatch reports show the fused launch on every router layer and no fallback.
- Router GEMV alone (2560 -> 512, us per call, 1 / 2 / 3 / 4 / 6 tokens): default 5.08 / 6.22 / 6.76 / 8.66 / 10.20;
  `SMALL_UNR=1` 4.67 / 5.33 / 6.36 / 7.17 / 9.22; `MMVF_ROWS=1` 4.98 / 10.11 / 10.18 / 10.28 / 13.42 (rejected:
  1.5-1.6x slower from 2 tokens). A 5-rows-a-block variant written for this (`MMVF_ROWS=2`, hashes equal) gave
  5.29 / 5.29 / 6.44 / 6.53 / 9.24: no gain over `SMALL_UNR` at 1-3 tokens, the usual counts, so it was removed.
- The chain (router_chain_bench, 48-layer graph, median of 30, `SMALL_UNR=1`, us a layer, all resident / with misses):

  | Tokens | GEMV + top-10 + doorbell | + bell | + bell, REDUX |
  |---|---|---|---|
  | 1 | 11.00 / 11.93 | 10.40 / 10.82 | 9.58 / 10.33 |
  | 2 | 11.69 / 13.03 | 10.75 / 12.14 | 10.24 / 11.66 |
  | 3 | 12.76 / 14.81 | 11.84 / 13.53 | 11.35 / 12.97 |
  | 4 | 13.61 / 15.83 | 12.69 / 14.63 | 12.18 / 14.12 |
  | 6 | 16.11 / 18.97 | 15.17 / 17.77 | 14.95 / 17.60 |
  | 8 | 23.68 / 27.43 | 22.74 / 26.26 | 22.68 / 26.26 |

- So `ROUTE_BELL=2` saves 1.0-1.8 us a layer, 50-85 us a window (~0.4%), and `SMALL_UNR` another 0.4-1.5 us a layer
  at 1-4 tokens. Issue #3's estimate (0.5 ms a window) was too high: the three kernels already ran back to back, so
  fusing them removes only one launch's ramp and the second block, not gaps.

## Decision
Both switches are tier A and faster in the kernel bench, but together they are below the engine A/B's resolution
(~2%). Per the bundling rule they ride with the CPU pool change (0005) as one bundle: `POOL_DAG=2` + `SMALL_UNR=3` +
`ROUTE_BELL=2`, measured by one confirmation A/B against q3.

## Not taken (yet)
- The router GEMV itself: 4.7-9.2 us against a 2.8 us DRAM floor, because each of its 512 blocks reads every token's
  activations again. Fusing the top-10 into the GEMV's last block (the chair's first idea) waits on that.
- A smaller or earlier input copy (#21) and the shared-expert gate in the router launch on partial residency (#22).
