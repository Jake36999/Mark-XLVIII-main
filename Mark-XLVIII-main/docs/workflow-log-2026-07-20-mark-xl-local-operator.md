# Mark XLVIII Local Operator Workflow Log

Created: 2026-07-20

Workspace root: `F:\Mark-XLVIII-main`

Primary Mark app root: `F:\Mark-XLVIII-main\Mark-XLVIII-main`

This log summarizes the setup and integration work completed so far for turning Mark XLVIII into a local-first project operator using Aletheia, LM Studio, OpenAI fallback/gating, and local speech.

No API keys or secrets are recorded here.

## Initial Goal

The goal was not to build a new platform. The goal was to set up the existing Mark XLVIII platform as the front door for several long-running personal projects, with Codex and Claude remaining the main high-value development orchestrators and OpenClaw acting as a lightweight continuity/helper layer between longer sessions.

Projects supplied for integration:

- `F:\quantule_mapper`
  - Custom physics exploration bench.
  - Runs may be orchestrated.
  - Scientific analysis should remain user-led or Claude-led.
- `F:\knowledge_compiler_engine (DAG Engine)`
  - Heavy custom-agent training/refinement system.
  - Future lightweight mode should integrate with tool-assist agents.
- `F:\Mark-XLVIII-main`
  - Current Mark XLVIII platform.
- `F:\network_management`
  - Custom CSI/RF pipeline using routers and Intel 5300 receivers.
  - Already has substantial ML integration.

Authority model selected:

- Operator mode is allowed.
- Destructive actions remain gated.
- Heavy compute, RF deployment, service stop/restart, git writes, secrets, and cleanup require confirmation.
- Safe inspection/status actions can run directly.

## Repository Orientation

The workspace was identified as a bundle rather than a single git repository:

- `Mark-XLVIII-main`
  - Voice/HUD assistant, PyQt UI, dashboard, memory, actions, Gemini Live integration.
- `Agent_backend` / Aletheia
  - Orchestration layer, MCP gateway, memory, workflows, allowed-root safety.
- `ToolSet`
  - Deterministic repo/workspace tooling: maps, semantic slicing, manifests, package/handoff generation.
- `ClawTeam-OpenClaw-main`
  - Multi-agent continuity layer for lighter coding assistance between Codex/Claude sessions.

High-level intended architecture:

```text
Mark UI / voice front door
  -> Aletheia operator bridge and project registry
  -> ToolSet deterministic repo tools
  -> OpenClaw / Codex / Claude continuity helpers
  -> LM Studio local models and optional OpenAI high-tier planning
```

## Project Operator Setup

Added a project operator registry and Mark action layer so Mark can route project operations through Aletheia rather than directly shelling out.

Key files added or changed:

- `config/project_registry.json`
- `actions/project_operator.py`
- `scripts/operator-env.ps1`
- `scripts/start-aletheia-operator.ps1`
- `scripts/start-mark-operator.ps1`
- `tests/test_project_operator.py`
- `main.py`

The registry contains entries for:

- `quantule_mapper`
- `knowledge_compiler_engine`
- `mark_platform`
- `network_management`

Safety behavior:

- Safe status/scout operations can run without confirmation.
- Destructive actions are blocked unless an explicit confirmation record exists.
- Heavy operations require confirmation.
- Operator bridge results are compacted before returning to Mark.

Verification performed earlier:

```powershell
python -m unittest tests.test_project_operator -v
python -m py_compile main.py ui.py actions\project_operator.py
```

The Aletheia bridge was previously verified reachable at:

```text
127.0.0.1:8765
```

Note: the latest process snapshot in this log did not show `python -m orchestrator.main`, so Aletheia may need to be restarted if operator bridge calls are needed again.

## Gemini Diagnostics And Decoupling

Mark originally depended on Gemini Live and would drop into `SLEEPING` when the Gemini API failed.

Gemini was tested directly and returned:

```text
429 RESOURCE_EXHAUSTED
Your prepayment credits are depleted.
```

That confirmed the local Mark/Aletheia pieces were not the root cause of the sleeping state. Gemini was reachable but the Google project had no usable credits.

Changes made:

- Mark defaults to router mode instead of requiring Gemini Live.
- Gemini Live only starts when explicitly configured.
- Google billing/quota/nonretryable auth failures switch Mark to router mode instead of permanently blocking the assistant.
- Text commands route through `core.model_router.call_text()` when Gemini Live is disabled or unavailable.
- Dashboard/text commands no longer get dropped just because Gemini is unavailable.

Important behavior:

- Gemini remains optional.
- Router mode is the normal local-first mode.
- Local model/OpenAI routing keeps Mark usable even when Gemini is invalid, out of credits, or absent.

