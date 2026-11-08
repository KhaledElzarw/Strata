**CONFIDENCE 200: 55%** — reachable, but the remaining gains must come mainly from the dependent GPU chain.

Using the timing sample:

\[
K=(3.25+3.24)/2=3.245\ \text{kept tokens/window}
\]

\[
t_{200}=1000K/200=16.225\text{ ms}
\]

That requires **2.65 ms/window saved** from the measured 18.875 ms. Using **166 tok/s** as a representative replay median gives \(1000(3.245)/166=19.55\) ms/window, requiring **3.32 ms saved**. This second calculation is approximate: the replay medians and timing sample are different aggregations.

These are my predicted **whole-window critical-path savings**, not isolated-kernel savings:

| Change | Predicted saving | Why it could survive overlap |
|---|---:|---|
| Improve HC loading, reduction scheduling and epilogue fusion while preserving arithmetic | **0.5–0.8 ms** | All 97 reads sit on the dependent chain. Serialized HC down/up/norm totals 3.38 ms; the supplied cold-read rate prices the weights alone at 1.97 ms. There is room, but the resident-kernel result argues against claiming the entire gap. |
| Improve native QKV, output and head projections: weight reuse, format-specific scheduling, quantization fusion | **0.8–1.2 ms** | These projections precede the next routing decision or sampling. Their serialized categories total approximately \(1.71+1.25+0.53+0.67=4.16\) ms. Saving roughly one quarter is ambitious but compatible with the earlier bandwidth-floor estimates. |
| Fuse compatible small operations in router/top-k/doorbell and GDN chains | **0.4–0.7 ms** | Removing dependencies and launches inside the main chain matters even while another stream is occupied. This requires preserving reduction and selection behavior; it does not assume another device-planning implementation will reverse the measured regression. |
| Reduce CPU completion tails through native expert kernels and scheduling | **0.4–0.7 ms** | The traced exposed tail is \(48\times17\,\mu s=0.816\) ms/window. That is the available saving—not the entire 5 ms CPU-pool time. The checkout contains a rounding-level fused AVX-512 gate/up path, but its comments are not evidence of a gain on this machine. |
| Optimize DFlash2 projection/head/reduction work at unchanged precision | **0.3–0.5 ms** | Drafting is a separate 1.5 ms dependency. Reading 591 MiB once at 645 GB/s already costs approximately 0.96 ms, limiting how much kernel work can disappear. |

The combined opportunity is **2.4–3.9 ms/window before interactions**. Its upper half reaches 200 across the replay medians; its lower half does not. Some candidates will fail parity or paired-performance gates, which keeps my confidence near 55%.

The dependency structure is explicit in [verify.cpp](/C:/src/Strata/src/core/verify.cpp:2567). I assign **no independent saving** to faster shared-expert or VRAM-hit kernels while CPU completion still determines combine time.

**CONFIDENCE 250: 10%** — physically possible, but the evidence does not establish a sufficient optimization budget.

\[
t_{250}=1000(3.245)/250=12.98\text{ ms/window}
\]

Required savings are **5.90 ms** against the timing sample, or approximately **6.57 ms** against the representative replay median. Even the optimistic end of the changes above leaves another **2–3 ms** to find.

A credible route needs those five changes plus either:

- **Another 2–3 ms from the dependent dense chain**, beyond the estimates above. That would require a substantial kernel/scheduling advance.
- **More accepted work per window without proportional additional cost.** For example, \(3.8/15.2\text{ ms}=250\) tok/s. That requires about **17% more kept tokens/window** alongside substantial latency reductions.

I do not credit that acceptance improvement today. The policy already prices measured window costs, larger windows consume more expert work, and lowering draft confidence has already lost performance. Acceptance of 0.77 alone is insufficient to predict the benefit: acceptance, window length and routing cost are correlated.

**CEILING: theoretical upper bound ≈820 tok/s at today’s mean kept window; practical estimate ≈220 tok/s, with a plausible excellent-engine range of 210–235. Today ≈20% / 75% of those point estimates.**

The **820 number is a loose bandwidth upper bound, not an attainable performance forecast**.

Assuming the supplied resident dense-weight inventory is traversed once per verify window:

