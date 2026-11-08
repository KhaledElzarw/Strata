# The sm86 lab

The tools and raw results behind the fork's numbers. Everything here was run on one machine: an RTX 3090 24 GB
(driver 591.86, 390 W stock power limit), a Ryzen 9 9950X, 128 GB of DDR5-5600 and Windows 11, with the abliterated
Qwen3.8-Flash-Next GSQ-RCO IQ3_XXS GGUF at a 262,144-token context.

The tools find the Strata checkout from their own location (this folder is `<checkout>/sm86/lab`), or from
`STRATA_DIR` if it is set. They need the checkout's `.venv` (Strata's setup makes it), a server config written by
Strata's setup (`<checkout>/strata-iq3_xxs.json`, the base every A/B arm starts from) and an engine built with
`build-engine.bat`.

## Tools

| Tool | What it does |
|---|---|
| `ab.py` | Interleaved A/B of engine settings on the recorded turns: `python ab.py runs/ab/exp-NAME.json`. Arms alternate every round (A B / B A / A B), each with a fresh engine, a warm-up request, then the replay. Summarize only with `python ab.py --summary runs/ab/NAME.json`: called the other way round it runs the A/B again and overwrites the results. |
| `replay.py` | Replays recorded chat requests against a running server and summarizes decode speed: `python replay.py run --src runs/replayset/hermes-v1 --label NAME`, then `python replay.py summary NAME`. |
| `readme_assets.py` | Recomputes every number and chart in the fork's README from the raw files (`../assets/results.json`, `../assets/chart-*.svg`). |
| `coldrun.py`, `coldbench.py` | Cold prompt throughput at 4K to 64K tokens, nothing reused: `python coldrun.py LABEL runs/ab/exp-res.json:q3`. |
| `idcheck.py` | Whole-engine forced decode: 1,363 scored tokens with the expert placement pinned, compared bit for bit between two configurations (Strata's `tools/force_check.py` underneath). |
| `hcbench.py` | HC-read kernel parity and timing: runs `fused_gr_bench` per variant and compares the output hashes. |
| `nsyscap.py`, `nsysconc.py`, `nsysan.py` | An Nsight Systems capture of one arm, and the per-stream, per-layer and gap analyses of its SQLite export. |
| `profsum.py`, `prof_parse.py` | Window-weighted averages of the engine's `STRATA_DECODE_TIMING` and `STRATA_VERIFY_PROFILE` lines. |
| `expmode.py`, `expsum.py`, `iltable.py` | Expert-kernel and GEMV-table bench sweeps (`native_expert_bench`, `mmvq_il_parity`). |
| `fc_config.py`, `pooled_check.py` | Phase 1's token-forcing quality checks (65 prompts x 400 tokens, both engines as scorers). |
| `make_tasks.py` | Writes the six synthetic coding tasks (`tasks/`) and their reference solutions (`tasks_ref/`); `--check` proves each task fails before and passes after. |
| `turnlog.py` | A recording proxy between an agent and the server: logs every request, which is how the replay set was captured. |
| `gpuwatch.py` | GPU temperature watchdog: writes `runs/THERMAL_STOP` above the limit, and the scripts stop. The owner's limit was 75-78 C on the core. |
| `make_run_config.py`, `launch-strata.ps1` | Write the run config with the expert cache sized to the free VRAM, and start the server. |
| `train_profile.py`, `xstest.py`, `dl_sc117.py` | An expert-profile trainer (no gain), the abliteration spot check (10 XSTest-style prompts), and the model download with `sc117-expected-sha256.txt`. |
| `build-engine.bat` | Builds `strata.exe` and the parity and bench tools for sm_86 only. |

The shell scripts (`hc*.sh`, `sweep*.sh`, `fc*.sh`, `expbench10*.sh`, `chain1.sh`, `hcfix.sh`) are the exact
experiment drivers as they ran, so they name the original machine's paths (`/c/src/Strata` and
`/d/Projects/local_ai/strata-lab`). Edit those two paths to rerun one.

## Data

| Folder | Contents |
|---|---|
| `runs/replayset/hermes-v1` | The 57 recorded turns: the six tasks solved by a local agent harness (Hermes) against the server. Each file is one chat request with the agent's system prompt and tools. |
| `runs/ab` | Every experiment (`exp-NAME.json`), its results (`NAME.json`), progress log, derived run configs (`configs/`), engine logs (`logs/`) and written analyses (`*-analysis.txt`). |
| `runs/replay` | Per-turn replay results (timings and answers) of every A/B arm, named `EXP-ARM-rROUND.jsonl`. |
| `runs/cold` | Cold prompt throughput (`q3.jsonl`, `q3pt.jsonl`). |
| `runs/hc`, `runs/id` | HC kernel parity logs and the whole-engine identity summaries (`sweep*.out`). |
| `runs/fc` | Phase 1's token-forcing results. |
| `runs/nsys` | The Nsight analyses (`*_an.txt`, `q3_conc.txt`, `q3_layers.txt`, `q3_gaps.txt`) and kernel summaries. |
| `runs/exp` | Expert-kernel bench logs. |
| `council/ceiling` | The question put to three outside models about the speed ceiling, and their answers. |

The experiments, in order: `e1`-`e8` (phase 1: drafter, expert cache, prefill chunk, draft confidence, stock
baseline), `ab3` (phase 2), `hc86` (HC read kernels), `dag1` (CPU pool batch and Q2_0 down rows), `sync1`, `tier5`,
`res` (resident HC read), and the timing and profiling runs `prof*`, `tim*`, `pf1`, `lp1`.

**Left out of the published copy:** the raw Nsight traces (about 1.1 GB), the agent harness's own install, logs and
configs that hold the machine's environment, and the bakeoff that chose the agent harness. The Windows user name in
paths is replaced with `user`, so a replayed prompt can differ from the measured one by that word.
