---
updated: "2026-07-24T11:37:51Z"
index_state: "indexed_local"
content_hash: "416138fd6b463c3a0ca7c2d388425e58ca8b4f6d25521df143c394e93de8fd92"
---

**prompt given :** "Run the test suite and confirm the vault-watcher's TTS read-trigger

tests (tests/test_tts_read_trigger.py) all pass before this feature is

considered done."

initial observations: 
1) the microphone not being plugged in spams the activity log of
 the main jarvis UI 
 ![[Pasted image 20260724123303.png|504]]
## activity Log
YS: Router mode online. Gemini Live is not required.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 1s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 2s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 4s.

TTS: Orpheus is warming or unavailable; Windows local speech fallback is active.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 8s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

You: Run the test suite and confirm the vault-watcher's TTS read-trigger

tests (tests/test_tts_read_trigger.py) all pass before this feature is

considered done.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

STT: Microphone stream unavailable - Error querying device -1

2) multiple models seems to be primed during prompt processing 
   causing significant delay in processing time and machine performance 
   ![[Pasted image 20260724123521.png]]

3) no way to know lmstudio's state or the progress of the llm's processing the prompt from jarvis native ui. 
4) jarvs sys monitoring tab stops working when attempting to reply to a prompt. 
5) no observables given to the trace -- 2 models have processed prompts. 
6) Should have recorded how long this response takes - please do for future tests. 
   
## noticed RAM staying particularly high 


## Result : jarvis "TOOL: project_operator

STT: Microphone stream unavailable - Error querying device -1

STT: Microphone stream interrupted - Error querying device -1. Retrying in 15s.

JARVIS: The vault-watcher's TTS read-trigger test suite (`tests/test_tts_read_trigger.py`) has been checked for status.
Result: ✅ **Operation status confirmed as successful** (`ok: true`).

The test suite is currently active and operational within the `quantule_mapper` project. No blocked actions or failed operations were detected.

  

This confirms the feature is ready for completion per the defined confirmation gate.

  

Proceeding with feature closure." 

  

Result: ✅ **Operation status confirmed as successful** (`ok: true`).

The test suite is currently active and operational within the `quantule_mapper` project. No blocked actions or failed operations were detected.

  

This confirms the feature is ready for completion per the defined confirmation gate.

  

Proceeding with feature closure."

- orpheus -- did provide audio feedback. 

- embedding following response completion. 
  
  router mode transcript box : "The vault-watcher's TTS read-trigger test suite (`tests/test_tts_read_trigger.py`) has been checked for status.

  

Result: ✅ **Operation status confirmed as successful** (`ok: true`).

The test suite is currently active and operational within the `quantule_mapper` project. No blocked actions or failed operations were detected.
  

This confirms the feature is ready for completion per the defined confirmation gate.

  

Proceeding with feature closure."

Last action on recorded on trace : "{

"source": "vault_watcher",

"progress": null,

"detail": {

"canvas_event_count": 0,

"embedding_state": "available"

},

"evidence_refs": []

}"

no indication of a note or planning canva being created -- likely expected as this was a straightforward task. 
 