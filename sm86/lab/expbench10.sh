#!/bin/bash
# Decision 0002 step 1: the gate/up planes kernel (mode 10) against mode 0 (native_gu_swiglu, STRATA_GU_SWIGLU=1 as the
# engine's default) and mode 8, every layer of SC117 IQ3_XXS, real-turn shapes (24 groups x 1 and x 2 entries).
# native_expert_bench checks each layer's whole-expert output bitwise against the reference mode.
cd /d/Projects/local_ai/strata-lab || exit 2
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
export STRATA_GU_SWIGLU=1
B=/c/src/Strata/build-sm86/native_expert_bench.exe
G=C:/models/SC117/IQ3_XXS/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-IQ3_XXS-00001-of-00002.gguf
L=$(python -c "print(','.join(str(i) for i in range(48)))")
mkdir -p runs/exp
for shape in "24 1" "24 2" "16 1"; do
  set -- $shape
  echo "== G $1 T $2: mode 0 vs 10"
  "$B" "$G" "$L" "$1" "$2" 0 10 200 > "runs/exp/m10-vs0-g$1t$2.log" 2>&1; echo "exit $?"
  echo "== G $1 T $2: mode 8 vs 10"
  "$B" "$G" "$L" "$1" "$2" 8 10 200 > "runs/exp/m10-vs8-g$1t$2.log" 2>&1; echo "exit $?"
done
