# Engineering notes: Strata on one RTX 3090

What was measured, what was learned, and what did not work, in the order the work happened (2026-11-07 to
2026-11-08). The fork's [README](../README.md) has the results; the kernel reasoning is in
[`docs/decisions`](../docs/decisions/). Unless a line says otherwise, a gain is a paired, interleaved A/B on the 57
recorded agent turns of [`lab/runs/replayset/hermes-v1`](lab/runs/replayset/hermes-v1).

## Setup

RTX 3090 24 GB on PCIe 4.0 (26.8 GB/s measured host to device), Ryzen 9 9950X (16 cores), 128 GB DDR5-5600,
Windows 11, NVIDIA driver 591.86 at the stock 390 W power limit. The model is the abliterated Qwen3.8-Flash-Next
GSQ-RCO IQ3_XXS GGUF: 48 layers (36 linear-attention GDN, 12 QSA attention), 512 experts with 10 routed per token,
hyper-connections with 4 streams, and about 40 GiB of expert weights. Context: 262,144 tokens, the model's native
maximum.

## Phase 1: configuration (2026-11-07)

**Free VRAM was the biggest lever, not a setting.** With VRAM-heavy desktop apps open, stock Strata held 6,377
experts on the GPU and replayed at 126.5-131.5 tok/s per round; with them closed it held 9,724 and replayed at
150.0-151.2. Moving the display to the CPU's integrated GPU freed another 1.27 GB.

What the phase-1 configuration changed, together +2.2% over stock (95% CI +0.3 to +4.1; same evening, not
interleaved):
- **The DFlash2 drafter with its tuned pack.** On this card stock Strata silently fell back to the MTP drafter: a
  CUDA IQ3_XXS start that is not "resident" never picked the tuned `selq4` pack. `STRATA_DRAFT_PACK` and a config
  `draft_pack` key fix that (+3.5% at about 6,500 expert slots).
- **An explicit GPU expert cache**, sized by the launcher to the VRAM free at start. Auto sizing either shrank to
  6,490 slots with apps open or, with them closed, left only 0.42 GB free, below the ~0.9 GB under which decode can
  stall. `--expert-cache 7100` gives 9,504 slots and keeps about 1.3 GB free.
- **DFlash2 confidence 0.65.** 0.5 was 1.9% slower (paired 0.981, 95% CI 0.965-0.997).

Two Windows limits matter here:
- **The per-process VRAM budget.** Under WDDM one process gets at most about 23,556 MiB of the 3090's 24 GB, even
  with no display on the card. The engine sees that budget and `nvidia-smi` does not, so the launcher caps its
  sizing at 23,550 MiB.
- **The commit limit.** Windows caps the memory all programs can reserve at RAM plus the page file, whether or not
  it is ever written. Strata reserves a lot (the CPU's expert arena, the 3.09 GiB context buffer in RAM, the
  conversation cache), and at the cap the next allocation fails, which can crash the engine without a message
  (0xC0000409). A fixed 64 GB page file raised the cap to 189.6 GiB. Decode speed is unchanged: nothing is paged.

Tried and dropped: an expert profile learned from real turns (no gain; the cache already adapts, hit rate 90-91%
either way), `STRATA_EXPDEC=1` (3.0% slower), the other HC kernel variant `GR_V3` (3-6% slower on other sm_86 cards),
and a 480 W power limit (not tried: at 390 W the core already reaches 75-77 C).

**Quality.** A token-forcing check (65 prompts x 400 tokens, expert placement pinned so every arm rounds the same
way) passed: DFlash2 text against stock text +0.07 points of mismatch rate (90% CI -0.24 to +0.37; the limit is 0.5).
Ten of ten XSTest-style prompts were answered, none refused, and all 18 live coding tasks passed their tests.

**Temperature.** Real agent use, where tool runs give the GPU short breaks, peaks at 75-76 C; turns run back to back
reach 77 C. A cooler card decodes about 3% faster, because it boosts higher under the same power cap.

## Phase 2: exact engine switches (2026-11-08)

+6.0% decode (95% CI +3.9 to +8.1) and -13.5% prompt time per turn:
1. The HC down projection on all 80 blocks instead of 41 (`STRATA_GR_DOWN82=1`), with the wide HC up read, the PCIe
   share's copy on its own stream beside the VRAM experts (`STRATA_FETCH_FORK=1`) and stream priorities: +1.0%.
2. GEMV tables measured on this 3090 (`STRATA_MMVQ_IL_3090=1`): +1.8%.
3. The expert kernel layout chosen per weight format (`STRATA_EXP_MODE=9`): expert kernel time -11 to -17% on all 48
   layers, but little end to end (see below).
4. The prompt path: a conversation re-parked only after 8,192 new tokens (`--conversation-cache-park-gain 8192`;
   parks went from 57 to 19 per replay) and asynchronous, pooled checkpoints (`STRATA_CKPT_*`).

