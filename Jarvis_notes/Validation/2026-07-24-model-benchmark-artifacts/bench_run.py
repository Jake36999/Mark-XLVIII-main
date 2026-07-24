"""Local-model characterization benchmark runner (2026-07-24).

For each model: force a cold start (unload), time an explicit `lms load
--gpu max --parallel 1`, then run each prompt via the LM Studio streaming API
(direct, pinned model, no router fallback, generous timeout) capturing
time-to-first-token, total latency, throughput, and output. Unload after.
GPU VRAM/util for BOTH cards is captured separately by gpu_monitor.ps1 and
correlated by timestamp afterward. Results append to a JSONL so the run is
crash-resilient and resumable.

Sequential by design -- never concurrent LM Studio calls (concurrency
corrupts timing, proven earlier this session).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

# Background output is redirected to a file; ensure unicode (lms spinner chars,
# model output) never crashes a print on a cp1252 console.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ART = Path(r"F:\Mark-XLVIII-main\Jarvis_notes\Validation\2026-07-24-model-benchmark-artifacts")
sys.path.insert(0, str(ART))
sys.path.insert(0, r"F:\Mark-XLVIII-main\Mark-XLVIII-main")

import requests

from bench_prompts import (  # noqa: E402
    BASELINE_MODELS,
    BASELINE_SUBSET,
    CANDIDATE_MODELS,
    NEEDLE_ANSWER,
    PROMPTS,
)

RESULTS = ART / "bench_results.jsonl"
LMS_API = "http://localhost:1234/v1/chat/completions"
LOAD_CONFIGS = [(8192, "max"), (4096, "max"), (4096, None)]  # try in order until one loads
GEN_TIMEOUT = 600
LOAD_TIMEOUT = 480


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def _done_keys() -> set[tuple[str, str]]:
    done = set()
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done.add((rec["model"], rec["prompt_id"]))
    return done


def _append(rec: dict) -> None:
    with RESULTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _lms(*args: str, timeout: int) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["lms", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, combined[-2000:]
    except subprocess.TimeoutExpired:
        return False, f"lms {' '.join(args)} timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"lms {' '.join(args)} error: {exc}"


def _unload_all() -> None:
    # `lms load` spawns a NEW instance each call rather than replacing, so memory
    # would accumulate across the run. Clear everything before each load to
    # guarantee exactly one instance and a genuine cold start.
    _lms("unload", "--all", timeout=60)


def _load(model: str) -> dict:
    """Try load configs in order (unloading all before each attempt so a
    timed-out partial load can't linger); return the first that succeeds, timed."""
    out = ""
    for ctx, gpu in LOAD_CONFIGS:
        _unload_all()
        args = ["load", model, "-c", str(ctx), "--parallel", "1", "-y"]
        if gpu is not None:
            args += ["--gpu", gpu]
        t0 = time.time()
        ok, out = _lms(*args, timeout=LOAD_TIMEOUT)
        elapsed = time.time() - t0
        if ok:
            return {"loaded": True, "load_seconds": round(elapsed, 2), "context": ctx, "gpu": gpu or "auto", "log": out[-400:]}
        # If it failed fast it's probably a real error; if it timed out, try a smaller config.
    return {"loaded": False, "load_seconds": None, "context": None, "gpu": None, "log": out[-400:]}


def _stream_call(model: str, system: str | None, user: str, max_tokens: int) -> dict:
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream_options": {"include_usage": True},
    }
    t0 = time.time()
    ttft = None  # time to first *content* (final-answer) token
    reasoning_ttft = None  # time to first reasoning token (true "time to first output" for r1-style models)
    chunks: list[str] = []
    reasoning_chunks: list[str] = []
    usage = {}
    finish_reason = None
    error = None
    try:
        with requests.post(LMS_API, json=payload, stream=True, timeout=GEN_TIMEOUT) as resp:
            if resp.status_code != 200:
                return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
                        "ttft_seconds": None, "total_seconds": round(time.time() - t0, 2),
                        "text": "", "usage": {}, "finish_reason": None}
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if obj.get("usage"):
                    usage = obj["usage"]
                for choice in obj.get("choices") or []:
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    # Reasoning models (deepseek-r1 etc.) stream their chain-of-thought
                    # in a separate `reasoning_content` field; capture it so a model that
                    # spent its whole token budget thinking doesn't record as empty.
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    if content:
                        if ttft is None:
                            ttft = time.time() - t0
                        chunks.append(content)
                    if reasoning:
                        if reasoning_ttft is None:
                            reasoning_ttft = time.time() - t0
                        reasoning_chunks.append(reasoning)
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
    except requests.exceptions.Timeout:
        error = f"generation timed out after {GEN_TIMEOUT}s"
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"

    total = time.time() - t0
    text = "".join(chunks)
    reasoning_text = "".join(reasoning_chunks)
    # "First output" = whichever arrived first (content or reasoning).
    first_output = min([t for t in (ttft, reasoning_ttft) if t is not None], default=None)
    ctoks = usage.get("completion_tokens")
    gen_time = (total - first_output) if (first_output is not None) else total
    tok_s = round(ctoks / gen_time, 2) if (ctoks and gen_time and gen_time > 0) else None
    return {
        "ok": bool(text) and error is None,
        "error": error,
        "ttft_seconds": round(ttft, 2) if ttft is not None else None,
        "reasoning_ttft_seconds": round(reasoning_ttft, 2) if reasoning_ttft is not None else None,
        "first_output_seconds": round(first_output, 2) if first_output is not None else None,
        "total_seconds": round(total, 2),
        "text": text,
        "reasoning_text": reasoning_text[:4000],
        "reasoning_chars": len(reasoning_text),
        "produced_final_answer": bool(text),
        "usage": usage,
        "tokens_per_second": tok_s,
        "finish_reason": finish_reason,
    }


