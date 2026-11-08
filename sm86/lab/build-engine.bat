@echo off
rem Build the Strata engine from this checkout (two folders up, or STRATA_DIR) for the RTX 3090 only (sm_86 SASS), release-style (PORTABLE: AVX2 ggml-cpu
rem like the prebuilt package, static MSVC runtime).  Output: <checkout>\build-sm86\strata.exe + strata_kq.dll.
rem   build-engine.bat [targets...]      default targets: strata strata_kq + the HC/MMVQ/expert parity and bench tools
rem Configure runs once (delete build-sm86\build.ninja to reconfigure).  One retry: CUDA 13.0's ptxas sometimes fails on a
rem PTX file it just wrote (Strata issue #45).
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
for %%I in ("%~dp0..\..") do set "SRC=%%~fI"
if defined STRATA_DIR set "SRC=%STRATA_DIR%"
set "BLD=%SRC%\build-sm86"
set "SRCF=%SRC:\=/%"
set "CUDA=C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v13.0"
set "TARGETS=%*"
if "%TARGETS%"=="" set "TARGETS=strata strata_kq fused_gr_bench gr_parity gr_multi_parity mmvq_il_parity native_expert_parity"
if not exist "%BLD%\build.ninja" (
  cmake -G Ninja -S "%SRC%" -B "%BLD%" -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_CUDA=ON -DSTRATA_BUILD_TESTS=OFF ^
    -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_PORTABLE=ON -DSTRATA_Q6K_EXPERTS=ON -DSTRATA_MMQ_KQUANTS=ON ^
    -DCMAKE_CUDA_ARCHITECTURES=86-real "-DCMAKE_CUDA_COMPILER=%CUDA%/bin/nvcc.exe" "-DCUDAToolkit_ROOT=%CUDA%" ^
    -DSTRATA_GGML_DIR=%SRCF%/third_party/llama.cpp
  if errorlevel 1 exit /b 1
)
cmake --build "%BLD%" --target %TARGETS%
if errorlevel 1 (
  echo build failed once, retrying
  cmake --build "%BLD%" --target %TARGETS%
  if errorlevel 1 exit /b 1
)
echo built %BLD%
exit /b 0