## Setup UX Changes

The first-run setup overlay originally required a Gemini API key. It was later expanded to accept OpenAI, then corrected again so local mode does not require either Gemini or OpenAI.

Changed:

- `ui.py`
  - `_is_config_ready()` now treats local router mode as ready when:
    - `os_system` is set.
    - `assistant_mode` is `router`.
    - At least one local provider such as `lmstudio` is configured.
  - Gemini API key field is optional.
  - OpenAI API key field is optional.
  - Setup no longer blocks launch when cloud keys are blank.
  - Entering a new OpenAI key sets planner preference to OpenAI.

Regression tests added/updated:

- `tests/test_router_mode.py`
- `tests/test_ui_setup_config.py`

Verified:

```powershell
python -m unittest tests.test_router_mode tests.test_ui_setup_config -v
```

## Model Provider Split

Implemented a model router in:

- `core/model_router.py`

Initial provider roles:

- Planner:
  - Optional OpenAI high-tier model.
  - Falls back to LM Studio if OpenAI key is missing/invalid/errors.
- Worker:
  - LM Studio local models.
- Gemini:
  - Optional legacy/live route only.

OpenAI behavior:

- Uses OpenAI Responses API when a valid key is present.
- OpenAI key validity is checked via `/models`.
- Validation is cached for 10 minutes.
- If the key is missing, invalid, unreachable, quota-failing, or the OpenAI call fails, the router falls back to LM Studio local models.

LM Studio behavior:

- Uses OpenAI-compatible `/v1/chat/completions`.
- Local system prompts are folded into the user message for better GGUF chat-template compatibility.
- This fixed Mistral's template error:

```text
Only user and assistant roles are supported!
```

Current LM Studio base URL:

```text
http://localhost:1234/v1
```

## Local Model Routing

The LM Studio developer log showed that Mark was already routing locally, but it tried to load large models for a simple greeting:

- `hello jarvis` first tried `qwen/qwen3.5-9b`.
- Qwen failed due to CUDA/system allocation pressure.
- Mark then tried `google/gemma-4-e4b`.
- Gemma also failed allocation.

To fix this, context-based model routing and fallback were added.

Current editable route map in `config/api_keys.json`:

```json
"model_routes": {
  "quick": [
    "mistralai/mistral-7b-instruct-v0.3",
    "google/gemma-4-e4b",
    "qwen/qwen3-vl-4b"
  ],
  "main": [
    "qwen/qwen3.5-9b",
    "mistralai/mistral-7b-instruct-v0.3",
    "deepseek-r1-0528-qwen3-8b",
    "google/gemma-4-e4b"
  ],
  "reasoning": [
    "deepseek-r1-0528-qwen3-8b",
    "qwen/qwen3.5-9b",
    "mistralai/mistral-7b-instruct-v0.3"
  ],
  "code": [
    "deepseek-r1-0528-qwen3-8b",
    "qwen/qwen3.5-9b",
    "mistralai/mistral-7b-instruct-v0.3"
  ],
  "vision": [
    "qwen/qwen3-vl-4b",
    "qwen3-vl-30b-a3b-instruct"
  ],
  "worker": [
    "google/gemma-4-e4b",
    "mistralai/mistral-7b-instruct-v0.3",
    "qwen/qwen3-vl-4b"
  ]
}
```

Routing intent:

- `quick`
  - Greetings and short prompts.
  - Avoids loading the larger Qwen 9B model.
- `main`
  - Larger planning/orchestration tasks.
- `reasoning`
  - Analysis, diagnosis, math, physics, proof/tradeoff style prompts.
- `code`
  - Debugging, implementation, tests, refactors.
- `vision`
  - Screenshots, OCR, image/visual requests.
- `worker`
  - Subtasks and smaller local grunt work.

Real smoke tests passed:

```text
hello jarvis -> local quick route replied successfully
heavier planner prompt -> local route replied successfully
```

## OpenAI Gate

Added a prompt-entry gate in `core/model_router.py`:

1. If the configured provider is OpenAI, validate the key first.
2. If valid, use OpenAI Responses API.
3. If missing, invalid, quota-failing, unreachable, or request-failing, use LM Studio fallback.
4. Cache the key validity for 10 minutes.

Current live behavior:

- `planner_provider` is set to `openai`.
- `planner_model` is set to `gpt-5.4`.
- No OpenAI key is currently stored in config.
- With no key, the router falls back to local LM Studio models.

Verified live fallback:

```text
planner_provider openai
has_openai_key False
hello jarvis -> local reply succeeded
```

## Text To Speech

TTS is functional.

Work completed:

