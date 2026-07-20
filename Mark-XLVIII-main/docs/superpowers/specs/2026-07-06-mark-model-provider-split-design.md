# Mark Model Provider Split Design

## Goal

Let Mark keep its current Gemini Live voice loop while routing text, coding, and project-assist work through a configurable split of paid OpenAI planning models and local LM Studio worker models.

## Architecture

Add a small provider router in `core/model_router.py`. The router reads `config/api_keys.json` and environment variables, normalizes task roles such as `planner` and `worker`, and exposes one text-generation API that existing actions can call without knowing which provider is active.

Gemini remains the default Live audio provider in `main.py`. This avoids a larger Realtime/audio migration while Gemini billing is being sorted out. Text actions can continue working even if Gemini Live is sleeping because their provider path is independent.

## Provider Roles

- `planner`: high-quality planning, architecture, and multi-step task decomposition. Default provider is OpenAI.
- `worker`: local or low-cost code drafting, debugging, and repetitive implementation assistance. Default provider is LM Studio.
- `gemini`: retained as an optional fallback/provider for existing behavior once Gemini credits are usable.

## Configuration

The router reads:

- `OPENAI_API_KEY` from the environment first.
- `openai_api_key` from `config/api_keys.json` as fallback.
- `planner_provider`, default `openai`.
- `planner_model`, default `gpt-5.5`.
- `worker_provider`, default `lmstudio`.
- `worker_model`, default `qwen/qwen3-4b`.
- `lmstudio_url`, default `http://localhost:1234/v1`.
- Existing `gemini_api_key` remains supported.

No smoke script or test prints secret values.

## Data Flow

Existing actions call a wrapper with a prompt and role:

1. `code_helper` calls the router with role `worker`.
2. `dev_agent` planner calls the router with role `planner`.
3. `dev_agent` writer calls the router with role `worker`.
4. The router builds the provider-specific HTTP or SDK request.
5. The action receives an object with a `.text` attribute, preserving the current Gemini-style call sites.

## Error Handling

Missing OpenAI keys produce a clear configuration error. LM Studio connection failures tell the user to start LM Studio API/server mode. Provider HTTP errors include status code and short response text without including secrets.

## Testing

Unit tests cover:

- Environment key precedence over config key.
- Role-specific model/provider selection.
- OpenAI Responses payload construction.
- LM Studio chat completions payload construction.
- Gemini-style wrapper compatibility for existing action code.

Smoke scripts cover:

- OpenAI key presence and a tiny Responses API request.
- LM Studio `/models` reachability and a tiny chat completion request.
