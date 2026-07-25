---
id: "jarvis-20260725T072040Z-e4defa34"
title: "WS4d Execution-Quality Evaluation — Context Preamble Before/After"
type: "report"
status: "active"
created: "2026-07-25T07:20:40Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "ws4d", "canvas-planning", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T07:20:40Z"
review_after: ""
source_version: 1
content_hash: "e1e4619ebac7f562ab573347f634f0254d0351b894945ef17212e42cef430dec"
supersedes: []
contradicts: []
depends_on: []
depended_on_by: []
extends: []
extended_by: []
implements: []
implemented_by: []
consumes: []
consumed_by: []
related: []
deleted: false
deleted_at: ""
lifecycle: "short_term"
sync_error: ""
---

> [!info] Scope
> WS4d's own deferred validation question, acted on the same week: does the deterministic context preamble ([[2026-07-25-ws4d-context-inheritance-build-and-live-test]]) actually change what the executing model produces, not just whether the mechanism is structurally present? Two focused, real, non-mocked comparisons -- the same node dispatched twice through `core.model_router.call_text`, once with the bare node prose (pre-WS4d behavior) and once with the real compiled `inputs.prompt` (post-WS4d, preamble included) -- everything else (model, role, system prompt, timeout) held identical. This is qualitative, illustrative evidence from two examples, not a rigorous controlled study across many prompts; that remains a real follow-up if a statistically grounded answer is ever needed.

## Test 1 -- system-goal grounding

Scenario: a research node ("Research how the OAuth callback URL should be configured") inside a two-branch OAuth plan (backend flow / frontend UI) for "the JARVIS operations dashboard... a local-only Flask app used by one operator, not a public multi-tenant service."

**Without context** (14s): a generic, provider-agnostic OAuth explainer covering Google/Azure/GitHub, with placeholder examples (`https://myapp.com/callback`). Never mentions local, localhost, single-operator, or Flask. Reads like documentation, not an answer for this system.

**With context** (18s): opens by naming the actual constraint -- "Since the JARVIS operations dashboard is a local-only Flask application used by a single operator..." -- and closes with a concrete, actionable recommendation: register `http://localhost:5000/auth/callback`, explicitly reasoning that HTTPS "though [recommended in production]... not applicable here, as it's a local-only app." Concrete and system-specific throughout, not generic.

## Test 2 -- sibling-branch coherence (the more serious failure mode)

Scenario: branch A's backend node states its own design explicitly: "exchange the authorization code for a token server-side, then set a signed session cookie. The frontend never sees the OAuth token directly." Branch B's research node asks "what the frontend Sign in button needs to do after the user completes the OAuth flow" -- deliberately testing whether the sibling-branch summary line (not the system-goal line) carries real weight.

**Without context** (14s): a generic frontend-auth answer that gets this system's own architecture wrong -- point 3 recommends the frontend "store a token (such as an access token or session token) in local storage or cookies," directly contradicting branch A's stated design. Two branches, each individually reasonable, silently building an incompatible system.

**With context** (20s): correctly reflects branch A's constraint throughout -- the frontend sends the authorization code to the backend, the backend performs the token exchange and sets a signed session cookie, and point 7 is stated as its own explicit rule: "Frontend Does Not Store or Expose OAuth Tokens... The token exchange and session management are entirely handled by the backend." The two branches are now describing one coherent system instead of two branches that would conflict at integration time.

## Assessment

Test 2 is the more important result: it isn't showing the preamble adds generic helpful color, it's showing the preamble prevents a real architectural inconsistency between two independently-dispatched nodes that each look individually reasonable. This is precisely the failure mode the owner's original request named -- "coax the agents to do what we need them to do across more simplistic nodes" -- and precisely what D1's "every node is a self-contained prompt" leaves no structural defense against on its own. Two real, non-mocked, non-cherry-picked-favorably comparisons (both prompts and both full responses preserved) is enough to call the mechanism's value demonstrated, not just structurally present. A larger controlled study (many prompts, statistical comparison, in the spirit of the session's earlier 16-prompt test) remains explicitly out of scope here and would only be worth building if a quantitative answer becomes necessary later.

## Related

[[2026-07-25-ws4d-context-inheritance-build-and-live-test]] · [[Planning Subsystem Roadmap]]
