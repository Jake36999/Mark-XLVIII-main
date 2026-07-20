# Mark Model Provider Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable OpenAI planner and LM Studio worker provider support for Mark text/code actions.

**Architecture:** Create `core/model_router.py` as the single text-generation boundary. Keep Gemini Live unchanged in `main.py`, and make selected Gemini text wrappers delegate to the router while preserving their current `.generate_content(...).text` interface.

**Tech Stack:** Python 3.11 stdlib, `requests`, existing Gemini SDK, PowerShell smoke scripts, `unittest`.

---

### Task 1: Router Tests

**Files:**
- Create: `tests/test_model_router.py`

- [ ] **Step 1: Write failing tests**

Add tests for config loading, role resolution, provider payload construction, and wrapper compatibility.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_model_router -v`

Expected: fail because `core.model_router` does not exist.

### Task 2: Provider Router

**Files:**
- Create: `core/model_router.py`

- [ ] **Step 1: Implement router**

Add config helpers, `ProviderSettings`, `call_text`, provider-specific request functions, and `ModelWrapper`.

- [ ] **Step 2: Run router tests**

Run: `python -m unittest tests.test_model_router -v`

Expected: pass.

### Task 3: Wire Coding Actions

**Files:**
- Modify: `actions/code_helper.py`
- Modify: `actions/dev_agent.py`
- Test: `tests/test_model_router.py`

- [ ] **Step 1: Add action wrapper tests**

Verify `code_helper._get_gemini()` uses the worker role and `dev_agent._get_model()` maps planner/writer models to planner/worker roles.

- [ ] **Step 2: Patch actions**

Replace direct Gemini client construction in those wrapper functions with `core.model_router.get_model_wrapper`.

- [ ] **Step 3: Run tests**

Run: `python -m unittest tests.test_model_router tests.test_project_operator -v`

Expected: pass.

### Task 4: Config Example And Smoke Scripts

**Files:**
- Create: `config/model_providers.example.json`
- Create: `scripts/test-openai-provider.ps1`
- Create: `scripts/test-lmstudio-provider.ps1`

- [ ] **Step 1: Add example config**

Document the provider keys without secrets.

- [ ] **Step 2: Add smoke scripts**

OpenAI script checks key presence and performs a tiny Responses API request. LM Studio script checks `/models` and performs a tiny chat completion request.

- [ ] **Step 3: Run syntax checks**

Run: `python -m py_compile core/model_router.py actions/code_helper.py actions/dev_agent.py`

Expected: pass.

### Task 5: Verification

**Files:**
- Existing test suite and smoke scripts.

- [ ] **Step 1: Run unit tests**

Run: `python -m unittest tests.test_model_router tests.test_project_operator -v`

Expected: pass.

- [ ] **Step 2: Run smoke scripts**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-lmstudio-provider.ps1`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-openai-provider.ps1`

Expected: pass when the external provider is configured and running; otherwise report actionable setup guidance.
