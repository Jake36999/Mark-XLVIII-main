from __future__ import annotations

import platform as _platform
import subprocess as _subprocess

# ── Nuclear: force CREATE_NO_WINDOW on EVERY subprocess call on Windows ───────
# This patches Popen itself, so no per-file flag is needed anywhere.
if _platform.system() == "Windows":
    _OrigPopen = _subprocess.Popen

    class _Popen(_OrigPopen):
        def __init__(self, args, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
            kw.pop("startupinfo", None)   # drop any stale/shared STARTUPINFO
            super().__init__(args, **kw)

    _subprocess.Popen = _Popen
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import audioop
import re
import threading
import time
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

from ui import JarvisUI
from core.model_router import call_text, call_with_tools
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import _capture_camera, _capture_screen
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.project_operator  import project_operator
from actions.jarvis_memory     import jarvis_memory
from actions.capability_registry import capability_registry
from actions.model_lifecycle   import (
    cleanup_idle as cleanup_idle_models,
    model_lifecycle,
    resolve_config as resolve_model_lifecycle_config,
)
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.system_monitor    import SystemMonitor, get_system_status
from actions.proactive         import ProactiveEngine


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _load_runtime_config() -> dict:
    try:
        return json.loads(API_CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _get_api_key() -> str:
    return _load_runtime_config()["gemini_api_key"]


def _assistant_mode(cfg: dict | None = None) -> str:
    cfg = _load_runtime_config() if cfg is None else cfg
    return str(cfg.get("assistant_mode") or "router").strip().lower()


def _gemini_live_enabled(cfg: dict | None = None) -> bool:
    cfg = _load_runtime_config() if cfg is None else cfg
    mode = _assistant_mode(cfg)
    voice_provider = str(cfg.get("voice_provider") or "").strip().lower()
    wants_gemini = mode in {"gemini", "gemini_live", "live"} or voice_provider == "gemini"
    return bool(wants_gemini and cfg.get("gemini_api_key") and genai is not None and types is not None and sd is not None)


def _is_nonretryable_gemini_error(error: str) -> bool:
    err = str(error).lower()
    return any(
        token in err
        for token in (
            "prepayment credits are depleted",
            "resource_exhausted",
            "billing",
            "quota",
            "api key not valid",
            "1007",
            "1011",
        )
    )



def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)
_VOICE_FILLER_TRANSCRIPTS = {
    "ah",
    "eh",
    "er",
    "hm",
    "hmm",
    "huh",
    "mm",
    "mmm",
    "mhm",
    "uh",
    "uhh",
    "um",
    "umm",
}

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


def _is_noise_voice_transcript(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized in _VOICE_FILLER_TRANSCRIPTS

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": (
            "Searches the web. Use for ANY question about current facts, events, prices, "
            "or topics — always prefer this over guessing. "
            "Modes: 'search' (default), 'news' (latest headlines on a topic), "
            "'research' (deep comprehensive answer), 'price' (product cost lookup), "
            "'compare' (side-by-side comparison of items)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query or topic"},
                "mode":   {"type": "STRING", "description": "search | news | research | price | compare"},
                "items":  {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "Items to compare (compare mode)"},
                "aspect": {"type": "STRING", "description": "Comparison aspect: price | specs | reviews | features"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "system_status",
        "description": (
            "Returns real-time system metrics: CPU usage, RAM, GPU load, CPU temperature, "
            "uptime, and process count. Use when the user asks about computer performance, "
            "temperature, memory, or resource usage."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures the screen or webcam image and lets you analyze it. "
            "MUST be called when user asks what is on screen, what you see, "
            "look at camera, analyze my screen, etc. "
            "You have NO visual ability without this tool. "
            "After the image is captured it is sent directly to you — describe what you see and answer the user's question. "
            "When using camera: the live view stays open until user says close it or calls close_camera."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "close_camera",
        "description": (
            "Closes the live camera view shown on screen. "
            "Call when user says: close camera, stop camera, turn off camera, "
            "kamerayı kapat, kapat, creepy, etc."
        ),
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "project_operator",
        "description": (
            "Operates the user's registered development projects through the Mark/Aletheia control plane. "
            "Use this for project status, scouting, handoffs, code maps, safe checks, and gated operator actions. "
            "Projects: quantule_mapper, knowledge_compiler_engine, mark_platform, network_management. "
            "Do not use code_helper or dev_agent for these existing projects unless the user asks for direct coding."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "project_id": {
                    "type": "STRING",
                    "description": "Registered project id, or empty with operation=list to list projects"
                },
                "operation": {
                    "type": "STRING",
                    "description": "list | status | scout | code_map | handoff | delegate_openclaw | verify_rf_backend | launch | stop | heavy_training"
                },
                "intent": {
                    "type": "STRING",
                    "description": "Natural language reason for the operation"
                },
                "command": {
                    "type": "STRING",
                    "description": "Optional exact command requested by the user"
                },
                "confirmation_id": {
                    "type": "STRING",
                    "description": "Confirmation token/id when retrying a gated operation"
                },
                "agent_preference": {
                    "type": "STRING",
                    "description": "Optional preferred helper: claude | codex | openclaw"
                }
            },
            "required": ["operation"]
        }
    },
    {
        "name": "jarvis_memory",
        "description": (
            "Manages JARVIS vault-first memory through the Jarvis_notes Obsidian vault and Mark-native "
            "local RAG index. Use for remember-this requests, memory notes, reports, deep research reports, "
            "logs, progress trackers, memory search, local reindexing, graph views, task extraction, and DAG "
            "candidate export. Remember Me is optional and disabled by default."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "operation": {
                    "type": "STRING",
                    "description": "health | create_note | sync_pending | query | reindex | reindex_local | query_local | graph | tasks | dag_candidates | export_training_candidates | list_templates"
                },
                "note_type": {
                    "type": "STRING",
                    "description": "memory | report | deep_research_report | log | progress_tracker"
                },
                "title": {"type": "STRING", "description": "Title for a generated vault note"},
                "content": {"type": "STRING", "description": "Markdown body or fact to persist"},
                "query": {"type": "STRING", "description": "Question or topic to search in RAG memory"},
                "tags": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Obsidian tags for the note"
                },
                "scope": {"type": "STRING", "description": "project | global for query"},
                "limit": {"type": "INTEGER", "description": "Maximum notes/results to process"}
            },
            "required": ["operation"]
        }
    },
    {
        "name": "capability_registry",
        "description": (
            "MCP-style registry of JARVIS tools and capabilities. Use when the user asks what JARVIS "
            "can do, whether web/news/reminders/speech/files/projects are available, asks for tool help, "
            "or wants a manifest of available tools. This describes capabilities; execution still goes "
            "through the normal tool router."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "operation": {
                    "type": "STRING",
                    "description": "list | search | describe | help | manifest | health | mcp"
                },
                "query": {"type": "STRING", "description": "Capability search query"},
                "tool_name": {"type": "STRING", "description": "Specific tool/capability name for help"},
                "method": {"type": "STRING", "description": "MCP-style method: tools/list | tools/get | tools/search | tools/call | capabilities/health"},
                "params": {"type": "OBJECT", "description": "Method parameters for mcp operation"},
                "limit": {"type": "INTEGER", "description": "Maximum search results"}
            },
            "required": ["operation"]
        }
    },
    {
        "name": "model_lifecycle",
        "description": (
            "Manages LM Studio loaded model lifecycle for JARVIS. Use for model status, loaded model counts, "
            "baseline warm models, idle cleanup, and unloading non-baseline task models. It treats LM Studio "
            "parallel slots as instance configuration, not separate loaded models."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "operation": {
                    "type": "STRING",
                    "description": "health | status | baseline | cleanup_idle | unload_non_baseline | loaded_models"
                },
                "force": {
                    "type": "BOOLEAN",
                    "description": "Only for manual unload_non_baseline; bypasses active-request guard when true."
                }
            },
            "required": ["operation"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use browser_control or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]


def _chat_json_schema(value):
    if isinstance(value, list):
        return [_chat_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    converted = {}
    for key, item in value.items():
        if key == "type" and isinstance(item, str):
            converted[key] = item.lower()
        else:
            converted[key] = _chat_json_schema(item)
    return converted


def _router_tool_names_for_text(text: str) -> list[str] | None:
    lowered = (text or "").lower()
    rules = [
        (("lm studio", "lmstudio", "loaded model", "loaded models", "model lifecycle", "cleanup model", "cleanup models", "unload model", "unload models", "task model", "baseline model", "idle cleanup"), ["model_lifecycle"]),
        (("what can you do", "what are your tools", "what tools", "available tools", "tool help", "capability", "capabilities", "can you ", "are you able", "do you have", "speech to text", "text to speech", "tts", "stt", "microphone"), ["capability_registry"]),
        (("system", "status", "cpu", "memory", "ram", "gpu", "temperature", "uptime", "performance"), ["system_status"]),
        (("remember", "memory", "memories", "note", "notes", "vault", "obsidian", "report", "research report", "deep research", "progress tracker", "search your memory", "what do you know", "memory graph", "tasks in memory", "dag candidate"), ["jarvis_memory"]),
        (("project", "repo", "repository", "quantule", "knowledge compiler", "network management", "mark platform", "aletheia", "scout", "code map", "handoff", "openclaw", "clawteam", "delegate", "continuity worker"), ["project_operator"]),
        (("search", "web", "latest", "news", "price", "compare", "current"), ["web_search"]),
        (("weather", "forecast"), ["weather_report"]),
        (("open ", "launch ", "start app", "run app"), ["open_app"]),
        (("browser", "website", "url", "click", "page", "tab"), ["browser_control"]),
        (("file", "folder", "directory", "read", "write", "copy", "move", "rename", "delete"), ["file_controller"]),
        (("screen", "camera", "see", "look at", "visual", "image"), ["screen_process", "close_camera"]),
        (("volume", "brightness", "window", "type", "keyboard", "mouse", "hotkey", "scroll"), ["computer_settings", "computer_control"]),
        (("code", "implement", "debug", "bug", "test", "build", "refactor"), ["code_helper", "dev_agent", "project_operator"]),
        (("youtube", "video"), ["youtube_video"]),
        (("message", "whatsapp", "telegram", "send "), ["send_message"]),
        (("remind", "reminder"), ["reminder"]),
        (("game", "steam", "epic"), ["game_updater"]),
        (("flight", "flights", "airport"), ["flight_finder"]),
        (("upload", "uploaded", "document", "pdf", "csv", "excel", "audio", "archive"), ["file_processor"]),
    ]
    selected: list[str] = []
    for tokens, names in rules:
        if any(token in lowered for token in tokens):
            selected.extend(names)
    if not selected:
        return None
    seen = set()
    return [name for name in selected if not (name in seen or seen.add(name))]


def _router_tool_schema(text: str | None = None) -> list[dict]:
    names = _router_tool_names_for_text(text or "")
    tools = []
    for declaration in TOOL_DECLARATIONS:
        if names is not None and declaration["name"] not in names:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": declaration["name"],
                    "description": declaration.get("description", ""),
                    "parameters": _chat_json_schema(
                        declaration.get("parameters") or {"type": "object", "properties": {}}
                    ),
                },
            }
        )
    return tools


