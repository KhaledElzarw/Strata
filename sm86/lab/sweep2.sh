#!/bin/bash
# Phase 2: the new build (down82 v2) and the PCIe-mode switch, whole-engine bit identity vs the prebuilt reference.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep2 > runs/TAG
E='exe=C:\src\Strata\build-sm86\strata.exe'
python idcheck.py sweep2 --reuse-ref \
  --cand "$E" \
  --cand "$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1" \
  --cand "$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_GR_NORM_FAST=1" \
  --cand "$E;args=--pcie-mode dma" \
  --cand "$E;args=--pcie-mode direct" \
  --cand ""
echo "exit=$?"
echo idle > runs/TAG
