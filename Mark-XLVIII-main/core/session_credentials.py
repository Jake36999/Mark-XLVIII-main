from __future__ import annotations

import atexit
import multiprocessing as mp
import threading
import uuid
from dataclasses import dataclass
from typing import Any


def detect_key_provider(key: str) -> str:
    """Guess which provider a pasted session key belongs to, purely from its
    shape -- Anthropic keys are always prefixed `sk-ant-`; everything else
    (plain `sk-...`, project-scoped `sk-proj-...`, etc.) is treated as OpenAI,
    preserving the box's original behavior for existing users."""
    return "anthropic" if str(key or "").strip().lower().startswith("sk-ant-") else "openai"


def classify_provider_failure(status_code: int | None, payload: Any = None, error: str = "") -> dict[str, Any]:
    code = int(status_code or 0)
    payload_text = str(payload or "").lower()
    error_text = str(error or "").lower()
    combined = f"{payload_text} {error_text}"
    if code == 401 or "invalid_api_key" in combined or "incorrect api key" in combined:
        return {"state": "invalid", "reason": "invalid_authentication", "clear_key": True, "retryable": False}
    if code == 403:
        return {"state": "degraded", "reason": "access_restricted", "clear_key": False, "retryable": False}
    if code == 429:
        reason = "quota_exhausted" if any(token in combined for token in ("insufficient_quota", "quota")) else "rate_limited"
        return {"state": "degraded", "reason": reason, "clear_key": False, "retryable": reason == "rate_limited"}
    if code == 404:
        return {"state": "degraded", "reason": "model_or_endpoint_unavailable", "clear_key": False, "retryable": False}
    if code >= 500:
        return {"state": "degraded", "reason": "provider_transient", "clear_key": False, "retryable": True}
    if code >= 400:
        return {"state": "degraded", "reason": "provider_request_rejected", "clear_key": False, "retryable": False}
    return {"state": "degraded", "reason": "network_unavailable", "clear_key": False, "retryable": True}


def _wipe(value: bytearray | None) -> None:
    if value is None:
        return
    for index in range(len(value)):
        value[index] = 0


def _safe_json(response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"message": str(getattr(response, "text", ""))[:500]}


_ANTHROPIC_VERSION = "2023-06-01"
_PROVIDER_DEFAULT_BASE_URL = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
}


def _provider_headers(key: bytearray, provider: str = "openai") -> dict[str, str]:
    # Anthropic authenticates via x-api-key + a version header, not a bearer
    # token -- everything else (openai and openai-compatible) uses Bearer.
    if provider == "anthropic":
        return {
            "x-api-key": bytes(key).decode("utf-8"),
            "anthropic-version": _ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
    return {
        "Authorization": f"Bearer {bytes(key).decode('utf-8')}",
        "Content-Type": "application/json",
    }


def _link_validation_request(provider: str, model: str) -> tuple[str, dict]:
    """(path, payload) for the tiny probe call that validates a freshly-linked
    key against the real API -- provider-specific because Anthropic's Messages
    API has no /responses endpoint and always requires max_tokens."""
    if provider == "anthropic":
        return "messages", {
            "model": model,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "Reply with OK."}],
        }
    return "responses", {"model": model, "input": "Reply with OK.", "max_output_tokens": 8}