def _select_input_device(
    sd_module,
    device=None,
    device_name: str = "",
    samplerate: int = 16000,
    channels: int = 1,
    dtype: str = "int16",
):
    if device not in (None, ""):
        try:
            return int(device)
        except (TypeError, ValueError):
            return device
    name = (device_name or "").strip().lower()
    if not name:
        return None
    try:
        devices = list(sd_module.query_devices())
        hostapis = list(sd_module.query_hostapis())
    except Exception:
        return None
    candidates = []
    for idx, info in enumerate(devices):
        if not info.get("max_input_channels", 0):
            continue
        if name not in str(info.get("name", "")).lower():
            continue
        hostapi_name = ""
        try:
            hostapi_name = str(hostapis[info.get("hostapi", 0)].get("name", "")).lower()
        except Exception:
            pass
        priority = 50
        if "wasapi" in hostapi_name:
            priority = 0
        elif "directsound" in hostapi_name:
            priority = 10
        elif "wdm-ks" in hostapi_name:
            priority = 20
        elif "mme" in hostapi_name:
            priority = 30
        if "mapper" in str(info.get("name", "")).lower():
            priority += 40
        try:
            sd_module.check_input_settings(
                device=idx,
                samplerate=samplerate,
                channels=channels,
                dtype=dtype,
            )
        except Exception:
            priority += 100
        candidates.append((priority, idx))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