def _auto_check(prompt: dict, text: str) -> dict:
    """Cheap programmatic validity checks; human quality grading happens later."""
    kind = prompt.get("check")
    if not kind:
        return {}
    if kind == "json":
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            if "\n" in candidate:
                candidate = candidate.split("\n", 1)[1]
        start, end = candidate.find("{"), candidate.rfind("}")
        parsed_ok = False
        if 0 <= start < end:
            try:
                json.loads(candidate[start:end + 1])
                parsed_ok = True
            except json.JSONDecodeError:
                parsed_ok = False
        return {"json_parseable": parsed_ok, "clean_json": text.strip().startswith("{")}
    if kind == "toolcall":
        try:
            obj = json.loads(text[text.find("{"):text.rfind("}") + 1])
            calls = obj.get("tool_calls") or []
            return {"emitted_tool_call": bool(calls) and isinstance(calls, list) and bool(calls[0].get("name"))}
        except Exception:  # noqa: BLE001
            return {"emitted_tool_call": False}
    if kind == "needle":
        return {"needle_found": NEEDLE_ANSWER.lower() in text.lower()}
    if kind == "attribution":
        import re
        return {"has_citation_markers": bool(re.search(r"\[\d+\]", text))}
    return {}


def run() -> None:
    done = _done_keys()
    plan: list[tuple[str, bool]] = [(m, False) for m in CANDIDATE_MODELS] + [(m, True) for m in BASELINE_MODELS]

    for model, is_baseline in plan:
        prompts = [p for p in PROMPTS if (not is_baseline or p["id"] in BASELINE_SUBSET)]
        if all((model, p["id"]) in done for p in prompts):
            print(f"[skip] {model} already complete", flush=True)
            continue

        print(f"\n===== {model} ({'baseline' if is_baseline else 'candidate'}) =====", flush=True)
        print(f"[{_utc()}] loading (cold, unload-all first)…", flush=True)
        load_info = _load(model)
        print(f"[{_utc()}] load -> {load_info['loaded']} ({load_info.get('load_seconds')}s, "
              f"ctx={load_info.get('context')}, gpu={load_info.get('gpu')})", flush=True)

        for prompt in prompts:
            if (model, prompt["id"]) in done:
                continue
            rec = {
                "model": model,
                "is_baseline": is_baseline,
                "prompt_id": prompt["id"],
                "kind": prompt["kind"],
                "started_at": _utc(),
                "load_info": load_info,
            }
            if not load_info["loaded"]:
                rec.update({"skipped": "model_failed_to_load", "run": None, "ended_at": _utc()})
                _append(rec)
                continue

            print(f"[{_utc()}] {model} :: {prompt['id']} ({prompt['kind']})…", flush=True)
            t0 = time.time()
            result = _stream_call(model, prompt["system"], prompt["user"], prompt["max_tokens"])
            result["auto_check"] = _auto_check(prompt, result.get("text") or "")
            rec.update({"run": result, "wall_seconds": round(time.time() - t0, 2), "ended_at": _utc()})
            _append(rec)
            print(f"    -> ok={result['ok']} ttft={result['ttft_seconds']} total={result['total_seconds']}s "
                  f"tok/s={result.get('tokens_per_second')} check={result['auto_check']}", flush=True)

        print(f"[{_utc()}] unloading all after {model}…", flush=True)
        _unload_all()

    # Restore the assistant's usual small models so LM Studio is left as found.
    print(f"[{_utc()}] restoring baseline residency (qwen3-4b + orpheus)…", flush=True)
    _lms("load", "qwen/qwen3-4b-2507", "-y", timeout=LOAD_TIMEOUT)
    _lms("load", "orpeus_text_to_speech", "-y", timeout=LOAD_TIMEOUT)
    print(f"\n[{_utc()}] BENCHMARK COMPLETE", flush=True)


if __name__ == "__main__":
    run()
