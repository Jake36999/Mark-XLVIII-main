# JARVIS → Home Assistant Bridge (smart-device control)

**Goal:** Give JARVIS a `home_assistant` tool that controls smart devices — lights, switches, and Alexa-linked entities — by calling Home Assistant's REST API on Frank. JARVIS proposes and calls; HA and its Alexa integration do the physical bridging.

**Tech Stack:** Python 3.11 stdlib + `requests`, existing MARK tool/dispatcher/capability-registry pattern, `unittest`.

---

## Environment (verified 2026-07-23)

| Node | Fact |
|---|---|
| Windows PC (JARVIS) | `192.168.0.190`, LM Studio on `1234`, dashboard on `8000/8001` |
| Frank (Home Assistant) | `192.168.0.50`, HA in Docker `network_mode: host`, UI + REST on **`:8123`** |
| Alexa | Bridged on the HA side (Nabu Casa / Alexa Smart Home skill / `emulated_hue`) — out of scope here |

JARVIS talks only to HA's REST API. Alexa is reached *through* HA.

---

## Design decisions

- **Direction is JARVIS → HA only.** JARVIS calls HA; HA is authoritative for device state. No reverse control channel in this plan.
- **Token, not password.** Auth is a HA **Long-Lived Access Token** (HA → user profile → Long-Lived Access Tokens), stored via the session credential broker pattern — never written to config, logs, or the vault, mirroring the OpenAI key handling.
- **State-changing calls are confirmation-gated.** `turn_on`/`turn_off`/`set` are writes with real-world effect → `requires_approval` in the dispatcher, like every other side-effectful tool. Read-only calls (`states`, `list_entities`) are ungated.
- **Fits the existing tool shape.** New `actions/home_assistant.py` action module + dispatcher entry + `main.py` TOOL_DECLARATIONS entry + capability-registry L0/L1 card, exactly like `reminder`/`weather_report`.
- **Untrusted responses.** HA entity names/attributes are external data → passed through `core.evidence.neutralise` before they ever reach a prompt (reuses this session's hardening).

---

## Configuration (ships disabled)

```json
{
  "home_assistant_enabled": false,
  "home_assistant_url": "http://192.168.0.50:8123",
  "home_assistant_timeout_seconds": 10,
  "home_assistant_allowed_domains": ["light", "switch", "scene", "script", "media_player", "climate"]
}
```
The token is supplied at runtime via the credential broker, not this file.

---

## Tasks (TDD, each: write failing test → implement → run)

### Task 1: REST client core
- `actions/home_assistant.py`: `_call(method, path, ...)` against `{home_assistant_url}/api/...` with `Authorization: Bearer <token>`, bounded timeout, structured error on non-200 / unreachable.
- Tests mock `requests`; cover 401 (bad token), timeout (HA down/unreachable), and a clean 200.

### Task 2: Read operations (ungated)
- `list_entities(domain="")` → `GET /api/states`, filtered to `home_assistant_allowed_domains`, entity names neutralised.
- `entity_state(entity_id)` → `GET /api/states/<id>`.
- Tests: filtering, neutralisation, missing entity.

### Task 3: Control operations (confirmation-gated)
- `call_service(domain, service, entity_id, data)` → `POST /api/services/<domain>/<service>`.
- Refuse any domain outside `home_assistant_allowed_domains` with a clear reason.
- Tests: allowed domain succeeds, disallowed refused, payload shape correct.

### Task 4: Wire the tool
- Dispatcher entry + effect classification: reads ungated, `call_service` gated as `write`.
- `main.py` TOOL_DECLARATIONS: operations `list_entities | entity_state | call_service`, params `domain | entity_id | service | data`.
- Capability-registry L0 card + L1 manifest; triggers ("turn on/off the …", "set the …", "what's the state of …").
- Corpus case: a hostile HA entity name cannot inject a fence into a downstream prompt.

### Task 5: Live validation (needs Jake — I can't reach Frank)
- Jake mints a Long-Lived token in HA and confirms reachability: `curl -H "Authorization: Bearer <token>" http://192.168.0.50:8123/api/` → `{"message": "API running."}`.
- Then: `list_entities("light")` returns real lights; `call_service("light","turn_off", <one light>)` toggles it; confirm the same entity is visible to Alexa.

---

## Open questions for Jake

1. **Which Alexa bridge** is HA using — Nabu Casa cloud, the self-hosted Alexa Smart Home skill, or `emulated_hue`? (Affects nothing in this tool, but determines whether Alexa already sees your entities.)
2. **Scope of control** — start read-only + lights/switches, or include `media_player`/`climate`/`scene` from the outset?
3. **Do you also want direction A** (HA/automations able to *call* JARVIS via `/api/command` on 8000)? That's a separate, smaller task and carries the LAN-exposure caveat.

---

## Non-goals
- No direct Alexa API calls (HA owns that bridge).
- No reverse HA→JARVIS channel in this plan (that's direction A).
- No change to LM Studio binding or firewall — those are the *LLM* connection, handled separately in the chat diagnosis.