class _RouterFunctionCall:
    def __init__(self, call_id: str, name: str, args: dict):
        self.id = call_id
        self.name = name
        self.args = args or {}


# --- Plugin system ---


class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session              = None
        self.audio_in_queue       = None
        self.out_queue            = None
        self._loop                = None
        self._is_speaking         = False
        self._speaking_lock       = threading.Lock()
        self._phone_active        = False   # True while phone mic is streaming; pauses PC mic
        self._pending_vision       = None    # (img_bytes, mime_type, question, angle) to inject after tool response
        self._vision_cam_active    = False   # True if camera was opened for vision → auto-close after response
        self._vision_close_pending = False   # True after vision injected; next turn_complete closes camera
        self._vision_last_time     = 0.0     # monotonic time of last screen_process call (cooldown guard)
        self._vision_busy          = False   # True while a vision capture/inject cycle is in flight
        self._interrupted          = False   # True while draining audio after user interrupt
        self.ui.on_text_command   = self._on_text_command
        self.ui.on_remote_clicked = self._make_remote_key
        self.ui.on_interrupt      = self.interrupt
        self.ui.on_mute_changed   = self._on_mute_changed
        self._turn_done_event: asyncio.Event | None = None
        self._dashboard     = None
        self._briefing_sent    = False          # morning briefing fires once per process
        self._sys_monitor      = SystemMonitor()  # persistent cooldown state
        self._proactive        = ProactiveEngine()
        self._last_user_speech = time.monotonic()  # updated on every user utterance
        self._local_tts        = None
        self._local_stt        = None
        self._router_stt_lock   = threading.Lock()
        self._router_stt_partial = ""
        self._stt_quiet_warned = False
        self._last_voice_text   = ""
        self._last_voice_time   = 0.0
        self._last_voice_filler_time = 0.0
        self._voice_input_block_until = 0.0
        self._router_turn_lock = threading.Lock()

    def _make_remote_key(self):
        """Called from Qt main thread when user presses Remote Control."""
        if self._dashboard is None:
            self.ui.write_log(
                "SYS: Dashboard unavailable. "
                "Run: pip install fastapi \"uvicorn[standard]\" cryptography"
            )
            return None
        key    = self._dashboard.new_key()
        url    = self._dashboard.get_url()
        manual = self._dashboard.get_manual_url()
        return url, key, f"{url}/auto-login?key={key}", manual

    def _on_text_command(self, text: str):
        if self._loop and self.session:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                self._loop
            )
            return
        threading.Thread(target=self._handle_router_text_command, args=(text,), daemon=True).start()

    def _submit_router_voice_transcript(self, text: str):
        text = _clean_transcript(text)
        if len(text) < 2:
            return
        now = time.monotonic()
        if self._voice_input_blocked(now):
            print(f"[JARVIS] Ignored voice transcript during speech guard: {text!r}")
            self._reset_router_stt()
            return
        if _is_noise_voice_transcript(text):
            elapsed = now - getattr(self, "_last_voice_filler_time", 0.0)
            if elapsed < self._voice_filler_cooldown_seconds():
                print(f"[JARVIS] Ignored rate-limited STT filler transcript: {text!r}")
                return
            self._last_voice_filler_time = now
        if text == self._last_voice_text and now - self._last_voice_time < 2.0:
            return
        self._last_voice_text = text
        self._last_voice_time = now
        self._last_user_speech = now
        self.ui.write_log(f"YOU (voice): {text}")
        threading.Thread(target=self._handle_router_text_command, args=(text,), daemon=True).start()

    def _reset_router_stt(self) -> None:
        stt = getattr(self, "_local_stt", None)
        lock = getattr(self, "_router_stt_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._router_stt_lock = lock
        with lock:
            self._router_stt_partial = ""
            if stt is not None and hasattr(stt, "reset"):
                stt.reset()

    def _flush_router_stt_turn(self) -> None:
        stt = getattr(self, "_local_stt", None)
        lock = getattr(self, "_router_stt_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._router_stt_lock = lock
        text = ""
        with lock:
            if stt is not None and hasattr(stt, "final_result"):
                try:
                    text = stt.final_result()
                except Exception as exc:
                    self.ui.write_log(f"STT: Could not finalize muted turn - {str(exc)[:120]}")
            if not text:
                text = getattr(self, "_router_stt_partial", "")
            self._router_stt_partial = ""
            if stt is not None and hasattr(stt, "reset"):
                stt.reset()
        if text:
            self._submit_router_voice_transcript(text)

    def _on_mute_changed(self, muted: bool) -> None:
        if muted:
            self._flush_router_stt_turn()
            return
        self._reset_router_stt()
        with self._speaking_lock:
            speaking = self._is_speaking
        if not speaking:
            self.ui.set_state("LISTENING")

    def _router_turn_mutex(self) -> threading.Lock:
        lock = getattr(self, "_router_turn_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._router_turn_lock = lock
        return lock

    def _voice_guard_seconds(self) -> float:
        try:
            cfg = _load_runtime_config()
            return max(0.0, float(cfg.get("stt_after_tts_cooldown_seconds", 1.0)))
        except Exception:
            return 1.0

    def _voice_filler_cooldown_seconds(self) -> float:
        try:
            cfg = _load_runtime_config()
            return max(0.0, float(cfg.get("stt_filler_cooldown_seconds", 300.0)))
        except Exception:
            return 300.0

    def _set_voice_input_cooldown(self, seconds: float | None = None) -> None:
        seconds = self._voice_guard_seconds() if seconds is None else max(0.0, float(seconds))
        until = time.monotonic() + seconds
        self._voice_input_block_until = max(getattr(self, "_voice_input_block_until", 0.0), until)

    def _voice_input_blocked(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        lock = getattr(self, "_speaking_lock", None)
        if lock is None:
            speaking = bool(getattr(self, "_is_speaking", False))
        else:
            with lock:
                speaking = bool(getattr(self, "_is_speaking", False))
        return speaking or now < getattr(self, "_voice_input_block_until", 0.0)

    def _router_system_prompt(self) -> str:
        memory = load_memory()
        mem_str = format_memory_for_prompt(memory)
        parts = [
            "[ROUTER MODE]\n"
            "You are JARVIS, the assistant running on the MARK XLVIII local platform. "
            "MARK XLVIII is the shell/platform name, not your assistant name. "
            "Router mode supports local STT/TTS, tools, reminders, web/news search, files, browser control, "
            "system status, project operations, and vault memory without Gemini Live. "
            "Gemini Live is optional for realtime live-model sessions only; do not imply it is required for speech or tools."
        ]
        if mem_str:
            parts.append(mem_str)
        parts.append(_load_system_prompt())
        return "\n\n".join(parts)

    def _router_tool_system_prompt(self) -> str:
        return (
            "You are JARVIS's tool router for the MARK XLVIII local platform. Decide whether the user's "
            "request needs one of the provided tools. Prefer tools for capability questions, current "
            "system status, project operations, files, browser/computer control, web search/news, reminders, "
            "weather, vault memory, and app launch requests. "
            "If no tool is needed, answer briefly."
        )

    def _handle_router_text_command(self, text: str):
        with self._router_turn_mutex():
            text = (text or "").strip()
            if not text:
                return
            self.ui.set_state("THINKING")
            try:
                try:
                    routed = call_with_tools(
                        text,
                        role="planner",
                        system=self._router_tool_system_prompt(),
                        tools=_router_tool_schema(text),
                        timeout=120,
                    )
                    if routed.tool_calls:
                        tool_results = []
                        for call in routed.tool_calls[:5]:
                            self.ui.write_log(f"TOOL: {call.name}")
                            result = self._execute_router_tool_call(call.id, call.name, call.arguments)
                            tool_results.append(
                                {
                                    "tool": call.name,
                                    "arguments": call.arguments,
                                    "result": str(result)[:4000],
                                }
                            )
                        summary_prompt = (
                            "The user asked:\n"
                            f"{text}\n\n"
                            "Tool results:\n"
                            f"{json.dumps(tool_results, indent=2)}\n\n"
                            "Answer the user concisely. Mention confirmation gates, blocked actions, "
                            "or failed tools only when they are actually present in the tool results."
                        )
                        reply = call_text(
                            summary_prompt,
                            role="worker",
                            system=self._router_system_prompt(),
                            timeout=120,
                        )
                    else:
                        reply = routed.text
                except Exception as planner_error:
                    print(f"[Router] Planner/tool route failed, falling back to worker text: {planner_error}")
                    reply = call_text(text, role="worker", system=self._router_system_prompt(), timeout=120)
                reply = (reply or "").strip()
                if not reply:
                    reply = "Router mode is active, but the model returned no text."
                self.ui.write_log(f"JARVIS: {reply[:500]}")
                self.ui.show_content("ROUTER MODE", reply)
                self.speak(reply)
            except Exception as exc:
                self.ui.write_log(f"ERR: Router model unavailable - {str(exc)[:180]}")
            finally:
                if not self.ui.muted and not self._voice_input_blocked():
                    self.ui.set_state("LISTENING")

    def _execute_router_tool_call(self, call_id: str, name: str, args: dict) -> str:
        fc = _RouterFunctionCall(call_id, name, args)
        response = asyncio.run(self._execute_tool(fc))
        payload = getattr(response, "response", {}) or {}
        if isinstance(payload, dict):
            return str(payload.get("result", payload))
        return str(payload)

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self._set_voice_input_cooldown(0.25)
            self._reset_router_stt()
            self.ui.set_state("SPEAKING")
            return
        self._reset_router_stt()
        self._set_voice_input_cooldown()
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

    def interrupt(self) -> None:
        """Stop JARVIS mid-speech: drain queued audio and open mic immediately."""
        self._interrupted = True
        q = self.audio_in_queue
        if q:
            drained = 0
            while True:
                try:
                    q.get_nowait()
                    drained += 1
                except Exception:
                    break
            if drained:
                print(f"[JARVIS] Interrupted - {drained} audio chunks discarded")
        self.set_speaking(False)
        self._voice_input_block_until = 0.0
        if self._turn_done_event:
            self._turn_done_event.clear()
        self.ui.write_log("SYS: Interrupted — listening...")

    def speak(self, text: str):
        if not self._loop or not self.session:
            local_tts = getattr(self, "_local_tts", None) or self._get_local_tts()
            if local_tts:
                local_tts.speak(
                    text,
                    on_start=lambda: self.set_speaking(True),
                    on_done=lambda: self.set_speaking(False),
                )
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def _get_local_tts(self):
        cfg = _load_runtime_config()
        if not cfg.get("voice_enabled", True):
            return None
        try:
            from core.tts import create_tts_player

            self._local_tts = create_tts_player(cfg)
            return self._local_tts
        except Exception as exc:
            self.ui.write_log(f"TTS: Local speech unavailable - {str(exc)[:160]}")
            return None

    def _get_local_stt(self):
        cfg = _load_runtime_config()
        if not cfg.get("voice_enabled", True):
            return None
        engine = str(cfg.get("stt_engine", "vosk")).strip().lower()
        if engine != "vosk":
            self.ui.write_log(f"STT: Live router microphone supports Vosk for now, not {engine}.")
            return None
        try:
            from core.stt import VoskSTT

            self._local_stt = VoskSTT(
                model_path=cfg.get("stt_model_path") or None,
                language=cfg.get("stt_language", "en-us"),
            )
            return self._local_stt
        except Exception as exc:
            self.ui.write_log(f"STT: Local speech recognition unavailable - {str(exc)[:160]}")
            return None

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] TOOL {name} {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                import time as _t_mod
                _now = _t_mod.monotonic()
                _cooldown = 4.0  # seconds — covers echo window after speaking ends
                if self._vision_busy or (_now - self._vision_last_time) < _cooldown:
                    _wait = max(0, _cooldown - (_now - self._vision_last_time))
                    print(f"[Vision] ⏳ Cooldown active ({_wait:.1f}s remaining) — ignoring duplicate call")
                    result = "Vision is still processing the previous request. I will not call this again."
                else:
                    self._vision_busy      = True
                    self._vision_last_time = _now
                    angle     = args.get("angle", "screen").lower()
                    user_text = args.get("text", "What do you see?")
                    if angle == "camera":
                        img_b, mime_t = await loop.run_in_executor(None, _capture_camera)
                        self.ui.start_camera_stream()
                        self._vision_cam_active = True
                        print(f"[Vision] 📷 Camera: {len(img_b):,} bytes")
                        _stall = "camera"
                    else:
                        img_b, mime_t = await loop.run_in_executor(None, _capture_screen)
                        print(f"[Vision] 🖥️  Screen: {len(img_b):,} bytes")
                        _stall = "screen"
                    self._pending_vision = (img_b, mime_t, user_text, angle)
                    result = (
                        f"[VISION_ACTIVE] {_stall.capitalize()} captured. "
                        f"Immediately say ONE natural sentence in the user's language "
                        f"(e.g. 'Looking at your {_stall} now, sir' / "
                        f"'{'Kameraya' if _stall == 'camera' else 'Ekrana'} bakıyorum efendim'). "
                        f"Do NOT describe or guess content — the actual image arrives in the NEXT message."
                    )

            elif name == "close_camera":
                self.ui.stop_camera_stream()
                result = "Camera closed."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "project_operator":
                r = await loop.run_in_executor(None, lambda: project_operator(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "jarvis_memory":
                r = await loop.run_in_executor(None, lambda: jarvis_memory(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "capability_registry":
                r = await loop.run_in_executor(
                    None,
                    lambda: capability_registry(
                        parameters=args,
                        player=self.ui,
                        speak=self.speak,
                        declarations=TOOL_DECLARATIONS,
                        config=_load_runtime_config(),
                    ),
                )
                result = r or "Done."

            elif name == "model_lifecycle":
                r = await loop.run_in_executor(
                    None,
                    lambda: model_lifecycle(parameters=args, player=self.ui, speak=self.speak),
                )
                result = r or "Done."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
                # Mirror results to the on-screen content panel
                _mode = args.get("mode", "search")
                if r and not r.startswith("No results") and not r.startswith("Search failed"):
                    _query = args.get("query") or ", ".join(args.get("items", []))
                    _label = f"{_mode.upper()} — {_query[:38]}" if _query else _mode.upper()
                    self.ui.show_content(_label, r)
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_status":
                r = await loop.run_in_executor(None, get_system_status)
                result = str(r)

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] TOOL_RESULT {name} -> {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted and not self._phone_active:
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] Mic error: {e}")
            raise

    async def _listen_router_stt(self):
        """Keep local router-mode mic input alive across device timeouts."""
        if sd is None:
            self.ui.write_log("STT: sounddevice unavailable; microphone input disabled.")
            return
        backoff = 1.0
        while True:
            try:
                await self._listen_router_stt_once()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                message = str(exc)[:160] or type(exc).__name__
                self.ui.write_log(f"STT: Microphone stream interrupted - {message}. Retrying in {backoff:.0f}s.")
                print(f"[JARVIS] Router STT mic restart after error: {exc}")
                try:
                    self._reset_router_stt()
                except Exception:
                    self._local_stt = None
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15.0)

    async def _listen_router_stt_once(self):
        """Local router-mode mic loop: PC mic -> Vosk -> router text command."""
        stt = getattr(self, "_local_stt", None)
        if stt is None:
            stt = await asyncio.to_thread(self._get_local_stt)
        if stt is None:
            return

        cfg = _load_runtime_config()
        device_name = str(cfg.get("stt_device_name") or "").strip()
        samplerate = 16000
        device = _select_input_device(sd, cfg.get("stt_device"), device_name, samplerate=samplerate)
        blocksize = 4000
        quiet_rms_threshold = int(cfg.get("stt_quiet_rms_threshold", 300))
        idle_restart_seconds = float(cfg.get("stt_idle_restart_seconds", 18))
        audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=24)
        loop = asyncio.get_event_loop()
        last_audio_health = 0.0
        last_callback_status = ""

        def enqueue_audio(data: bytes):
            try:
                audio_q.put_nowait(data)
            except asyncio.QueueFull:
                pass

        def callback(indata, frames, time_info, status):
            nonlocal last_callback_status
            if status:
                status_text = str(status)
                if status_text != last_callback_status:
                    last_callback_status = status_text
                    print(f"[JARVIS] STT input status: {status_text}")
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if jarvis_speaking or self.ui.muted or self._phone_active:
                return
            loop.call_soon_threadsafe(enqueue_audio, indata.tobytes())

        try:
            stream_kwargs = {
                "samplerate": samplerate,
                "channels": 1,
                "dtype": "int16",
                "blocksize": blocksize,
                "callback": callback,
            }
            if device not in (None, ""):
                stream_kwargs["device"] = device
            with sd.InputStream(**stream_kwargs):
                try:
                    active_device = sd.query_devices(device, "input") if device not in (None, "") else sd.query_devices(kind="input")
                    active_name = active_device.get("name", "default input")
                except Exception:
                    active_name = str(device or "default input")
                self.ui.write_log(f"STT: Local Vosk microphone online ({active_name}).")
                print(f"[JARVIS] Router STT mic stream open on {active_name}")
                while True:
                    try:
                        chunk = await asyncio.wait_for(audio_q.get(), timeout=idle_restart_seconds)
                    except asyncio.TimeoutError:
                        if self.ui.muted or self._phone_active:
                            continue
                        with self._speaking_lock:
                            jarvis_speaking = self._is_speaking
                        if jarvis_speaking:
                            continue
                        raise TimeoutError(f"no microphone audio callbacks for {idle_restart_seconds:.0f}s")
                    now = time.monotonic()
                    if now - last_audio_health > 6.0:
                        last_audio_health = now
                        try:
                            rms = audioop.rms(chunk, 2)
                        except Exception:
                            rms = 0
                        if rms < quiet_rms_threshold and not getattr(self, "_stt_quiet_warned", False):
                            self._stt_quiet_warned = True
                            self.ui.write_log(
                                f"STT: Input is very quiet (rms {rms}). Check headset mute/input level."
                            )
                    try:
                        def process_locked(data):
                            with self._router_stt_lock:
                                return stt.process_chunk(data)

                        text, is_final = await asyncio.to_thread(process_locked, chunk)
                    except Exception as exc:
                        self.ui.write_log(f"STT: Recognition error - {str(exc)[:160]}")
                        await asyncio.sleep(1)
                        continue
                    if is_final and text:
                        with self._router_stt_lock:
                            self._router_stt_partial = ""
                        self._submit_router_voice_transcript(text)
                    elif text:
                        with self._router_stt_lock:
                            self._router_stt_partial = text
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.ui.write_log(f"STT: Microphone stream unavailable - {str(exc)[:160]}")
            print(f"[JARVIS] Router STT mic error: {exc}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._interrupted:
                            pass  # discard: interrupted
                        else:
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            # Split into ~50 ms chunks so interrupt() stops audio within 50 ms
                            # (24000 Hz × 2 bytes/sample × 0.05 s = 2400 bytes per slice)
                            _audio_data = response.data
                            _SLICE = 2400
                            for _i in range(0, len(_audio_data), _SLICE):
                                self.audio_in_queue.put_nowait(_audio_data[_i : _i + _SLICE])

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt and txt != (out_buf[-1] if out_buf else ""):
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                self._last_user_speech = time.monotonic()

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            # If this turn_complete ends an interrupted response, clear the
                            # flag and skip all further processing for that turn.
                            if self._interrupted:
                                self._interrupted = False
                                in_buf  = []
                                out_buf = []
                                continue

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "user",
                                        "text": full_in,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "jarvis",
                                        "text": full_out,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            out_buf = []

                            # Vision injection: model finished tool-response turn → now send the image
                            if self._pending_vision and self.session:
                                import base64 as _b64
                                img_b, mime_t, question, angle = self._pending_vision
                                self._pending_vision = None
                                b64 = _b64.b64encode(img_b).decode("ascii")
                                print(f"[Vision] 📤 {len(img_b):,} bytes (angle={angle}) → main session")
                                await self.session.send_client_content(
                                    turns={"parts": [
                                        {"inline_data": {"mime_type": mime_t, "data": b64}},
                                        {"text": question},
                                    ]},
                                    turn_complete=True,
                                )
                                # Mark next turn_complete behaviour depending on angle
                                if self._vision_cam_active:
                                    # Camera: keep busy until JARVIS finishes speaking the answer
                                    self._vision_cam_active    = False
                                    self._vision_close_pending = True
                                else:
                                    # Screen-only: no camera to close; release busy flag now
                                    self._vision_busy = False
                            elif self._vision_close_pending:
                                # This turn_complete IS the vision answer — close camera + release busy flag
                                self._vision_close_pending = False
                                self._vision_busy = False
                                async def _cam_close():
                                    await asyncio.sleep(2.0)
                                    self.ui.stop_camera_stream()
                                asyncio.create_task(_cam_close())

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] TOOL_CALL {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[JARVIS] Recv error: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                try:
                    await asyncio.to_thread(stream.write, chunk)
                except (RuntimeError, asyncio.CancelledError):
                    break   # executor shutting down — exit cleanly
        except Exception as e:
            print(f"[JARVIS] Play error: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    # ── Morning briefing ────────────────────────────────────────────────────────

    async def _send_startup_briefing(self) -> None:
        """
        Two-phase briefing for instant perceived response:
          Phase 1 — immediate greeting (no tools, no fetch) → Jarvis speaks in <2s
          Phase 2 — news fetched in background, injected after greeting finishes
        """
        await asyncio.sleep(0.3)
        if not self.session:
            return

        # ── memory ───────────────────────────────────────────────────────────
        memory   = load_memory()
        identity = memory.get("identity", {})

        def _val(k: str) -> str:
            e = identity.get(k, {})
            return (e.get("value", "") if isinstance(e, dict) else str(e)).strip()

        lang = _val("language")
        name = _val("name")

        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M")

        # ── Phase 1: instant greeting — one simple sentence ──────────────────
        lang_clause = f" Respond in {lang}." if lang else ""
        name_clause = f" Address the user as {name}." if name else ""
        p1 = (
            f"Greet the user, mention it is {time_str}, and say you are fetching today's news headlines now. "
            f"One short sentence only. Do not call any tools.{lang_clause}{name_clause}"
        )

        await self.session.send_client_content(
            turns={"parts": [{"text": p1}]},
            turn_complete=True,
        )
        self.ui.write_log("SYS: Briefing phase 1 (greeting) sent.")

        # ── Phase 2: fetch news in background, deliver after greeting plays ───
        async def _guarded_news():
            try:
                await self._briefing_news_phase(lang)
            except Exception as e:
                print(f"[Briefing] Phase 2 error: {e}")
                self.ui.write_log(f"SYS: Briefing news phase failed: {e}")
        asyncio.create_task(_guarded_news())

    async def _briefing_news_phase(self, lang: str) -> None:
        """
        Sends phase-2 (news) to Gemini ~1.5 s after phase-1 is dispatched so
        Gemini starts working on it while phase-1 audio is still playing.
        """
        lang_str = f" Respond in {lang}." if lang else ""

        # 1.5 s is enough for Gemini to finish generating phase-1 audio on its
        # side (turn_complete) while the greeting is still being played locally.
        await asyncio.sleep(1.5)

        if not self.session:
            return

        p2 = (
            "[BRIEFING] Call web_search with mode='news' and query='top world news today' "
            "to find actual recent news articles with real event headlines (not just website names). "
            "After the search, say ONE specific news event from the results in one sentence, "
            f"then say the full list is displayed on screen.{lang_str}"
        )

        await self.session.send_client_content(
            turns={"parts": [{"text": p2}]},
            turn_complete=True,
        )
        self.ui.write_log("SYS: Briefing phase 2 (news) sent.")

    # ── System monitor ──────────────────────────────────────────────────────────

    async def _run_system_monitor(self) -> None:
        """Background task: voice alerts when metrics exceed thresholds."""
        while True:
            await asyncio.sleep(10)
            alert = await asyncio.to_thread(self._sys_monitor.check)
            if alert and self.session:
                try:
                    await self.session.send_client_content(
                        turns={"parts": [{"text": alert}]},
                        turn_complete=True,
                    )
                except Exception as e:
                    print(f"[Monitor] ⚠️ Could not send alert: {e}")

    # ── Proactive mode ──────────────────────────────────────────────────────────

    async def _run_proactive_mode(self) -> None:
        """
        Background task: periodically checks if the user has been silent long enough,
        then hands time + memory context to Gemini so it can decide what (if anything)
        to say proactively. No hardcoded rules — Gemini makes the call.
        """
        while True:
            await asyncio.sleep(60)   # evaluate once per minute

            if not self.session:
                continue

            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue

            if not self._proactive.should_trigger(self._last_user_speech):
                continue

            self._proactive.mark_triggered()

            try:
                memory = await asyncio.to_thread(load_memory)
                prompt = self._proactive.build_prompt(memory)
                await self.session.send_client_content(
                    turns={"parts": [{"text": prompt}]},
                    turn_complete=True,
                )
                self.ui.write_log("SYS: Proactive check-in.")
            except Exception as e:
                print(f"[Proactive] ⚠️ {e}")

    # ── Phone audio relay ────────────────────────────────────────────────────────

    async def _run_model_lifecycle_cleanup(self) -> None:
        """Periodically release non-baseline LM Studio models when Mark is idle."""
        while True:
            try:
                cfg = resolve_model_lifecycle_config()
                interval = max(30, int(cfg.get("idle_cleanup_seconds", 300)))
                await asyncio.sleep(interval)
                result = await asyncio.to_thread(cleanup_idle_models)
                unloaded = result.get("unloaded") if isinstance(result, dict) else None
                if unloaded:
                    names = ", ".join(
                        str(item.get("model_key") or item.get("instance_id"))
                        for item in unloaded
                        if isinstance(item, dict)
                    )
                    if names:
                        self.ui.write_log(f"LMSTUDIO: unloaded idle task model(s): {names}")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[LMStudio] Cleanup error: {e}")
                await asyncio.sleep(60)

    async def _relay_phone_audio(self) -> None:
        """Forward phone mic PCM chunks from dashboard queue into the Gemini Live session."""
        q = self._dashboard._phone_audio_queue
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No audio for 1 s → phone mic inactive, give PC mic back
                self._phone_active = False
                continue
            self._phone_active = True   # phone is streaming — silence PC mic
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and not self.ui.muted:
                try:
                    self.out_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass

    def _on_phone_connected(self) -> None:
        self.ui.write_log("SYS: Phone connected via Remote Dashboard.")
        self.ui.notify_phone_connected()

    # ── dashboard command relay ─────────────────────────────────────────────

    async def _process_dashboard_commands(self) -> None:
        while True:
            try:
                text = await asyncio.wait_for(
                    self._dashboard._command_queue.get(), timeout=0.5
                )
                if not text:
                    continue
                # Wait up to 8s for session to become ready after a wake
                for _ in range(80):
                    if self.session:
                        break
                    await asyncio.sleep(0.1)
                if self.session:
                    await self.session.send_client_content(
                        turns={"parts": [{"text": text}]},
                        turn_complete=True,
                    )
                    self.ui.write_log(f"[Web]: {text}")
                else:
                    self.ui.write_log(f"[Web]: {text}")
                    await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self._handle_router_text_command(text)
                    )
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"[Dashboard] Command error: {e}")
                await asyncio.sleep(0.5)

    async def _run_router_mode(self):
        print("[JARVIS] Router mode active. Gemini Live disabled/unavailable.")
        self.session = None
        self.ui.set_state("LISTENING")
        self.ui.write_log("SYS: Router mode online. Gemini Live is not required.")
        if self._dashboard:
            await self._dashboard.broadcast({"type": "status", "state": "active"})
        asyncio.create_task(self._listen_router_stt())
        while True:
            await asyncio.sleep(3600)

    # ── main loop ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()

        # Start dashboard (optional — needs: pip install fastapi "uvicorn[standard]" cryptography)
        try:
            from dashboard.server import DashboardServer
            self._dashboard = DashboardServer()
            self._dashboard.set_connect_callback(self._on_phone_connected)
            asyncio.create_task(self._dashboard.serve())
            # Runs for the whole lifetime, not just inside an active session
            asyncio.create_task(self._process_dashboard_commands())
        except Exception as e:
            print(f"[Dashboard] Disabled: {e}")
            self._dashboard = None

        asyncio.create_task(self._run_model_lifecycle_cleanup())

        if not _gemini_live_enabled():
            await self._run_router_mode()
            return

        while True:
            switch_to_router = False
            try:
                print("[JARVIS] Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                # Fresh client on every reconnect — avoids stale HTTP session state
                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1beta"}
                )

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()

                    # Reset transient state that must not carry over from a previous session
                    self._pending_vision       = None
                    self._vision_cam_active    = False
                    self._vision_close_pending = False
                    self._vision_busy          = False
                    self._vision_last_time     = 0.0
                    self._interrupted          = False

                    print("[JARVIS] Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")

                    if self._dashboard:
                        await self._dashboard.broadcast({"type": "status", "state": "active"})

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._run_system_monitor())
                    tg.create_task(self._run_proactive_mode())
                    if self._dashboard:
                        tg.create_task(self._relay_phone_audio())

                    # Morning briefing — fires once per process launch
                    if not self._briefing_sent:
                        self._briefing_sent = True
                        tg.create_task(self._send_startup_briefing())

            except KeyboardInterrupt:
                raise
            except SystemExit:
                raise
            except BaseException as e:
                # Catches both Exception and BaseExceptionGroup (Python 3.11+
                # TaskGroup raises BaseExceptionGroup when tasks are cancelled
                # externally, which `except Exception` would miss, letting the
                # exception escape the while-loop and causing asyncio.run() to
                # start shutdown — resulting in "executor after shutdown" errors).
                err_str = str(e)
                print(f"[JARVIS] Error ({type(e).__name__}): {e}")
                traceback.print_exc()

                if _is_nonretryable_gemini_error(err_str):
                    self.ui.write_log("GEMINI: Live unavailable - switching to router mode.")
                    switch_to_router = True
                    err_str = ""

                # Invalid API key — stop hammering the API, prompt re-configuration
                if "API key not valid" in err_str or "1007" in err_str:
                    self.ui.write_log("ERR: API key invalid — please re-enter your key.")
                    self.ui.set_state("SLEEPING")
                    self.ui.prompt_reconfig()
                    while not self.ui._win._ready:
                        await asyncio.sleep(1)
                    print("[JARVIS] New API key saved — reconnecting...")
                    _conn_backoff = 3
                    continue

                # Network / timeout errors — log clearly and back off
                is_net_err = any(k in err_str for k in (
                    "TimeoutError", "timed out", "getaddrinfo", "CancelledError",
                    "ConnectionRefusedError", "OSError", "Cannot connect",
                ))
                if is_net_err:
                    _conn_backoff = min(getattr(self, "_conn_backoff", 3) * 2, 60)
                    self._conn_backoff = _conn_backoff
                    self.ui.write_log(
                        f"NET: Bağlantı kurulamadı — {_conn_backoff}s sonra tekrar deneniyor. "
                        "(VPN gerekiyor olabilir)"
                    )
                else:
                    self._conn_backoff = 3
            finally:
                self.session = None

            if switch_to_router:
                await self._run_router_mode()
                return

            self.set_speaking(False)
            self.ui.set_state("SLEEPING")

            if self._dashboard:
                await self._dashboard.broadcast({"type": "status", "state": "sleeping"})

            delay = getattr(self, "_conn_backoff", 3)
            print(f"[JARVIS] Reconnecting in {delay}s...")
            await asyncio.sleep(delay)

def main():
    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
