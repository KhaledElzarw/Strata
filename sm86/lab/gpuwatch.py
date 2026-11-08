"""GPU watch for the 480 W runs: nvidia-smi every 500 ms into a CSV, with a hard temperature stop.

    python gpuwatch.py --dir runs [--warn 75] [--stop 77] [--hold 2]

At --warn C it prints a warning. At --stop C held for --hold seconds it kills the Strata engine (strata.exe) and its
server (python ... serve.server), so the GPU load ends, and writes <dir>/THERMAL_STOP; scripts check for that file and
abort. The owner's limit is 75-78 C on the GPU core. nvidia-smi cannot read GDDR6X memory-junction temperature.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

FIELDS = ["timestamp", "temperature.gpu", "power.draw", "power.limit", "clocks.sm", "clocks.mem", "memory.used",
          "utilization.gpu", "clocks_event_reasons.active"]
KILL_SERVER = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*serve.server*' } | "
               "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")


def kill_strata() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "strata.exe"], capture_output=True)
    subprocess.run(["powershell", "-NoProfile", "-Command", KILL_SERVER], capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(Path(__file__).with_name("runs")))
    ap.add_argument("--warn", type=float, default=75.0)
    ap.add_argument("--stop", type=float, default=77.0)
    ap.add_argument("--hold", type=float, default=2.0)
    ap.add_argument("--interval-ms", type=int, default=500)
    a = ap.parse_args()
    d = Path(a.dir)
    d.mkdir(parents=True, exist_ok=True)
    out = d / "gpuwatch.csv"
    new = not out.exists()
    proc = subprocess.Popen(["nvidia-smi", "--query-gpu=" + ",".join(FIELDS), "--format=csv,noheader,nounits",
                             f"-lms={a.interval_ms}"], stdout=subprocess.PIPE, text=True, bufsize=1)
    hot_since, warned = None, False
    with open(out, "a", encoding="utf-8") as f:
        if new:
            f.write("epoch," + ",".join(FIELDS) + "\n")
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            now = time.time()
            f.write(f"{now:.2f},{line}\n")
            f.flush()
            parts = [p.strip() for p in line.split(",")]
            try:
                temp, power = float(parts[1]), float(parts[2])
            except (IndexError, ValueError):
                continue
            if temp >= a.warn and not warned:
                print(f"[gpuwatch] WARN {temp:.0f} C at {power:.0f} W", flush=True)
                warned = True
            elif temp < a.warn - 2:
                warned = False
            if temp >= a.stop:
                hot_since = hot_since or now
                if now - hot_since >= a.hold:
                    kill_strata()
                    info = {"epoch": now, "temp_c": temp, "power_w": power, "line": line}
                    (d / "THERMAL_STOP").write_text(json.dumps(info), encoding="utf-8")
                    print(f"[gpuwatch] STOP {temp:.0f} C for {a.hold:.0f}s at {power:.0f} W: Strata killed", flush=True)
                    hot_since = None
            else:
                hot_since = None


if __name__ == "__main__":
    main()
