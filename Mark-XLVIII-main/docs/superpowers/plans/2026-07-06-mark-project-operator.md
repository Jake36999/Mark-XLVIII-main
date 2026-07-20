# Mark Project Operator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first working operator-mode project integration so Mark can route project operations through a registry and Aletheia bridge while gating risky actions.

**Architecture:** Keep Mark as the user-facing front door and add a focused `actions/project_operator.py` module. Store project metadata in a JSON registry under `config/`, add PowerShell startup scripts under `scripts/`, and wire a new Gemini tool declaration into `main.py`.

**Tech Stack:** Python 3.11+, stdlib JSON/socket/subprocess/pathlib, Mark's existing Gemini Live tool-calling pattern, Aletheia TCP JSON-RPC bridge.

---

### Task 1: Project Registry And Policy Classifier

**Files:**
- Create: `F:\Mark-XLVIII-main\Mark-XLVIII-main\config\project_registry.json`
- Create: `F:\Mark-XLVIII-main\Mark-XLVIII-main\actions\project_operator.py`
- Create: `F:\Mark-XLVIII-main\Mark-XLVIII-main\tests\test_project_operator.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/test_project_operator.py` with tests that load the registry, list all four projects, allow safe status operations, gate heavy operations, and block destructive commands.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_project_operator -v`
Expected: FAIL because `actions.project_operator` does not exist.

- [ ] **Step 3: Implement registry and classifier**

Create `project_registry.json` and `actions/project_operator.py` with `load_registry()`, `classify_operation()`, `list_projects()`, and `project_operator()`.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m unittest tests.test_project_operator -v`
Expected: PASS.

### Task 2: Aletheia Bridge Client And Safe Operations

**Files:**
- Modify: `F:\Mark-XLVIII-main\Mark-XLVIII-main\actions\project_operator.py`
- Modify: `F:\Mark-XLVIII-main\Mark-XLVIII-main\tests\test_project_operator.py`

- [ ] **Step 1: Write failing bridge tests**

Add tests for building JSON-RPC calls, returning setup guidance when the bridge is unavailable, and mapping `scout` to `mcp_scout_workspace`.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_project_operator -v`
Expected: FAIL for missing bridge behavior.

- [ ] **Step 3: Implement bridge client**

Add a small TCP JSON-RPC client and safe operation dispatch for `list_projects`, `status`, `scout`, `code_map`, and `handoff`.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m unittest tests.test_project_operator -v`
Expected: PASS.

### Task 3: Mark Tool Wiring

**Files:**
- Modify: `F:\Mark-XLVIII-main\Mark-XLVIII-main\main.py`
- Modify: `F:\Mark-XLVIII-main\Mark-XLVIII-main\tests\test_project_operator.py`

- [ ] **Step 1: Write failing wiring test**

Add a test that imports `main.py` with external dependencies stubbed and verifies `project_operator` is declared.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_project_operator -v`
Expected: FAIL because `project_operator` is not declared.

- [ ] **Step 3: Wire action into Mark**

Import `project_operator`, add its function declaration, and dispatch it in `_execute_tool()`.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m unittest tests.test_project_operator -v`
Expected: PASS.

### Task 4: Startup Scripts

**Files:**
- Create: `F:\Mark-XLVIII-main\Mark-XLVIII-main\scripts\start-aletheia-operator.ps1`
- Create: `F:\Mark-XLVIII-main\Mark-XLVIII-main\scripts\start-mark-operator.ps1`
- Create: `F:\Mark-XLVIII-main\Mark-XLVIII-main\scripts\operator-env.ps1`

- [ ] **Step 1: Write script validation test**

Add a test that confirms scripts exist and contain the registered project roots in `ALETHEIA_ALLOWED_ROOTS`.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_project_operator -v`
Expected: FAIL because scripts are missing.

- [ ] **Step 3: Add startup scripts**

Add scripts that configure Aletheia allowed roots, state path, bridge host/port, and launch the daemon/Mark app.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m unittest tests.test_project_operator -v`
Expected: PASS.

### Task 5: Start And Verify Local Pipeline

**Files:**
- No source edits expected.

- [ ] **Step 1: Run full focused tests**

Run: `python -m unittest tests.test_project_operator -v`
Expected: PASS.

- [ ] **Step 2: Start Aletheia daemon**

Run: `powershell -ExecutionPolicy Bypass -File .\scripts\start-aletheia-operator.ps1`
Expected: daemon starts on `127.0.0.1:8765` or reports missing dependencies/setup clearly.

- [ ] **Step 3: Start Mark**

Run: `powershell -ExecutionPolicy Bypass -File .\scripts\start-mark-operator.ps1`
Expected: Mark GUI starts, or reports missing API/config/dependencies clearly.