**Where the time went** (Nsight Systems, 484 decode windows): the GPU is busy 98% of each window, and launch gaps cost
only 0.3 ms per window, so kernels that only save launches do not help. The MoE step waits on the CPU's share of the
missed experts: when the GPU expert kernels got 12% faster, the GPU just waited longer for the CPU.

Tried and dropped: one persistent HC kernel (`STRATA_HC_PERSIST=1`, rounding-level: 0.5% slower), 8-bit HC weights
(`STRATA_HC_Q8=1`: +0.9%, not worth its KL of 0.025), a PCIe share of 0.4 (+0.5 to +0.9%, noise) and of 0.5-0.6
(8-12% slower, because the CPU and PCIe reads share the same DDR5 bandwidth), AVX-512 gathers on the CPU path (0.8%
slower on Zen 5), one expert layout for every format, and requesting all HC down weights at once.

## Phase 2b: new exact kernels (2026-11-08)

Adopted, each bit-identical (kernel parity benches and the whole-engine forced decode at all 1,363 positions):
1. **New HC read kernels**: the DOWN86 ring (token-parallel owners reading weight tiles through a `cp.async`
   shared-memory ring), the up T-hybrid (UP75 from 3 tokens) and the norm-computed `xn`. +3.7% (95% CI +2.1 to +5.5).
   [Decision 0001](../docs/decisions/0001-sm86-hc-read-kernels.md).
2. **Q2_0 expert down rows on 4 lanes** (`STRATA_EXP9_DOWN=42:10`): the butterfly's first two levels become in-lane
   adds in the same order. Down time 0.47-0.96 of the previous kernel's. +2.0% (95% CI +0.4 to +3.6) on top of the
   POOL_DAG arm, +1.6% (-0.1 to +3.3) over the plain base. [Decision 0002](../docs/decisions/0002-sm86-vram-expert-kernels.md).
3. **Tier 5**: the step's doorbell number stored instead of read back over PCIe, the VRAM hits folded into the
   combine, no CPU activation for tokens with no CPU expert, the HC up plane layout and the DOWN87 kernel. +4.7%
   (95% CI +2.6 to +6.9).

Not adopted, both exact: one resident cooperative HC-read kernel (`STRATA_GR_RES=1`; about 4 us faster per read
alone, about 0.15 ms per window inside the engine, neutral on real turns,
[decision 0004](../docs/decisions/0004-sm86-hc-resident-read.md)), and the CPU pool as one batch per layer
(`STRATA_POOL_DAG=1`; pool time -6% in forced decode, neutral on real turns,
[decision 0003](../docs/decisions/0003-sm86-cpu-expert-pool-dataflow.md)). Windows large pages for the CPU expert
arena: +0.7%, within noise.

**Where the time goes now.** A verify window takes 18.9 ms and keeps 3.24 tokens (3,048 timed windows): the host
waits 11.0 ms for the GPU's dense chain to reach each layer's expert step, spends 5.0 ms in the CPU expert step,
1.5 ms drafting, and about 1.4 ms on everything else. Per layer the dense GPU chain (HC reads, attention or linear
attention, projections, router) is on the critical path; in the Nsight timeline the GPU's expert work ends at about
88 us into the expert step and the CPU pool's at about 105 us (both inflated by the trace). The CPU pool reads about
232 MB of experts per window at about 47 GB/s, of the 75-80 GB/s that DDR5-5600 delivers.

**Prefill.** Cold prompts: 4K about 2,100 tok/s, 16K and 32K about 2,900, 64K about 3,100 (21 s). Real agent turns:
median 0.87 s, a fixed ~0.49 s plus ~0.42 ms per new token. At 32K the GPU time splits into experts 24%, HC 18%,
attention 17%, linear attention 14.5% and PCIe waits 4%: prefill is bound by compute and kernel efficiency, not by
the bus. Upstream's prefill CPU share (prompt chunks up to 3,072 tokens) is left as upstream ships it, with a
disclaimer in the README; its documented KL against GPU-only is 0.004-0.011.

## What is next

At 3.24 tokens a window, 200 tok/s needs 16.2 ms a window and 250 needs 13.0 ms. The exact savings identified so far
are estimated at 2.4-3.9 ms: the CPU pool's bandwidth (0.7-1.4 ms), the HC and dense projections (1-2 ms), one kernel
for router, top-k and doorbell (about 0.5 ms), fusing the small linear-attention kernels (about 0.5 ms) and the
drafter (about 0.4 ms). More tokens a window would raise every number one for one, but that needs a different draft
model. The outside estimates are in [`lab/council/ceiling`](lab/council/ceiling).

Also open: the route-tail skip (upstream's default, slightly lossy, KL 0.003-0.006), which has not been measured on
against off here. Every open idea is an [issue](https://github.com/KhaledElzarw/Strata/issues).