def _broker_main(connection) -> None:
    import requests

    credentials: dict[str, bytearray] = {}
    states: dict[str, dict[str, Any]] = {}
    try:
        while True:
            request = connection.recv()
            operation = str(request.get("operation") or "status")
            provider = str(request.get("provider") or "openai").lower()
            if operation == "shutdown":
                connection.send({"ok": True})
                break
            if operation == "status":
                state = states.get(provider, {"state": "unlinked", "reason": "no_session_key"})
                connection.send({"ok": True, "provider": provider, **state})
                continue
            if operation == "unlink":
                _wipe(credentials.pop(provider, None))
                states[provider] = {"state": "unlinked", "reason": "user_unlinked"}
                connection.send({"ok": True, "provider": provider, **states[provider]})
                continue
            if operation == "link":
                raw = str(request.get("key") or "").strip()
                if not raw:
                    connection.send({"ok": False, "provider": provider, "state": "invalid", "reason": "empty_key"})
                    continue
                _wipe(credentials.pop(provider, None))
                credentials[provider] = bytearray(raw.encode("utf-8"))
                default_base = _PROVIDER_DEFAULT_BASE_URL.get(provider, _PROVIDER_DEFAULT_BASE_URL["openai"])
                base_url = str(request.get("base_url") or default_base).rstrip("/")
                model = str(request.get("model") or "").strip()
                headers = _provider_headers(credentials[provider], provider)
                model_count = 0
                try:
                    # Anthropic: skip the /models list check and validate with the
                    # real message probe below instead -- its exact list-endpoint
                    # response shape hasn't been verified against a live key, and a
                    # wrong assumption there would reject an otherwise-valid key
                    # before ever reaching the probe that actually proves it works.
                    if provider != "anthropic":
                        models_response = requests.get(f"{base_url}/models", headers=headers, timeout=15)
                        models_payload = _safe_json(models_response)
                        if not 200 <= models_response.status_code < 300:
                            failure = classify_provider_failure(models_response.status_code, models_payload)
                            if failure["clear_key"]:
                                _wipe(credentials.pop(provider, None))
                            states[provider] = {**failure, "model": model}
                            connection.send({"ok": False, "provider": provider, **states[provider]})
                            continue
                        model_ids = {
                            str(item.get("id"))
                            for item in (models_payload.get("data") or [])
                            if isinstance(item, dict) and item.get("id")
                        }
                        model_count = len(model_ids)
                        if model and model_ids and model not in model_ids:
                            states[provider] = {
                                "state": "degraded",
                                "reason": "configured_model_unavailable",
                                "model": model,
                                "model_count": model_count,
                            }
                            connection.send({"ok": True, "provider": provider, **states[provider]})
                            continue
                    probe_path, probe_payload = _link_validation_request(provider, model)
                    probe_response = requests.post(
                        f"{base_url}/{probe_path}",
                        json=probe_payload,
                        headers=headers,
                        timeout=30,
                    )
                    probe_data = _safe_json(probe_response)
                    if not 200 <= probe_response.status_code < 300:
                        failure = classify_provider_failure(probe_response.status_code, probe_data)
                        if failure["clear_key"]:
                            _wipe(credentials.pop(provider, None))
                        states[provider] = {**failure, "model": model, "model_count": model_count}
                        connection.send({"ok": False, "provider": provider, **states[provider]})
                        continue
                    states[provider] = {
                        "state": "linked",
                        "reason": "validated",
                        "model": model,
                        "model_count": model_count,
                    }
                    connection.send({"ok": True, "provider": provider, **states[provider]})
                except Exception as exc:
                    failure = classify_provider_failure(None, error=str(exc))
                    states[provider] = {**failure, "model": model}
                    connection.send({"ok": False, "provider": provider, **states[provider]})
                continue
            if operation == "request":
                key = credentials.get(provider)
                if key is None:
                    connection.send({"ok": False, "provider": provider, "state": "unlinked", "reason": "no_session_key"})
                    continue
                default_base = _PROVIDER_DEFAULT_BASE_URL.get(provider, _PROVIDER_DEFAULT_BASE_URL["openai"])
                base_url = str(request.get("base_url") or default_base).rstrip("/")
                path = "/" + str(request.get("path") or "responses").lstrip("/")
                try:
                    response = requests.post(
                        f"{base_url}{path}",
                        json=request.get("payload") or {},
                        headers=_provider_headers(key, provider),
                        timeout=int(request.get("timeout") or 120),
                    )
                    data = _safe_json(response)
                    if not 200 <= response.status_code < 300:
                        failure = classify_provider_failure(response.status_code, data)
                        if failure["clear_key"]:
                            _wipe(credentials.pop(provider, None))
                        states[provider] = failure
                        connection.send({"ok": False, "provider": provider, "status_code": response.status_code, "error": data, **failure})
                    else:
                        states[provider] = {"state": "linked", "reason": "request_succeeded"}
                        connection.send({"ok": True, "provider": provider, "status_code": response.status_code, "data": data})
                except Exception as exc:
                    failure = classify_provider_failure(None, error=str(exc))
                    states[provider] = failure
                    connection.send({"ok": False, "provider": provider, "error": str(exc), **failure})
                continue
            connection.send({"ok": False, "error": f"Unsupported broker operation: {operation}"})
    except EOFError:
        pass
    finally:
        for value in credentials.values():
            _wipe(value)
        credentials.clear()
        connection.close()


@dataclass(frozen=True)
class CredentialHandle:
    provider: str
    session_id: str


class SessionCredentialBroker:
    def __init__(self) -> None:
        self.session_id = uuid.uuid4().hex
        self._connection = None
        self._process: mp.Process | None = None
        self._lock = threading.RLock()

    def _ensure_started(self) -> None:
        if self._process is not None and self._process.is_alive():
            return
        parent, child = mp.Pipe(duplex=True)
        process = mp.Process(target=_broker_main, args=(child,), name="jarvis-credential-broker", daemon=True)
        process.start()
        child.close()
        self._connection = parent
        self._process = process

    def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._ensure_started()
            assert self._connection is not None
            self._connection.send(payload)
            return dict(self._connection.recv())

    def link(self, provider: str, key: str, *, base_url: str, model: str) -> dict[str, Any]:
        result = self._send({"operation": "link", "provider": provider, "key": key, "base_url": base_url, "model": model})
        result["handle"] = CredentialHandle(provider, self.session_id).__dict__
        return result

    def link_openai(self, key: str, *, base_url: str, model: str) -> dict[str, Any]:
        return self.link("openai", key, base_url=base_url, model=model)

    def has_linked_session(self) -> bool:
        """True only when a broker subprocess is actually live.

        `link()` is the only way a key enters the broker, and it starts the
        subprocess, so a False here is an exact "nothing has been linked this
        session" rather than a guess. Callers use it to skip the `status()`
        IPC round trip on a purely local session -- without it, asking "is
        OpenAI linked?" would *spawn* a credential-broker process just to be
        told no, on every planner turn.
        """
        with self._lock:
            return self._process is not None and self._process.is_alive()

    def status(self, provider: str = "openai") -> dict[str, Any]:
        return self._send({"operation": "status", "provider": provider})

    def unlink(self, provider: str = "openai") -> dict[str, Any]:
        return self._send({"operation": "unlink", "provider": provider})

    def request(self, *, provider: str = "openai", base_url: str, path: str, payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
        return self._send({
            "operation": "request",
            "provider": provider,
            "base_url": base_url,
            "path": path,
            "payload": payload,
            "timeout": timeout,
        })

    def close(self) -> None:
        with self._lock:
            if self._process is None:
                return
            if self._process.is_alive() and self._connection is not None:
                try:
                    self._connection.send({"operation": "shutdown"})
                    self._connection.poll(1.0)
                    if self._connection.poll():
                        self._connection.recv()
                except Exception:
                    pass
            self._process.join(timeout=2)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=2)
            if self._connection is not None:
                self._connection.close()
            self._connection = None
            self._process = None


_BROKER = SessionCredentialBroker()
atexit.register(_BROKER.close)


def get_session_broker() -> SessionCredentialBroker:
    return _BROKER

