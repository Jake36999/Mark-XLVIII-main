"""Correlate bench_results.jsonl with gpu_samples.csv; print per-model summary."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ART = Path(r"F:\Mark-XLVIII-main\Jarvis_notes\Validation\2026-07-24-model-benchmark-artifacts")


def parse_ts(s: str) -> float:
    s = s.strip().rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    raise ValueError(s)


# --- load GPU samples ---
gpu = []
with (ART / "gpu_samples.csv").open(encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        try:
            gpu.append((parse_ts(row["timestamp"]), row["card"], float(row["dedicated_mib"]), float(row["util_pct"])))
        except (ValueError, KeyError):
            continue
gpu.sort()


def gpu_window(t0: float, t1: float) -> dict:
    lo, hi = t0 - 1, t1 + 1
    peak = {"GTX_1080": 0.0, "RX_5500XT": 0.0}
    util = {"GTX_1080": 0.0, "RX_5500XT": 0.0}
    for ts, card, mib, u in gpu:
        if lo <= ts <= hi and card in peak:
            peak[card] = max(peak[card], mib)
            util[card] = max(util[card], u)
    return {"vram_peak": peak, "util_peak": util}


# --- load results ---
recs = []
with (ART / "bench_results.jsonl").open(encoding="utf-8") as fh:
    for line in fh:
        if line.strip():
            recs.append(json.loads(line))

by_model: dict[str, list] = {}
for r in recs:
    by_model.setdefault(r["model"], []).append(r)

print("=" * 100)
for model, rows in by_model.items():
    load = rows[0].get("load_info", {})
    # model's loaded window = first start to last end
    starts = [parse_ts(r["started_at"]) for r in rows]
    ends = [parse_ts(r["ended_at"]) for r in rows if r.get("ended_at")]
    win = gpu_window(min(starts), max(ends)) if ends else {"vram_peak": {}, "util_peak": {}}
    vp = win["vram_peak"]
    print(f"\n### {model}   (baseline={rows[0].get('is_baseline')})")
    print(f"  load: ok={load.get('loaded')} {load.get('load_seconds')}s ctx={load.get('context')} gpu={load.get('gpu')}")
    print(f"  VRAM peak during window: GTX_1080={vp.get('GTX_1080',0):.0f} MiB  RX_5500XT={vp.get('RX_5500XT',0):.0f} MiB"
          f"  (combined {vp.get('GTX_1080',0)+vp.get('RX_5500XT',0):.0f} MiB)")
    print(f"  {'probe':6} {'ok':3} {'final':5} {'1stout':7} {'total':7} {'tok/s':6} {'finish':10} {'rsn_chars':9} check")
    for r in sorted(rows, key=lambda x: x["prompt_id"]):
        run = r.get("run") or {}
        if r.get("skipped"):
            print(f"  {r['prompt_id']:6} SKIPPED ({r['skipped']})")
            continue
        print(f"  {r['prompt_id']:6} "
              f"{str(run.get('ok')):3.3} "
              f"{str(run.get('produced_final_answer')):5.5} "
              f"{str(run.get('first_output_seconds')):>7} "
              f"{str(run.get('total_seconds')):>7} "
              f"{str(run.get('tokens_per_second')):>6} "
              f"{str(run.get('finish_reason')):10.10} "
              f"{str(run.get('reasoning_chars')):>9} "
              f"{run.get('auto_check')}")