\[
B_{\text{dense}}=(1466+2069)\times2^{20}=3.707\text{ GB/window}
\]

\[
t_{\text{dense}}\ge3.707/936=3.960\text{ ms/window}
\]

\[
R\le3.245/0.003960=819\text{ tok/s}
\]

This omits routed experts, KV traffic, drafting, intermediate traffic and synchronization. Consequently, it deliberately overstates achievable speed.

HC alone requires:

\[
97\times2\times320\times10240\times2
=1.2714\text{ GB/window}
\]

That is **1.36 ms at 936 GB/s**, or **1.97 ms at the measured 645 GB/s**. Those are weight-read times before reductions, normalization and dependency overhead.

A more useful, **conditional resource roof** is approximately **310–390 tok/s**:

- CPU expert-weight demand, using the supplied mean blob size:

\[
48\times2.78\times1.66\text{ MiB}=232\text{ MB/window}
\]

\[
232\text{ MB}/60\text{ GB/s}=3.87\text{ ms}
\]

- Treating approximately 3.6 GB of dense weights as dependent work, excluding the forked shared-expert portion, gives **3.85–5.58 ms** at 936–645 GB/s.
- One draft-weight traversal adds approximately **0.66–0.96 ms**.
- If GPU expert work fits inside the CPU interval:

\[
t_{\text{window}}\gtrsim(3.85\text{–}5.58)+3.87+(0.66\text{–}0.96)
=8.38\text{–}10.41\text{ ms}
\]

\[
R\lesssim312\text{–}387\text{ tok/s}
\]

This is a roofline calculation using **measured sustained DDR bandwidth**, not a certified physical bound. Selected expert sizes, cache reuse and actual GPU expert traffic need verification.

In particular, **32.4 VRAM-hit pairs are not necessarily 32.4 separate expert reads**. The [expert kernels](/C:/src/Strata/src/kernels/cuda/iq_kernels.cu:2450) already decode weights once and apply them to multiple entries.

My practical estimate of **220 tok/s** means a **14.75 ms/window** budget. The limits are dependent dense kernels, roughly 48 CPU/GPU rendezvous, expert-tail variability, drafting and WDDM scheduling—not raw bandwidth alone. Relative to 166 tok/s, reaching it requires approximately **33% more throughput**, or **25% less window time**.

An absolute number independent of window policy cannot be inferred. Allowing eight perfectly accepted tokens changes even the loose dense-only bound to approximately **2,020 tok/s**. The supplied evidence does not support that acceptance behavior.

**PREFILL: cold 64K now ≈21 s / estimated practical floor 11–15 s; warm median now 842 ms / estimated practical floor 400–550 ms.**

These floors are engineering estimates, with less confidence than the decode estimates.

| Cold prompt | Now | Estimated practical floor |
|---|---:|---:|
| 4K | 1.8–2.1 s | **1.2–1.5 s** |
| 16K | 5.6–5.7 s | **3–4 s** |
| 32K | 11.1–11.4 s | **5.5–7.5 s** |
| 64K | 21.0 s | **11–15 s** |

For a 32K chunk, borrowing 8,211 slots leaves approximately 1,293 resident slots:

\[
B_{\text{stream}}\approx39.97\text{ GiB}-1293(1.66\text{ MiB})
=37.87\text{ GiB}
\]

\[
t_{\text{stream}}\ge37.87\text{ GiB}/26.8\text{ GB/s}=1.52\text{ s/chunk}
\]

Restoring the 13.27 GiB loan requires another:

\[
13.27\text{ GiB}/26.8\text{ GB/s}=0.532\text{ s}
\]

Thus two 32K chunks plus one refill have approximately a **3.56 s aggregate PCIe traffic floor**. The measured 21 s cannot be explained by saturated bulk PCIe alone.

The model geometry also implies substantial arithmetic per prompt token:

\[
F_{\text{routed}}
=48\times10\times3\times2560\times640\times2
=4.719\text{ G operations/token}
\]

HC contributes **1.271 GFLOP/token**. GDN/QSA projections, shared experts and routing bring the projection subtotal to roughly **7.2 GFLOP/token**, excluding routed experts.