1. Added Windows local TTS fallback:
   - `WindowsSapiTTSEngine` in `core/tts.py`
   - Uses SAPI/System.Speech.
   - Inspired by the lightweight TTS approach found in `F:\network_management`.

2. Added OpenAI-compatible TTS engine:
   - `OpenAICompatibleTTSEngine` in `core/tts.py`
   - Targets endpoints such as `/v1/audio/speech`.
   - Used for local Orpheus bridge.

3. Added Orpheus TTS bridge:
   - Cloned under `tools/Orpheus-FastAPI-LMStudio`
   - Patched to allow configurable LM Studio model ID.
   - Patched to expose `/runtime` diagnostics.
   - Patched to avoid reload-mode spawning problems.
   - Patched startup print to avoid Windows console Unicode crash.
   - Patched port from 5005 to 5006 to avoid stale/ghost listener issues.

4. Added launcher:
   - `scripts/start-orpheus-tts-bridge.ps1`

5. Current TTS endpoint:

```text
http://127.0.0.1:5006/v1
```

Current TTS config:

```json
"tts_engine": "orpheus",
"tts_url": "http://127.0.0.1:5006/v1",
"tts_model": "orpheus",
"tts_voice": "tara",
"tts_response_format": "wav"
```

TTS bridge was verified returning real WAV audio:

```text
status 200
content-type audio/wav
```

## Orpheus / LM Studio TTS Details

Two TTS GGUF models were inspected:

- `F:\.lmstudio\models\mradermacher\Bhojpuri_text_to_speech-GGUF\Bhojpuri_text_to_speech.Q4_K_S.gguf`
- `F:\.lmstudio\models\D-Khalid\Orpeus_Text_To_Speech\unsloth.Q4_K_M.gguf`

LM Studio model IDs:

- `bhojpuri_text_to_speech`
- `orpeus_text_to_speech`

Important finding:

- LM Studio does not directly expose these GGUF TTS models through `/v1/audio/speech`.
- Orpheus-style TTS uses a Llama backbone to emit audio tokens.
- A SNAC decoder is required to convert those tokens to audio.
- The FastAPI bridge handles:
  - text prompt
  - LM Studio `/v1/completions`
  - Orpheus audio token generation
  - SNAC decoding
  - WAV response

The base Llama model card was used to confirm that Llama 3.2 3B Instruct itself is text-in/text-out, not audio-out.

References used:

- `https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct`
- `https://github.com/TheLocalLab/Orpheus-FastAPI-LMStudio`
- `https://lmstudio.ai/docs/developer/rest`

## CUDA / GPU Setup

The system has two GPUs:

- NVIDIA GeForce GTX 1080
- Radeon RX 5500 XT

User preference:

- Focus on the NVIDIA 1080.

CUDA audit:

- `nvidia-smi` available.
- NVIDIA driver reported CUDA 13.0 capability.
- `nvcc` available.
- CUDA toolkits found:
  - `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.2`
  - `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6`
  - `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.1`

Existing CUDA PyTorch environments found:

- `F:\network_management\Wi-Fi Sensing & CSI Data Extraction\Model_training\.venv-gtx1080`
  - `torch 2.7.1+cu126`
  - CUDA available.
  - Sees `NVIDIA GeForce GTX 1080`.
- `F:\knowledge_compiler_engine (DAG Engine)\.venv_semantic`
  - `torch 2.5.1+cu121`
  - CUDA available.
- `F:\knowledge_compiler_engine (DAG Engine)\.venv_training`
  - `torch 2.5.1+cu121`
  - CUDA available.

No CUDA torch reinstall was performed.

Only missing bridge dependencies were installed into the existing GTX1080 venv:

- `snac`
- `fastapi`
- `uvicorn`
- `pydantic`
- `sounddevice`
- `python-multipart`

The Orpheus bridge launcher now prefers:

```text
F:\network_management\Wi-Fi Sensing & CSI Data Extraction\Model_training\.venv-gtx1080\Scripts\python.exe
```

Runtime diagnostics from `/runtime` confirmed:

```text
torch 2.7.1+cu126
cuda_available True
cuda_devices ['NVIDIA GeForce GTX 1080']
CUDA_VISIBLE_DEVICES 0
```

## Speech To Text

Initial STT status was dependency/config only. It has now been wired into router mode.

Completed:

- Config defaults include:
  - `stt_engine`: `vosk`
  - `stt_language`: `en-us`
- Dependencies were added/installed:
  - `vosk`
  - `miniaudio`
  - `sounddevice`
- Existing `core/stt.py` contains Vosk and Whisper STT classes.

Completed later in this workflow:

- Live mic capture through `sounddevice`.
- Vosk streaming recognition.
- Router-mode transcript handoff through `JarvisLive._submit_router_voice_transcript()`.
- Router-mode STT loop startup through `JarvisLive._listen_router_stt()`.

