<#
Start Strata with the abliterated Qwen3.8-Flash-Next (SC117 IQ3_XXS) and the tuned settings:
  DFlash2 drafter (conf 0.65), GPU expert cache sized to the VRAM free now (7100 = ~9,500 slots with the monitor on the iGPU),
  262,144-token context, 2 GiB conversation cache.
OpenAI-compatible endpoint: http://127.0.0.1:<Port>/v1   (model name: qwen3.8-flash-next-iq3_xxs)

  powershell -NoProfile -File sm86\lab\launch-strata.ps1 [-Port 19100] [-DraftConf auto|0.5|0.65]

Close VRAM-heavy apps first for the biggest cache.  The server runs in its own window; close it to stop Strata.
#>
param([int]$Port = 19100, [string]$DraftConf = "auto")
$ErrorActionPreference = "Stop"
$strata = if ($env:STRATA_DIR) { $env:STRATA_DIR } else { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$py = Join-Path $strata ".venv\Scripts\python.exe"
$lab = Split-Path -Parent $MyInvocation.MyCommand.Path
$tuned = Join-Path $strata "strata-iq3_xxs-tuned.json"
$run = Join-Path $strata "strata-iq3_xxs-run.json"

# a Strata server that is already running holds the VRAM: stop it first
Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "python.exe" -and $_.CommandLine -like "*serve*server.py*--engine*strata*") -or $_.Name -eq "strata.exe"
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
for ($i = 0; $i -lt 30 -and (Get-Process strata -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 500 }

$free = [int]((nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits) | Select-Object -First 1).Trim()
& $py (Join-Path $lab "make_run_config.py") $tuned $run $free --draft-conf $DraftConf
if (-not $?) { throw "could not write $run" }

Start-Process -FilePath $py -WorkingDirectory $strata -ArgumentList @(
    (Join-Path $strata "serve\server.py"), "--engine", "strata", "--config", $run, "--port", "$Port")

$t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt 600) {
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
        if ($h.loaded) {
            Write-Host ("Strata ready after {0:N0} s: http://127.0.0.1:{1}/v1 (model qwen3.8-flash-next-iq3_xxs)" -f ((Get-Date) - $t0).TotalSeconds, $Port)
            exit 0
        }
    } catch { }
    Start-Sleep -Seconds 2
}
throw "Strata did not report loaded within 10 minutes; see $([IO.Path]::ChangeExtension($run, '.log'))"