Optimistically pricing projections at 71 TFLOP/s and routed integer-dot work at 284 TOPS:

\[
t_{\text{compute}}\gtrsim7.2/71000+4.719/284000
=0.118\text{ ms/token}
\]

That is approximately **7.8 s for 64K**, before attention, recurrence, dequantization, partial tiles and control overhead. Those peak rates use FP32 accumulation and dense, rather than sparse, throughput. [NVIDIA GA102 specifications](https://www.nvidia.com/content/PDF/nvidia-ampere-ga-102-gpu-architecture-whitepaper-v2.1.pdf)

Do **not** add 7.8 s and 3.56 s mechanically: copies and computation overlap. Conversely, neither number is a prediction that the engine can operate at its peak throughout. Together they support an excellent-engine floor around **11–15 s**, while leaving today’s largest prefill bottleneck unresolved without stage timing.

For warm turns, the fit implies a representative suffix size:

\[
N_{\text{new}}\approx(842-505)/0.404=834\text{ tokens}
\]

Approximately **337 ms scales with new tokens** and **505 ms is the fitted intercept**. The intercept is not proof that 505 ms is removable housekeeping.

A 400–550 ms engineering floor corresponds, for example, to:

\[
150\text{–}250\text{ ms fixed}
+(0.30\text{–}0.36)\times834
=400\text{–}550\text{ ms}
\]

There is insufficient transfer-byte and checkpoint evidence to calculate a firm warm-turn hardware floor.

The top changes would be:

1. **Reduce redundant conversation parking, checkpoint copies and restore synchronization.** Predicted warm saving: **150–250 ms/turn**, conditional on those operations accounting for that much exposed time. Park-gain’s measured benefit supports investigating this path.
2. **Improve dense/HC prefill GEMMs and overlap dequantization while preserving precision.** Predicted cold-64K saving: **2–4 s**; warm saving: **20–50 ms**. This prediction needs dense-stage timing to establish its available budget.
3. **Improve expert grouping, gather/compute fusion and buffer lifetimes.** Predicted cold-64K saving: **2–4 s**; warm saving: **40–90 ms**. Preserve existing activation quantization and expert arithmetic; credit only exposed copy/grouping stalls.

These savings interact and should not be added at their maxima. Also, the checkout already [sizes loans per prompt segment](/C:/src/Strata/src/program/generate.cpp:17009) and [queues refills before waiting](/C:/src/Strata/src/program/generate.cpp:16945). Neither behavior is an unimplemented optimization opportunity.

**WHAT WOULD CHANGE MY MIND:** an untraced, paired replay showing **at least 3.3 ms/window net saving**, unchanged kept-token yield and passing quality checks would move my 200 confidence substantially upward. For 250, the strongest evidence would be **3.8 kept tokens at ≤15.2 ms/window**, or the current yield at ≤12.98 ms.

The most useful diagnostic is a per-window record of **dependent dense time, exposed CPU tail, unique expert bytes, window width and kept tokens**. For prefill, separate exposed compute/copy waits from cache restore, checkpoint and refill time.

**UNCERTAIN:**

- **Quality reference for prefill.** The [CPU-share code](/C:/src/Strata/src/prefill/prefill.cpp:268) documents output differences. KL 0.004–0.011 does not establish rounding-only equivalence. I have treated the adopted path as the performance baseline; its status against the owner’s quality reference remains unresolved.
- **Actual occupied context.** These estimates concern the supplied replay distribution with native 262K capacity retained. They do not establish equivalent speed at 262K occupied tokens. Sparse KV access also does not imply streaming the entire 3.09 GiB every window.
- **Exact traffic and overlap.** Selected expert sizes, unique GPU expert counts, cache reuse and untraced layer timing are missing. Nsight inflation cannot safely be removed using one universal scale factor.
- **Thermal sustainability.** I assumed the reported power and temperature envelope. Sustained clocks and memory-junction temperature could reduce practical ceilings.
- **Verification:** independent static assessment of checkout `adc1c1294`; supplied measurements were not reproduced. No edits, builds, tests or benchmarks. Tracked tree clean; existing untracked `dflash2/`, `engine-feed/`, and `strata-iq3_xxs.json.bak` remain. Rollback: not applicable.