Current status:

- Spoken output is functional.
- Typed prompts are functional.
- Spoken input capture and Vosk transcription were verified with `Microphone (Jabra Evolve2 40)`.
- Router-mode transcript handoff is covered by tests.
- A live in-app voice prompt should now route through Vosk to the local/OpenAI-gated model router.

Verification sample:

```text
CAPTURE_STATS rms=1840.03 peak=28527
TRANSCRIPT=mark voice input
STT_OK=True
```

## Dependency Checks

`scripts/check-mark-dependencies.ps1` was updated to check required runtime modules, including speech additions:

- `PyQt6`
- `requests`
- `google.genai`
- `sounddevice`
- `comtypes`
- `vosk`
- `miniaudio`
- `edge_tts`
- `snac`
- `fastapi`
- `uvicorn`
- `cryptography`
- `psutil`
- `PIL`
- `cv2`
- `mss`

`requirements.txt` was updated with local speech dependencies:

- `vosk`
- `miniaudio`
- `edge-tts`
- `snac`

## Current Live Config

Current key routing/config state:

```json
{
  "assistant_mode": "router",
  "voice_provider": "disabled",
  "voice_enabled": true,
  "tts_engine": "orpheus",
  "tts_url": "http://127.0.0.1:5006/v1",
  "stt_engine": "vosk",
  "planner_provider": "openai",
  "planner_model": "gpt-5.4",
  "worker_provider": "lmstudio",
  "worker_model": "google/gemma-4-e4b",
  "lmstudio_url": "http://localhost:1234/v1"
}
```

Important:

- No OpenAI key is recorded in this log.
- If no OpenAI key is present, Mark falls back to LM Studio.
- If an OpenAI key is invalid, Mark falls back to LM Studio.
- If OpenAI errors or quota fails, Mark falls back to LM Studio.
- `gpt-5.4` should be confirmed against actual OpenAI account/model availability when a key is added.

## Current Running Processes

Latest process snapshot showed:

- Orpheus bridge launcher:
  - PID `32440`
  - `scripts\start-orpheus-tts-bridge.ps1`
- Orpheus bridge parent Python:
  - PID `32588`
  - GTX1080 venv Python.
- Orpheus bridge listener:
  - PID `29132`
  - Listening on port `5006`.
- Mark launcher:
  - PID `31752`
  - `scripts\start-mark-operator.ps1`
- Mark UI:
  - PID `25100`
  - `python.exe .\main.py`

## Verification Commands Used

Common verification commands used during this workflow:

```powershell
python -m py_compile core\model_router.py main.py ui.py core\tts.py
python -m py_compile tools\Orpheus-FastAPI-LMStudio\app.py tools\Orpheus-FastAPI-LMStudio\tts_engine\inference.py

python -m unittest tests.test_model_router tests.test_router_mode tests.test_ui_setup_config tests.test_speech_runtime -v
python -m unittest tests.test_project_operator -v

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check-mark-dependencies.ps1
```

Recent full relevant verification:

```text
32 tests OK
py_compile OK
OpenAI missing-key fallback answered locally
Orpheus bridge returned audio/wav
UI readiness true without cloud keys
```

## Known Caveats And Next Steps

1. STT is not complete.
   - Vosk is configured and installed.
   - Live mic-to-router loop still needs implementation/verification.

2. Aletheia may not currently be running.
   - The bridge was previously verified.
   - The latest process snapshot did not show `orchestrator.main`.
   - Restart with `scripts\start-aletheia-operator.ps1` before relying on operator bridge calls.

3. LM Studio memory pressure still matters.
   - The router now avoids heavy models for small prompts and falls back on load errors.
   - A future improvement should call LM Studio's native unload endpoint before switching between large model contexts.

4. Valid OpenAI model IDs should be confirmed.
   - Current planner model is `gpt-5.4`.
   - If the account does not expose that exact model ID, OpenAI will fail and Mark will fall back locally.

5. Some actions still contain direct Gemini-specific logic.
   - Several older actions use Gemini clients directly.
   - Core prompt routing is now safe, but individual action modules should be migrated gradually to `core.model_router`.

6. Mark is not a git checkout.
   - No commits were made.
   - Changes are local files in the extracted project directory.

## Practical Resume Point

If resuming this workflow, the best next technical slice is:

1. Start/check Aletheia operator bridge.
2. Implement the Vosk live mic input loop.
3. Migrate remaining direct Gemini action calls to `core.model_router`.
4. Add LM Studio model unload/load management for large model switching.
5. Add a small status screen or command in Mark showing:
   - current provider
   - selected route
   - active LM Studio model
   - TTS bridge status
   - STT status
