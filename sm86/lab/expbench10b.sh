#!/bin/bash
# Post-rebuild check of the Q2_0 down kernel (mode 10) after the gate/up mode 10 code was removed: mode 8 vs 10.
cd /d/Projects/local_ai/strata-lab || exit 2
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
export STRATA_GU_SWIGLU=1
B=/c/src/Strata/build-sm86/native_expert_bench.exe
G=C:/models/SC117/IQ3_XXS/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-IQ3_XXS-00001-of-00002.gguf
L=$(python -c "print(','.join(str(i) for i in range(48)))")
for shape in "24 1" "24 2"; do
  set -- $shape
  "$B" "$G" "$L" "$1" "$2" 8 10 200 > "runs/exp/m10b-vs8-g$1t$2.log" 2>&1; echo "G $1 T $2 exit $?"
  python expsum.py "runs/exp/m10b-vs8-g$1t$2.log" | grep -E "^==|q2_0|all layers"
done
