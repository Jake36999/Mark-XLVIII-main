import base64
import unittest
from unittest import mock

from core.tts import DeepInfraTTSEngine


class FakeBroker:
    def __init__(self, *, state="linked", request_result=None):
        self.state = state
        self.request_result = request_result
        self.requests: list[dict] = []

    def status(self, provider="openai"):
        return {"state": self.state}

    def request(self, **kwargs):
        self.requests.append(kwargs)
        return dict(self.request_result or {"ok": True, "data": {}})


class DeepInfraTTSEngineTests(unittest.TestCase):
    def _engine(self, **kwargs):
        return DeepInfraTTSEngine(**kwargs)

    def test_synthesizes_and_plays_base64_audio(self):
        audio = b"fake-wav-bytes"
        data_uri = "data:audio/wav;base64," + base64.b64encode(audio).decode("ascii")
        broker = FakeBroker(request_result={"ok": True, "data": {"audio": data_uri}})
        engine = self._engine()

        with mock.patch("core.session_credentials.get_session_broker", return_value=broker), \
             mock.patch("core.tts._play_audio_bytes") as play:
            engine.speak("hello")

        play.assert_called_once_with(audio)
        self.assertEqual(engine.last_backend, "deepinfra")
        self.assertEqual(engine.last_error, "")

    def test_synthesizes_and_plays_url_audio(self):
        audio = b"fake-mp3-bytes"
        broker = FakeBroker(request_result={"ok": True, "data": {"audio": "https://example.com/out.wav"}})
        engine = self._engine()

        fake_response = mock.Mock(content=audio)
        fake_response.raise_for_status = mock.Mock()
        with mock.patch("core.session_credentials.get_session_broker", return_value=broker), \
             mock.patch("core.tts._play_audio_bytes") as play, \
             mock.patch("requests.get", return_value=fake_response) as get:
            engine.speak("hello")

        get.assert_called_once()
        play.assert_called_once_with(audio)
        self.assertEqual(engine.last_backend, "deepinfra")

    def test_sends_correct_endpoint_and_default_kokoro_payload(self):
        broker = FakeBroker(request_result={"ok": True, "data": {"audio": "data:audio/wav;base64,"}})
        engine = self._engine(model="hexgrad/Kokoro-82M")

        with mock.patch("core.session_credentials.get_session_broker", return_value=broker), \
             mock.patch("core.tts._play_audio_bytes"):
            engine.speak("hello world")

        call = broker.requests[0]
        self.assertEqual(call["provider"], "deepinfra")
        self.assertEqual(call["base_url"], "https://api.deepinfra.com/v1/inference")
        self.assertEqual(call["path"], "hexgrad/Kokoro-82M")
        self.assertEqual(call["payload"], {"text": "hello world"})

    def test_qwen3_tts_uses_input_field_and_voice_not_text(self):
        """Regression guard: Qwen3-TTS 422'd on {"text": ...} live this
        session -- its own error named the required field `input`, and it
        needs a voice preset where Kokoro/chatterbox don't."""
        broker = FakeBroker(request_result={"ok": True, "data": {"audio": "data:audio/wav;base64,"}})
        engine = self._engine(model="Qwen/Qwen3-TTS")

        with mock.patch("core.session_credentials.get_session_broker", return_value=broker), \
             mock.patch("core.tts._play_audio_bytes"):
            engine.speak("hello world")

        payload = broker.requests[0]["payload"]
        self.assertEqual(payload, {"input": "hello world", "voice": "Vivian"})

    def test_qwen3_tts_respects_an_explicit_voice_override(self):
        broker = FakeBroker(request_result={"ok": True, "data": {"audio": "data:audio/wav;base64,"}})
        engine = self._engine(model="Qwen/Qwen3-TTS", voice="Serena")

        with mock.patch("core.session_credentials.get_session_broker", return_value=broker), \
             mock.patch("core.tts._play_audio_bytes"):
            engine.speak("hi")

        self.assertEqual(broker.requests[0]["payload"]["voice"], "Serena")

    def test_falls_back_to_sapi_when_key_is_unlinked(self):
        broker = FakeBroker(state="unlinked")
        engine = self._engine()

        with mock.patch("core.session_credentials.get_session_broker", return_value=broker), \
             mock.patch.object(engine._fallback, "speak") as fallback_speak:
            engine.speak("hello")

        fallback_speak.assert_called_once_with("hello")
        self.assertEqual(engine.last_backend, "sapi_fallback")
        self.assertIn("unlinked", engine.last_error)
        self.assertEqual(broker.requests, [])  # never even attempted the network call

    def test_falls_back_to_sapi_on_broker_request_failure(self):
        broker = FakeBroker(request_result={"ok": False, "reason": "provider_transient"})
        engine = self._engine()

        with mock.patch("core.session_credentials.get_session_broker", return_value=broker), \
             mock.patch.object(engine._fallback, "speak") as fallback_speak:
            engine.speak("hello")

        fallback_speak.assert_called_once_with("hello")
        self.assertEqual(engine.last_backend, "sapi_fallback")

    def test_falls_back_to_sapi_when_response_has_no_audio_field(self):
        broker = FakeBroker(request_result={"ok": True, "data": {}})
        engine = self._engine()

        with mock.patch("core.session_credentials.get_session_broker", return_value=broker), \
             mock.patch.object(engine._fallback, "speak") as fallback_speak:
            engine.speak("hello")

        fallback_speak.assert_called_once_with("hello")
        self.assertEqual(engine.last_backend, "sapi_fallback")

    def test_defaults_to_kokoro_when_model_is_blank(self):
        engine = self._engine(model="")
        self.assertEqual(engine.model, "hexgrad/Kokoro-82M")


if __name__ == "__main__":
    unittest.main()
