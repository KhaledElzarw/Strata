param([string]$Name, [long]$Mask = 0x55555555, [string]$EnvSet = "", [string]$BenchArgs)
# kq_cpu_bench with a process affinity mask: 0x55555555 = one thread per physical core on a 16-core / 32-thread CPU, as the
# engine's pool runs (unpinned, Windows may put two threads on one core: 41-53 GB/s instead of 55-59 on the 9950X).
#   powershell -File kq_pinned.ps1 -Name hot-default -BenchArgs "--pairs iq3_s/iq4_nl --threads 1 --nt 1,2 --hot 1"
#   -EnvSet "STRATA_IQ_GATHER=1;STRATA_IQ_MT_MIN=1"   environment for this run only
# Output: runs/cpu/kq-NAME.txt, then one line per pair, token count and thread count.
$lab = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = if ($env:STRATA_DIR) { $env:STRATA_DIR } else { Split-Path -Parent (Split-Path -Parent $lab) }
$exe = Join-Path $root "build-sm86\kq_cpu_bench.exe"
$out = Join-Path $lab "runs\cpu\kq-$Name.txt"
foreach ($kv in ($EnvSet -split ';')) { if ($kv -match '^(\w+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') } }
$p = Start-Process -FilePath $exe -ArgumentList $BenchArgs -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError "$out.err"
$p.ProcessorAffinity = [IntPtr]$Mask   # before the threads start: the bench quantizes its blobs first
$p.WaitForExit()
foreach ($kv in ($EnvSet -split ';')) { if ($kv -match '^(\w+)=') { [Environment]::SetEnvironmentVariable($Matches[1], $null, 'Process') } }
$cur = ""
foreach ($l in Get-Content $out) {
  if ($l -match '^(\S+/\S+):') { $cur = $Matches[1] }
  elseif ($l -match 'nt (\d) threads\s+(\d+):\s+([\d.]+) GB/s') { "{0,-16} nt {1} thr {2,2}: {3,5} GB/s" -f $cur, $Matches[1], $Matches[2], $Matches[3] }
}
