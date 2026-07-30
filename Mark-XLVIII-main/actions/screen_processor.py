from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import numpy as np

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

from core.runtime_config import load_runtime_config, save_runtime_config

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE        = _base_dir()
def _load_config() -> dict:
    return load_runtime_config()


def _save_config_key(key: str, value) -> None:
    try:
        cfg = _load_config()
        cfg[key] = value
        save_runtime_config(cfg)
    except Exception as e:
        print(f"[Vision] ⚠️  Could not save config key '{key}': {e}")




def _get_os() -> str:
    return _load_config().get("os_system", "windows").lower()


_IMG_MAX_W = 1280
_IMG_MAX_H = 720
_JPEG_Q    = 82

# A screenshot bound for OCR is a different problem from a webcam frame bound
# for scene description, and it used to be treated as the same one. These
# numbers were sized for a Gemini Live *stream*, where continuous frames crossed
# the network and bandwidth set the budget. A single capture handed to a model
# on localhost has no such budget, and the cost of getting it wrong is total:
# downscaling a 1920x1080 desktop to 1280x720 with BILINEAR and JPEG 82 leaves
# UI text a few pixels tall. Measured live, the OCR model answered "the image is
# too blurry to recognize any text content" and then hallucinated fragments.
#
# 2560x1440 lets an ordinary 1080p or 1440p display through untouched; anything
# larger is resampled with LANCZOS, which preserves small text far better than
# BILINEAR. The camera path keeps the smaller size -- describing a room does not
# need the detail, and the webcam does not produce it.
_OCR_MAX_W  = 2560
_OCR_MAX_H  = 1440
_OCR_JPEG_Q = 92



def _compress(
    img_bytes: bytes,
    source_format: str = "PNG",
    *,
    max_size: tuple[int, int] | None = None,
    quality: int | None = None,
    resample=None,
) -> tuple[bytes, str]:
    if not _PIL:
        return img_bytes, f"image/{source_format.lower()}"

    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail(max_size or (_IMG_MAX_W, _IMG_MAX_H), resample or PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality or _JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[Vision] ⚠️  Image compress failed: {e}")
        return img_bytes, f"image/{source_format.lower()}"

def _capture_screen() -> tuple[bytes, str]:

    if not _MSS:
        raise RuntimeError("mss is not installed. Run: pip install mss")

    with mss.mss() as sct:
        monitors = sct.monitors          # [0] = all combined, [1..n] = real screens
        target   = monitors[1] if len(monitors) > 1 else monitors[0]
        shot     = sct.grab(target)
        png      = mss.tools.to_png(shot.rgb, shot.size)

    return _compress(
        png,
        "PNG",
        max_size=(_OCR_MAX_W, _OCR_MAX_H),
        quality=_OCR_JPEG_Q,
        resample=PIL.Image.LANCZOS if _PIL else None,
    )


def _cv2_backend() -> int:
    """Return the best OpenCV camera backend for the current OS."""
    if not _CV2:
        return 0
    os_name = _get_os()
    if os_name == "windows":
        return cv2.CAP_DSHOW    
    if os_name == "mac":
        return cv2.CAP_AVFOUNDATION  
    return cv2.CAP_ANY


def _probe_camera(index: int, backend: int, warmup: int = 5) -> bool:

    if not _CV2:
        return False
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    return bool(np.mean(frame) > 8)


def _detect_camera_index() -> int:

    backend = _cv2_backend()
    print("[Vision] 🔍 Auto-detecting camera...")
    for idx in range(6):
        if _probe_camera(idx, backend):
            print(f"[Vision] ✅ Camera found at index {idx}")
            _save_config_key("camera_index", idx)
            return idx
        print(f"[Vision] ⚠️  Camera index {idx}: no usable frame")

    print("[Vision] ⚠️  No camera found — defaulting to index 0")
    _save_config_key("camera_index", 0)
    return 0


def _get_camera_index() -> int:
    cfg = _load_config()
    if "camera_index" in cfg:
        return int(cfg["camera_index"])
    return _detect_camera_index()


def _capture_camera() -> tuple[bytes, str]:
    if not _CV2:
        raise RuntimeError("OpenCV (cv2) is not installed. Run: pip install opencv-python")

    index   = _get_camera_index()
    backend = _cv2_backend()
    cap     = cv2.VideoCapture(index, backend)

    if not cap.isOpened():
        raise RuntimeError(f"Camera index {index} could not be opened.")

    for _ in range(10):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("Camera returned no frame.")

    if _PIL:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)
        return buf.getvalue(), "image/jpeg"

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])
    return buf.tobytes(), "image/jpeg"






def screen_process(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Capture the screen or camera and answer a question about it, locally.

    Returns the answer, or "" on failure -- so the old `if screen_process(...)`
    truthiness check still reads correctly.

    This used to hand the capture to a Gemini Live session and return True the
    moment the bytes were queued, which reported success for work that had not
    happened yet and, once Live was switched off, for work that never happened
    at all. It now waits for a real answer from a local model.
    """
    params    = parameters or {}
    user_text = (params.get("text") or params.get("user_text") or "").strip()
    angle     = params.get("angle", "screen").lower().strip()

    if not user_text:
        print("[Vision] ⚠️  No question provided — aborting")
        return ""

    print(f"[Vision] ▶ angle={angle!r}  question='{user_text[:80]}'")

    try:
        if angle == "camera":
            image_bytes, mime_type = _capture_camera()
            print(f"[Vision] 📷 Camera: {len(image_bytes):,} bytes")
            if player and hasattr(player, "start_camera_stream"):
                try:
                    player.start_camera_stream()
                except Exception as _e:
                    print(f"[Vision] ⚠️  Camera stream failed: {_e}")
            elif player and hasattr(player, "show_camera_frame"):
                try:
                    player.show_camera_frame(image_bytes)
                except Exception as _e:
                    print(f"[Vision] ⚠️  Camera preview failed: {_e}")
        else:
            image_bytes, mime_type = _capture_screen()
            print(f"[Vision] 🖥️  Screen: {len(image_bytes):,} bytes")
    except Exception as e:
        print(f"[Vision] ❌ Capture error: {e}")
        return ""

    from actions.vision_pipeline import describe_image

    outcome = describe_image(image_bytes, mime_type, user_text, angle=angle)
    if angle == "camera" and player and hasattr(player, "stop_camera_stream"):
        try:
            player.stop_camera_stream()
        except Exception as _e:
            print(f"[Vision] ⚠️  Could not close camera: {_e}")
    if not outcome.get("ok"):
        print(f"[Vision] ❌ {outcome.get('error') or 'no answer'}")
        return ""
    print(f"[Vision] ✅ {outcome.get('path') or 'local'}")
    return str(outcome.get("answer") or "")



if __name__ == "__main__":
    print("[TEST] screen_processor.py")
    print("=" * 52)
    mode = input("angle — screen / camera (default: screen): ").strip().lower() or "screen"
    q    = input("Question (Enter = default): ").strip() or "What do you see? Be brief."

    t1 = time.perf_counter()
    answer = screen_process({"angle": mode, "text": q})
    print(f"\nAnswered in {time.perf_counter()-t1:.1f}s\n")
    print(answer or "Failed — no local vision model produced an answer.")
