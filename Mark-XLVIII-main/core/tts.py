"""
Text-to-Speech engines for MARK XL.

EdgeTTS     – free Microsoft TTS (internet required, no API key)
Kokoro      – fully offline neural TTS (~330 MB model)
ElevenLabs  – cloud API (API key required, best quality)
"""
from __future__ import annotations

import asyncio
import os
import queue as _queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import sounddevice as sd



# USE_TF=0 stops transformers from importing TensorFlow (saves 4-8 s startup).
# Do NOT set USE_TORCH or USE_JAX explicitly — forcing those values breaks
# transformers' lazy-loader on certain versions, causing AutoModel and other
# classes to vanish from the public namespace.  Auto-detection is reliable.
os.environ.setdefault("USE_TF",                 "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_ORPHEUS_START_LOCK = threading.Lock()
_ORPHEUS_PROCESS: subprocess.Popen | None = None
_ORPHEUS_LAST_START = 0.0
_ORPHEUS_WARM_LOCK = threading.Lock()
_ORPHEUS_WARM_EVENT = threading.Event()
_ORPHEUS_WARM_THREAD: threading.Thread | None = None
_ORPHEUS_LAST_WARM = 0.0
_ORPHEUS_WARM_STATE: dict[str, Any] = {
    "warming": False,
    "ready": False,
    "error": "",
    "model": "orpeus_text_to_speech",
}


def _orpheus_health_url(base_url: str) -> str:
    root = (base_url or "http://127.0.0.1:5006/v1").rstrip("/")
    if root.lower().endswith("/v1"):
        root = root[:-3]
    return f"{root}/health"


def _endpoint_reachable(base_url: str, timeout: float = 1.0) -> bool:
    try:
        import requests

        response = requests.get(_orpheus_health_url(base_url), timeout=max(0.2, timeout))
        return response.status_code < 500
    except Exception:
        return False


def _tts_model_loaded(config: dict[str, Any]) -> bool:
    model = str(config.get("tts_lmstudio_model") or "orpeus_text_to_speech").lower()
    try:
        from actions.model_lifecycle import status

        payload = status(config)
        loaded = payload.get("loaded") or []
        aliases = {model, model.replace("orpheus", "orpeus"), model.replace("orpeus", "orpheus")}
        return any(
            any(alias in str(item.get("model_key") or item.get("instance_id") or "").lower() for alias in aliases)
            for item in loaded
        )
    except Exception:
        return False


def warm_local_tts_service(config: dict[str, Any], *, wait_seconds: float = 0.0) -> dict[str, Any]:
    """Start the bridge and load one baseline Orpheus instance in the background."""
    engine = str(config.get("tts_engine") or "").strip().lower()
    if engine not in {"orpheus", "lmstudio_tts", "openai_compatible", "openai_tts"}:
        return {"ok": True, "engine": engine, "ready": True, "warming": False}

    ensure_local_tts_service(config)
    if _endpoint_reachable(str(config.get("tts_url") or config.get("tts_base_url") or "")) and _tts_model_loaded(config):
        with _ORPHEUS_WARM_LOCK:
            _ORPHEUS_WARM_STATE.update({"warming": False, "ready": True, "error": ""})
            _ORPHEUS_WARM_EVENT.set()
            return dict(_ORPHEUS_WARM_STATE)

    global _ORPHEUS_WARM_THREAD, _ORPHEUS_LAST_WARM
    retry_seconds = max(10.0, float(config.get("tts_warm_retry_seconds", 60.0)))
    with _ORPHEUS_WARM_LOCK:
        thread_running = _ORPHEUS_WARM_THREAD is not None and _ORPHEUS_WARM_THREAD.is_alive()
        retry_ready = time.monotonic() - _ORPHEUS_LAST_WARM >= retry_seconds
        if not thread_running and retry_ready:
            model = str(config.get("tts_lmstudio_model") or "orpeus_text_to_speech").strip()
            _ORPHEUS_WARM_EVENT.clear()
            _ORPHEUS_WARM_STATE.update({"warming": True, "ready": False, "error": "", "model": model})
            _ORPHEUS_LAST_WARM = time.monotonic()

            def _warm() -> None:
                error = ""
                try:
                    from actions.model_lifecycle import ensure_model_loaded

                    loaded = ensure_model_loaded(
                        model,
                        route="speech",
                        cfg=config,
                        timeout=int(config.get("tts_model_load_timeout_seconds", 180)),
                    )
                    if not loaded.get("ok"):
                        raise RuntimeError(str(loaded.get("error") or "Orpheus model load failed."))
                    bridge_timeout = max(1.0, float(config.get("tts_bridge_startup_seconds", 30.0)))
                    deadline = time.monotonic() + bridge_timeout
                    base_url = str(config.get("tts_url") or config.get("tts_base_url") or "")
                    while not _endpoint_reachable(base_url) and time.monotonic() < deadline:
                        time.sleep(0.25)
                    if not _endpoint_reachable(base_url):
                        raise RuntimeError("Orpheus bridge did not become ready before the startup deadline.")
                except Exception as exc:
                    error = str(exc)
                finally:
                    ready = not error and _tts_model_loaded(config)
                    with _ORPHEUS_WARM_LOCK:
                        _ORPHEUS_WARM_STATE.update(
                            {"warming": False, "ready": ready, "error": error if not ready else ""}
                        )
                        _ORPHEUS_WARM_EVENT.set()

            _ORPHEUS_WARM_THREAD = threading.Thread(target=_warm, name="jarvis-orpheus-warm", daemon=True)
            _ORPHEUS_WARM_THREAD.start()

    if wait_seconds > 0:
        _ORPHEUS_WARM_EVENT.wait(timeout=max(0.0, float(wait_seconds)))
    with _ORPHEUS_WARM_LOCK:
        return dict(_ORPHEUS_WARM_STATE)


def ensure_local_tts_service(config: dict[str, Any]) -> dict[str, Any]:
    """Start the local Orpheus bridge once; callers can use SAPI while it warms."""
    engine = str(config.get("tts_engine") or "").strip().lower()
    if engine not in {"orpheus", "lmstudio_tts", "openai_compatible", "openai_tts"}:
        return {"ok": True, "engine": engine, "reachable": True, "started": False}
    base_url = str(config.get("tts_url") or config.get("tts_base_url") or "http://127.0.0.1:5006/v1")
    reachable = _endpoint_reachable(base_url)
    if reachable or not bool(config.get("tts_auto_start_bridge", True)):
        return {"ok": reachable, "engine": engine, "reachable": reachable, "started": False}

    global _ORPHEUS_PROCESS, _ORPHEUS_LAST_START
    with _ORPHEUS_START_LOCK:
        if _endpoint_reachable(base_url):
            return {"ok": True, "engine": engine, "reachable": True, "started": False}
        if _ORPHEUS_PROCESS is not None and _ORPHEUS_PROCESS.poll() is None:
            return {"ok": False, "engine": engine, "reachable": False, "started": False, "starting": True}
        if time.monotonic() - _ORPHEUS_LAST_START < 30.0:
            return {"ok": False, "engine": engine, "reachable": False, "started": False, "starting": True}

        repo_root = Path(__file__).resolve().parent.parent
        script = repo_root / "scripts" / "start-orpheus-tts-bridge.ps1"
        if not script.exists() or sys.platform != "win32":
            return {
                "ok": False,
                "engine": engine,
                "reachable": False,
                "started": False,
                "error": f"Orpheus bridge launcher was not found: {script}",
            }
        logs = repo_root / "runtime_logs"
        logs.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        stdout_path = logs / f"orpheus-auto-{stamp}.out.log"
        stderr_path = logs / f"orpheus-auto-{stamp}.err.log"
        stdout_handle = stdout_path.open("ab")
        stderr_handle = stderr_path.open("ab")
        try:
            kwargs: dict[str, Any] = {
                "cwd": str(repo_root),
                "stdout": stdout_handle,
                "stderr": stderr_handle,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            _ORPHEUS_PROCESS = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                **kwargs,
            )
            _ORPHEUS_LAST_START = time.monotonic()
        finally:
            stdout_handle.close()
            stderr_handle.close()
        return {
            "ok": False,
            "engine": engine,
            "reachable": False,
            "started": True,
            "starting": True,
            "pid": _ORPHEUS_PROCESS.pid,
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
        }


def tts_runtime_status(config: dict[str, Any]) -> dict[str, Any]:
    engine = str(config.get("tts_engine") or "").strip().lower()
    if engine not in {"orpheus", "lmstudio_tts", "openai_compatible", "openai_tts"}:
        return {"engine": engine, "primary_ready": True, "fallback": ""}
    base_url = str(config.get("tts_url") or config.get("tts_base_url") or "http://127.0.0.1:5006/v1")
    bridge_ready = _endpoint_reachable(base_url)
    model_ready = _tts_model_loaded(config)
    with _ORPHEUS_WARM_LOCK:
        warm_state = dict(_ORPHEUS_WARM_STATE)
    return {
        "engine": engine,
        "bridge_ready": bridge_ready,
        "model_ready": model_ready,
        "primary_ready": bridge_ready and model_ready,
        "fallback": "windows",
        "warming": bool(warm_state.get("warming")),
        "warm_error": str(warm_state.get("error") or ""),
    }


# ---------------------------------------------------------------------------
# Audio playback helpers
# ---------------------------------------------------------------------------

def _to_numpy(samples) -> np.ndarray:
    """Convert samples to float32 numpy array.

    Handles both numpy arrays and PyTorch tensors (Kokoro >= 0.9).

    PyTorch built against numpy 1.x raises RuntimeError('Numpy is not available')
    when numpy 2.x is installed.  The .tolist() fallback always works regardless
    of PyTorch / numpy version pairing.
    """
    if hasattr(samples, "detach"):                  # PyTorch tensor
        t = samples.detach().cpu().float()
        try:
            return t.numpy()                        # fast path (compatible versions)
        except RuntimeError:
            # PyTorch/numpy version mismatch — convert via Python list (always safe)
            return np.asarray(t.tolist(), dtype=np.float32)
    return np.asarray(samples, dtype=np.float32)


def _compress_silence(
    arr: np.ndarray,
    sample_rate: int    = 24_000,
    max_silence_ms: int = 500,    # cap punctuation pauses — keeps natural rhythm
    threshold: float    = 0.003,  # RMS below this = silence; lower = less clipping
) -> np.ndarray:
    """
    Shorten Kokoro's very long punctuation pauses (1-2 s → ≤500 ms).
    Conservative settings preserve natural prosody; only trims extreme pauses.
    """
    max_samp  = int(max_silence_ms * sample_rate / 1000)
    frame_len = 240                   # ~10 ms at 24 kHz
    out: list[np.ndarray] = []
    silent_acc = 0

    for i in range(0, len(arr), frame_len):
        chunk = arr[i : i + frame_len]
        if np.sqrt(np.mean(chunk ** 2) + 1e-12) < threshold:
            silent_acc += len(chunk)
            if silent_acc <= max_samp:
                out.append(chunk)
        else:
            silent_acc = 0
            out.append(chunk)

    return np.concatenate(out) if out else arr


def _play_np(samples, sample_rate: int) -> None:
    """Play float32 mono (or stereo) audio via sounddevice.
    Accepts numpy arrays or PyTorch tensors.
    """
    sd.play(_to_numpy(samples), sample_rate)
    sd.wait()


def _play_audio_bytes(audio_bytes: bytes) -> None:
    """Decode MP3/WAV/OGG bytes and play via sounddevice (uses miniaudio)."""
    import miniaudio
    decoded = miniaudio.decode(
        audio_bytes,
        output_format=miniaudio.SampleFormat.FLOAT32,
        nchannels=1,
    )
    samples = np.array(decoded.samples, dtype=np.float32)
    sd.play(samples, decoded.sample_rate)
    sd.wait()


def _split_text_for_tts(text: str, max_chars: int = 260) -> list[str]:
    """Split text into ordered speech chunks without duplicating the full reply."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    max_chars = max(80, int(max_chars or 260))
    if len(text) <= max_chars:
        return [text]

    parts = re.split(r"(?<=[.!?;:])\s+", text)
    chunks: list[str] = []
    current = ""

    def _push(value: str) -> None:
        value = value.strip()
        if value:
            chunks.append(value)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) > max_chars:
            _push(current)
            current = ""
            words = part.split()
            line = ""
            for word in words:
                candidate = f"{line} {word}".strip()
                if len(candidate) <= max_chars:
                    line = candidate
                else:
                    _push(line)
                    line = word
            current = line
            continue
        candidate = f"{current} {part}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            _push(current)
            current = part
    _push(current)
    return chunks


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

class WindowsSapiTTSEngine:
    """Lightweight Windows local TTS using SAPI/System.Speech."""

    def __init__(self, voice: str | None = None, rate: int = 0, volume: int = 100):
        self.voice = voice or ""
        self.rate = int(rate)
        self.volume = int(volume)
        self._voice = None

    def _sapi_voice(self):
        if self._voice is None:
            import comtypes.client

            voice = comtypes.client.CreateObject("SAPI.SpVoice")
            voice.Rate = self.rate
            voice.Volume = max(0, min(100, self.volume))
            self._voice = voice
        return self._voice

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        try:
            self._sapi_voice().Speak(text)
            return
        except Exception as first_error:
            print(f"[TTS] Windows SAPI COM failed, trying System.Speech: {first_error}")
        self._speak_powershell(text)

    def _speak_powershell(self, text: str) -> None:
        command = (
            "$t=$args[0]; "
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate={self.rate}; "
            f"$s.Volume={max(0, min(100, self.volume))}; "
            "$s.Speak($t)"
        )
        kwargs = {"capture_output": True}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command, text],
            **kwargs,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"System.Speech fallback failed: {stderr[:200]}")


class ResilientTTSEngine:
    """Use neural speech only when its bridge and model are ready; otherwise speak immediately with SAPI."""

    def __init__(self, primary: Any, fallback: Any, config: dict[str, Any]):
        self.primary = primary
        self.fallback = fallback
        self.config = dict(config)
        self.last_backend = ""
        self.last_error = ""
        self._primary_retry_after = 0.0

    def speak(self, text: str) -> None:
        status = tts_runtime_status(self.config)
        now = time.monotonic()
        if not status.get("primary_ready") and now >= self._primary_retry_after:
            warm = warm_local_tts_service(
                self.config,
                wait_seconds=float(self.config.get("tts_orpheus_first_turn_wait_seconds", 12.0)),
            )
            status = tts_runtime_status(self.config)
            if warm.get("error"):
                self.last_error = str(warm["error"])
        if status.get("primary_ready"):
            try:
                self.last_backend = "orpheus"
                self.primary.speak(text)
                self.last_error = ""
                self._primary_retry_after = 0.0
                return
            except Exception as exc:
                self.last_error = str(exc)
                self._primary_retry_after = time.monotonic() + max(
                    10.0, float(self.config.get("tts_primary_failure_backoff_seconds", 60.0))
                )
                print(f"[TTS] Orpheus failed; using Windows fallback: {exc}")
        else:
            warm_local_tts_service(self.config, wait_seconds=0.0)
        self.last_backend = "windows"
        self.fallback.speak(text)

    def cancel(self) -> None:
        for engine in (self.primary, self.fallback):
            cancel = getattr(engine, "cancel", None)
            if callable(cancel):
                cancel()

class EdgeTTSEngine:
    """Microsoft EdgeTTS – free, requires internet."""

    def __init__(self, voice: str = "en-US-GuyNeural"):
        self.voice = voice

    def speak(self, text: str) -> None:
        loop = asyncio.new_event_loop()
        try:
            audio_bytes = loop.run_until_complete(self._synth(text))
        finally:
            loop.close()
        if audio_bytes:
            _play_audio_bytes(audio_bytes)

    async def _synth(self, text: str) -> bytes:
        import edge_tts
        comm = edge_tts.Communicate(text, self.voice)
        buf  = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)


# ---------------------------------------------------------------------------
# Kokoro import helper — auto-upgrades on version-mismatch errors
# ---------------------------------------------------------------------------

# Errors that indicate the installed kokoro uses old transformers classes
# (AlbertModel, AutoModel) that are no longer exported at the top level.
_KOKORO_COMPAT_ERRORS = ("AlbertModel", "AutoModel", "cannot import name")


def _import_kokoro_pipeline():
    """Import KPipeline, auto-upgrading kokoro if a version mismatch is found.

    Old kokoro (<0.9) imports AlbertModel / AutoModel from transformers.
    Newer transformers versions no longer export these at the top level,
    causing an ImportError.  kokoro>=0.9 removed these dependencies.

    When the error is detected we:
      1. Upgrade kokoro to >=0.9 via pip (silent, background)
      2. Flush stale kokoro entries from sys.modules
      3. Re-import — this time it should succeed
    """
    import sys

    def _try_import():
        from kokoro import KPipeline  # noqa: PLC0415
        return KPipeline

    try:
        return _try_import()
    except Exception as first_err:
        err_msg = str(first_err)
        if not any(marker in err_msg for marker in _KOKORO_COMPAT_ERRORS):
            # Unrelated error (kokoro not installed, etc.)
            raise RuntimeError(
                f"Kokoro import failed: {first_err}\n"
                "Run: pip install kokoro>=0.9 soundfile"
            ) from first_err

        # ── Version mismatch: upgrade kokoro silently and retry ──────────
        print("[TTS] Kokoro/transformers version mismatch detected — upgrading kokoro…")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "kokoro>=0.9",
             "--upgrade", "--quiet", "--disable-pip-version-check"],
            capture_output=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(
                f"Kokoro auto-upgrade failed: {stderr[:200]}\n"
                "Run manually: pip install kokoro>=0.9 soundfile"
            ) from first_err

        # Flush any stale kokoro submodules from the import cache
        stale = [k for k in sys.modules if k == "kokoro" or k.startswith("kokoro.")]
        for key in stale:
            del sys.modules[key]

        print("[TTS] Kokoro upgraded — retrying import…")
        try:
            return _try_import()
        except Exception as retry_err:
            raise RuntimeError(
                f"Kokoro still broken after upgrade: {retry_err}\n"
                "Run manually: pip install --upgrade kokoro transformers"
            ) from retry_err


# Kokoro voice prefix → KPipeline lang_code mapping
_KOKORO_LANG_CODES = {
    "a": "a",   # American English  (af_*, am_*)
    "b": "b",   # British English   (bf_*, bm_*)
    "j": "j",   # Japanese          (jf_*, jm_*)
    "z": "z",   # Mandarin Chinese  (zf_*, zm_*)
    "s": "s",   # Spanish           (sf_*, sm_*)
    "f": "f",   # French            (ff_*, fm_*)
    "h": "h",   # Hindi             (hf_*, hm_*)
    "i": "i",   # Italian           (if_*, im_*)
    "p": "p",   # Brazilian Portuguese
    "r": "r",   # Russian           (rf_*, rm_*)
    "e": "e",   # German            (ef_*, em_*)
}


class KokoroTTSEngine:
    """Fully offline Kokoro neural TTS.

    Model (~330 MB) is downloaded from HuggingFace on first use,
    then cached locally — subsequent starts load from disk.

    Warmup strategy: _init() runs synchronously in the background
    _do_tts() thread (not the UI thread).  After the pipeline loads,
    a dummy inference compiles the PyTorch JIT graph immediately so
    the first real speak() call has zero compilation overhead.
    """

    def __init__(self, voice: str = "af_heart", speed: float = 1.0):
        self.voice     = voice
        self.speed     = speed
        self._pipeline = None
        self._lock     = threading.Lock()
        self._init()   # blocking, but called from background thread

    @property
    def _lang_code(self) -> str:
        prefix = self.voice[0].lower() if self.voice else "a"
        return _KOKORO_LANG_CODES.get(prefix, "a")

    def _init(self) -> None:
        if self._pipeline is not None:
            return

        lang = self._lang_code

        # Prefer GPU — Kokoro on CUDA is ~10x faster than CPU.
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cpu":
                import os as _os
                n_threads = max(1, min(4, (_os.cpu_count() or 4) // 2))
                try:
                    torch.set_num_threads(n_threads)
                    torch.set_num_interop_threads(2)
                except RuntimeError:
                    pass
                print(
                    f"[TTS] Kokoro on CPU — for faster speech install CUDA PyTorch:\n"
                    "      pip install torch --index-url https://download.pytorch.org/whl/cu118"
                )
        except Exception:
            device = "cpu"

        print(f"[TTS] Kokoro — loading (lang='{lang}', device='{device}')…")

        KPipeline = _import_kokoro_pipeline()

        def _create_pipeline():
            try:
                return KPipeline(lang_code=lang, device=device)
            except TypeError:
                return KPipeline(lang_code=lang)   # older build — no device param

        try:
            self._pipeline = _create_pipeline()
        except Exception as _first_err:
            # Offline flag set but model not cached yet → clear flags and download once.
            # Keywords cover multiple huggingface_hub error message variants across versions.
            _e = str(_first_err).lower()
            _offline_keywords = (
                "offline", "not found", "cache", "localentry",
                "does not exist", "outgoing", "local_files_only",
            )
            if any(k in _e for k in _offline_keywords):
                print("[TTS] Kokoro model not in local cache — downloading (one-time, internet required)…")
                os.environ.pop("HF_HUB_OFFLINE",      None)
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
                os.environ.pop("HF_DATASETS_OFFLINE",  None)
                try:
                    self._pipeline = _create_pipeline()
                except Exception as _dl_err:
                    raise RuntimeError(
                        f"Kokoro model download failed.\n"
                        f"Internet access is required the first time to download the voice model (~330 MB).\n"
                        f"After the first download it runs fully offline.\n"
                        f"Tip: Switch to EdgeTTS (free, no download) in the Configure panel if offline.\n"
                        f"Details: {_dl_err}"
                    ) from _dl_err
            else:
                raise

        print("[TTS] Kokoro compiling (first-time only)…")
        # Warmup: compiles PyTorch JIT graph so first real speak() call is instant.
        try:
            for _ in self._pipeline("hello", voice=self.voice, speed=self.speed):
                pass
            print("[TTS] Kokoro ready.")
        except Exception as e:
            print(f"[TTS] Kokoro warmup warning: {e}")

    def speak(self, text: str) -> None:
        with self._lock:
            if self._pipeline is None:
                self._init()

        # ── Concurrent synthesise + playback ────────────────────────────────
        # Kokoro generates audio chunks lazily.  Without threading, we:
        #   synthesise chunk N → play N → synthesise N+1 → play N+1 …
        # With a producer/consumer pair, chunk N+1 synthesises WHILE chunk N
        # plays, cutting perceived latency by the playback duration of all but
        # the last chunk (typically 1-3 s on multi-sentence responses).
        audio_q: "_queue.Queue[np.ndarray | None]" = _queue.Queue(maxsize=4)
        synth_error: list[Exception] = []

        def _synth():
            try:
                for _, _, audio in self._pipeline(text, voice=self.voice, speed=self.speed):
                    if audio is not None:
                        arr = _to_numpy(audio)
                        arr = _compress_silence(arr)
                        if arr.size > 0:
                            audio_q.put(arr)          # blocks if player is slow (backpressure)
            except Exception as exc:
                synth_error.append(exc)
            finally:
                audio_q.put(None)                     # sentinel → player exits

        synth_thread = threading.Thread(target=_synth, daemon=True)
        synth_thread.start()

        # Player runs in this thread so sd.wait() doesn't block the synth thread.
        while True:
            arr = audio_q.get()
            if arr is None:
                break
            _play_np(arr, 24000)

        synth_thread.join()

        if synth_error:
            raise synth_error[0]


class ElevenLabsTTSEngine:
    """ElevenLabs cloud TTS – API key required."""

    def __init__(self, api_key: str, voice_id: str = "pNInz6obpgDQGcFmaJgB"):
        self.api_key  = api_key
        self.voice_id = voice_id

    def speak(self, text: str) -> None:
        import requests
        headers = {
            "xi-api-key":   self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text":     text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
            json=payload, headers=headers, timeout=30,
        )
        resp.raise_for_status()
        _play_audio_bytes(resp.content)


class OpenAICompatibleTTSEngine:
    """OpenAI-compatible local/cloud TTS endpoint.

    Useful for Orpheus FastAPI bridges that expose /v1/audio/speech while using
    LM Studio or llama.cpp underneath for GGUF token generation.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5005/v1",
        model: str = "orpheus",
        voice: str = "tara",
        response_format: str = "wav",
        speed: float = 1.0,
        api_key: str | None = None,
        chunk_chars: int = 260,
        chunk_workers: int = 1,
        chunking_enabled: bool = True,
        request_timeout_seconds: float = 240.0,
        lifecycle_config: dict | None = None,
    ):
        self.base_url = (base_url or "http://localhost:5005/v1").rstrip("/")
        self.model = model or "orpheus"
        self.voice = voice or "tara"
        self.response_format = response_format or "wav"
        self.speed = float(speed)
        self.api_key = api_key or ""
        self.chunk_chars = max(80, int(chunk_chars or 260))
        # LM Studio's parallel slots are shared by every local model. Speech uses
        # one generation at a time and overlaps only decoding/playback with the
        # next chunk; parallel HTTP synthesis caused duplicate and stale voices.
        self.chunk_workers = 1
        self.requested_chunk_workers = max(1, min(4, int(chunk_workers or 1)))
        self.chunking_enabled = bool(chunking_enabled)
        self.request_timeout_seconds = max(30.0, float(request_timeout_seconds or 240.0))
        self.lifecycle_config = dict(lifecycle_config or {})
        self._synth_lock = threading.Lock()
        self._turn_lock = threading.Lock()
        self._cancel_lock = threading.Lock()
        self._cancel_epoch = 0

    def _begin_turn(self) -> int:
        with self._cancel_lock:
            self._cancel_epoch += 1
            return self._cancel_epoch

    def _turn_is_current(self, turn_id: int) -> bool:
        with self._cancel_lock:
            return turn_id == self._cancel_epoch

    def cancel(self) -> None:
        """Cancel playback and prevent stale chunks from being submitted."""
        with self._cancel_lock:
            self._cancel_epoch += 1
        sd.stop()

    def _synth_chunk(self, text: str) -> bytes:
        import requests

        text = (text or "").strip()
        if not text:
            return b""

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = requests.post(
            f"{self.base_url}/audio/speech",
            json={
                "model": self.model,
                "input": text,
                "voice": self.voice,
                "response_format": self.response_format,
                "speed": self.speed,
            },
            headers=headers,
            timeout=self.request_timeout_seconds,
        )
        resp.raise_for_status()
        content_type = (resp.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            raise RuntimeError(f"TTS endpoint returned JSON instead of audio: {resp.text[:300]}")
        if not resp.content:
            raise RuntimeError("TTS endpoint returned no audio.")
        return resp.content

    def _synth_for_turn(self, text: str, turn_id: int) -> bytes:
        # A cancelled request may still be draining inside requests/LM Studio.
        # Holding this lock until it returns prevents the replacement turn from
        # occupying another model slot in the meantime.
        with self._synth_lock:
            if not self._turn_is_current(turn_id):
                return b""
            if not self.lifecycle_config:
                audio = self._synth_chunk(text)
                return audio if self._turn_is_current(turn_id) else b""
            lease_id = ""
            lifecycle = None
            lease_outcome = "completed"
            try:
                from actions import model_lifecycle as lifecycle

                lease = lifecycle.acquire_generation_lease(
                    "orpeus_text_to_speech",
                    route="speech",
                    cfg=self.lifecycle_config,
                    wait_seconds=float(self.lifecycle_config.get("tts_generation_wait_seconds", 900.0)),
                )
                if not lease.get("ok"):
                    raise RuntimeError(lease.get("error") or "TTS generation lease unavailable.")
                lease_id = str(lease.get("lease_id") or "")
                lifecycle.update_generation_lease(
                    lease_id,
                    state="GENERATING",
                    instance_id="orpeus_text_to_speech",
                    cfg=self.lifecycle_config,
                    details={"component": "tts", "turn_id": turn_id},
                )
                audio = self._synth_chunk(text)
                return audio if self._turn_is_current(turn_id) else b""
            except Exception:
                lease_outcome = "failed"
                raise
            finally:
                if lifecycle is not None and lease_id:
                    if lease_outcome == "completed" and not self._turn_is_current(turn_id):
                        lease_outcome = "cancelled"
                    lifecycle.release_generation_lease(
                        lease_id,
                        cfg=self.lifecycle_config,
                        outcome=lease_outcome,
                    )

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return

        with self._turn_lock:
            if self.lifecycle_config and self.lifecycle_config.get(
                "tts_release_idle_task_models", True
            ):
                try:
                    from actions import model_lifecycle

                    # Speech is latency-sensitive. Release a specialist that is
                    # merely warm, while lifecycle leases protect active work.
                    #
                    # `keep` is load-bearing: the speech model is no longer a
                    # baseline (it loads on demand and idles out through the
                    # task-model TTL, per the 2026-07-24 RAM decision), so
                    # without naming it here this cleanup could unload the very
                    # voice it is about to speak with and force an immediate
                    # reload.
                    voice_models = {
                        str(self.lifecycle_config.get("tts_lmstudio_model") or "").strip(),
                        str(getattr(self, "model", "") or "").strip(),
                    }
                    model_lifecycle.unload_non_baseline(
                        self.lifecycle_config,
                        timeout=10,
                        force=False,
                        keep={item for item in voice_models if item},
                    )
                except Exception as exc:
                    print(f"[TTS] Idle task-model cleanup skipped: {exc}")
            turn_id = self._begin_turn()
            chunks = _split_text_for_tts(text, self.chunk_chars) if self.chunking_enabled else [text]
            audio_q: "_queue.Queue[bytes | object]" = _queue.Queue(maxsize=1)
            sentinel = object()

            def _produce() -> None:
                try:
                    for chunk in chunks:
                        if not self._turn_is_current(turn_id):
                            break
                        audio = self._synth_for_turn(chunk, turn_id)
                        if not audio or not self._turn_is_current(turn_id):
                            break
                        while self._turn_is_current(turn_id):
                            try:
                                audio_q.put(audio, timeout=0.1)
                                break
                            except _queue.Full:
                                continue
                finally:
                    try:
                        audio_q.put_nowait(sentinel)
                    except _queue.Full:
                        pass

            producer = threading.Thread(target=_produce, name="jarvis-tts-synth", daemon=True)
            producer.start()
            try:
                while self._turn_is_current(turn_id):
                    try:
                        item = audio_q.get(timeout=0.1)
                    except _queue.Empty:
                        if not producer.is_alive():
                            break
                        continue
                    if item is sentinel:
                        break
                    if self._turn_is_current(turn_id):
                        _play_audio_bytes(item)
            finally:
                # On cancellation the in-flight HTTP request drains under
                # _synth_lock; it is intentionally not orphaned into a new slot.
                producer.join(timeout=0.25)


# ---------------------------------------------------------------------------
# Thread-safe player wrapper
# ---------------------------------------------------------------------------

class TTSPlayer:
    """
    Wraps any *Engine. Exposes a blocking speak() method
    meant to be called from a dedicated background thread.
    """

    def __init__(
        self,
        engine,
        duplicate_window_seconds: float = 20.0,
        max_pending_utterances: int = 1,
    ):
        self._engine  = engine
        self._playing = False
        self._play_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._active_text = ""
        self._pending_texts: dict[int, str] = {}
        self._active_ticket = 0
        self._next_ticket = 0
        self._cancelled_through = 0
        self._max_pending_utterances = max(0, int(max_pending_utterances))
        self._last_text = ""
        self._last_done_at = 0.0
        self._duplicate_window_seconds = max(0.0, float(duplicate_window_seconds))
        self.last_error = ""

    @property
    def is_playing(self) -> bool:
        with self._state_lock:
            return self._playing

    def _claim_utterance(self, text: str) -> int | None:
        now = time.monotonic()
        with self._state_lock:
            duplicate_active = text == self._active_text or text in self._pending_texts.values()
            duplicate_recent = (
                text == self._last_text
                and self._duplicate_window_seconds > 0
                and now - self._last_done_at <= self._duplicate_window_seconds
            )
            if duplicate_active or duplicate_recent:
                print("[TTS] Suppressed duplicate utterance.")
                return None
            if self._playing and len(self._pending_texts) >= self._max_pending_utterances:
                print("[TTS] Suppressed utterance because the bounded speech queue is full.")
                return None
            if not self._playing and self._pending_texts:
                print("[TTS] Suppressed utterance because speech startup is already queued.")
                return None
            self._next_ticket += 1
            ticket = self._next_ticket
            self._pending_texts[ticket] = text
            return ticket

    def speak(
        self,
        text:     str,
        on_start: Optional[Callable] = None,
        on_done:  Optional[Callable] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Synthesise and play text. BLOCKING – call from a dedicated thread."""
        text = (text or "").strip()
        ticket = self._claim_utterance(text) if text else None
        if ticket is None:
            return
        with self._play_lock:
            with self._state_lock:
                if ticket <= self._cancelled_through or self._pending_texts.get(ticket) != text:
                    self._pending_texts.pop(ticket, None)
                    return
                self._pending_texts.pop(ticket, None)
                self._active_ticket = ticket
                self._active_text = text
                self._playing = True
            try:
                if on_start:
                    on_start()
                self._engine.speak(text)
            except Exception as e:
                self.last_error = str(e)
                print(f"[TTS] Error: {e}")
                if on_error:
                    on_error(str(e))
            finally:
                with self._state_lock:
                    if self._active_ticket == ticket:
                        self._playing = False
                        self._active_ticket = 0
                        self._active_text = ""
                        self._last_text = text
                        self._last_done_at = time.monotonic()
                # Keep this callback inside _play_lock so an older turn cannot
                # reopen the microphone after a replacement turn has started.
                if on_done:
                    on_done()

    def stop(self) -> None:
        cancel = getattr(self._engine, "cancel", None)
        if callable(cancel):
            cancel()
        sd.stop()
        with self._state_lock:
            self._cancelled_through = self._next_ticket
            self._playing = False
            self._active_ticket = 0
            self._active_text = ""
            self._pending_texts.clear()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_tts_player(config: dict) -> TTSPlayer:
    engine_name = config.get("tts_engine", "edgetts").lower()
    if engine_name in ("windows", "sapi", "system", "system_speech"):
        engine = WindowsSapiTTSEngine(
            voice=config.get("tts_voice", ""),
            rate=int(config.get("tts_rate", 0)),
            volume=int(config.get("tts_volume", 100)),
        )
    elif engine_name == "kokoro":
        voice  = config.get("tts_voice", "af_heart")
        speed  = float(config.get("tts_speed", 1.0))
        engine = KokoroTTSEngine(voice=voice, speed=speed)
    elif engine_name == "elevenlabs":
        api_key  = config.get("elevenlabs_api_key", "")
        voice_id = config.get("tts_voice", "pNInz6obpgDQGcFmaJgB")
        engine   = ElevenLabsTTSEngine(api_key=api_key, voice_id=voice_id)
    elif engine_name in ("openai_compatible", "openai_tts", "lmstudio_tts", "orpheus"):
        primary = OpenAICompatibleTTSEngine(
            base_url=config.get("tts_url") or config.get("tts_base_url") or config.get("orpheus_tts_url", ""),
            model=config.get("tts_model", "orpheus"),
            voice=config.get("tts_voice", "tara"),
            response_format=config.get("tts_response_format", "wav"),
            speed=float(config.get("tts_speed", 1.0)),
            api_key=config.get("tts_api_key", ""),
            chunk_chars=int(config.get("tts_chunk_chars", 260)),
            chunk_workers=int(config.get("tts_chunk_workers", 1)),
            chunking_enabled=bool(config.get("tts_chunking_enabled", True)),
            request_timeout_seconds=float(config.get("tts_request_timeout_seconds", 240.0)),
            lifecycle_config=config,
        )
        fallback = WindowsSapiTTSEngine(
            voice=config.get("tts_fallback_voice", ""),
            rate=int(config.get("tts_fallback_rate", config.get("tts_rate", 0))),
            volume=int(config.get("tts_volume", 100)),
        )
        warm_local_tts_service(config, wait_seconds=0.0)
        engine = ResilientTTSEngine(primary, fallback, config)
    else:   # edgetts (default)
        voice  = config.get("tts_voice", "en-US-GuyNeural")
        engine = EdgeTTSEngine(voice=voice)
    return TTSPlayer(
        engine,
        duplicate_window_seconds=float(config.get("tts_duplicate_window_seconds", 20.0)),
        max_pending_utterances=int(config.get("tts_max_pending_utterances", 1)),
    )
