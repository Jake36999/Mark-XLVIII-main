import unittest
import asyncio
import threading
from unittest import mock


class WindowsTtsTests(unittest.TestCase):
    def test_create_tts_player_supports_windows_engine(self):
        from core import tts

        player = tts.create_tts_player({"tts_engine": "windows"})

        self.assertIsInstance(player._engine, tts.WindowsSapiTTSEngine)

    def test_tts_player_invokes_engine_and_callbacks(self):
        from core.tts import TTSPlayer

        calls = []

        class FakeEngine:
            def speak(self, text):
                calls.append(text)

        player = TTSPlayer(FakeEngine())
        player.speak("hello", on_start=lambda: calls.append("start"), on_done=lambda: calls.append("done"))

        self.assertEqual(calls, ["start", "hello", "done"])


class OpenAICompatibleTtsTests(unittest.TestCase):
    def test_create_tts_player_supports_openai_compatible_engine(self):
        from core import tts

        player = tts.create_tts_player({"tts_engine": "orpheus"})

        self.assertIsInstance(player._engine, tts.OpenAICompatibleTTSEngine)
        self.assertEqual(player._engine.base_url, "http://localhost:5005/v1")
        self.assertEqual(player._engine.model, "orpheus")
        self.assertEqual(player._engine.voice, "tara")

    def test_openai_compatible_engine_posts_audio_speech_payload(self):
        from core import tts

        engine = tts.OpenAICompatibleTTSEngine(
            base_url="http://localhost:5005/v1/",
            model="tts-1",
            voice="leah",
            speed=1.1,
        )
        response = mock.Mock()
        response.headers = {"content-type": "audio/wav"}
        response.content = b"RIFF....WAVE"
        response.raise_for_status.return_value = None

        with mock.patch("requests.post", return_value=response) as post, mock.patch("core.tts._play_audio_bytes") as play:
            engine.speak("hello")

        post.assert_called_once()
        call = post.call_args
        self.assertEqual(call.args[0], "http://localhost:5005/v1/audio/speech")
        self.assertEqual(call.kwargs["json"]["input"], "hello")
        self.assertEqual(call.kwargs["json"]["model"], "tts-1")
        self.assertEqual(call.kwargs["json"]["voice"], "leah")
        self.assertEqual(call.kwargs["json"]["speed"], 1.1)
        play.assert_called_once_with(b"RIFF....WAVE")


class RouterModeSpeechTests(unittest.TestCase):
    def test_speak_uses_local_tts_when_no_gemini_session_exists(self):
        import main

        spoken = []
        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis._loop = None
        jarvis.session = None
        jarvis._local_tts = mock.Mock()
        jarvis._local_tts.speak.side_effect = lambda text, **_: spoken.append(text)

        jarvis.speak("router reply")

        self.assertEqual(spoken, ["router reply"])

    def test_voice_transcript_is_sent_to_router_text_handler(self):
        import main

        handled = []
        logs = []
        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis._is_speaking = False
        jarvis._speaking_lock = threading.Lock()
        jarvis._voice_input_block_until = 0.0
        jarvis._last_voice_text = ""
        jarvis._last_voice_time = 0.0
        jarvis._last_voice_filler_time = 0.0
        jarvis._last_user_speech = 0.0
        jarvis.ui = mock.Mock()
        jarvis.ui.write_log.side_effect = logs.append
        jarvis._handle_router_text_command = handled.append

        class ImmediateThread:
            def __init__(self, target, args=(), daemon=None):
                self.target = target
                self.args = args

            def start(self):
                self.target(*self.args)

        with mock.patch("threading.Thread", ImmediateThread):
            jarvis._submit_router_voice_transcript(" Mark voice input ")

        self.assertEqual(handled, ["Mark voice input"])
        self.assertEqual(logs, ["YOU (voice): Mark voice input"])

    def test_voice_filler_transcripts_are_rate_limited(self):
        import main

        handled = []
        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis._is_speaking = False
        jarvis._speaking_lock = threading.Lock()
        jarvis._voice_input_block_until = 0.0
        jarvis._last_voice_text = ""
        jarvis._last_voice_time = 0.0
        jarvis._last_voice_filler_time = 0.0
        jarvis._last_user_speech = 0.0
        jarvis.ui = mock.Mock()
        jarvis._handle_router_text_command = handled.append

        class ImmediateThread:
            def __init__(self, target, args=(), daemon=None):
                self.target = target
                self.args = args

            def start(self):
                self.target(*self.args)

        with mock.patch("threading.Thread", ImmediateThread), \
             mock.patch("main._load_runtime_config", return_value={"stt_filler_cooldown_seconds": 300}), \
             mock.patch("time.monotonic", side_effect=[1000.0, 1120.0, 1301.0]):
            jarvis._submit_router_voice_transcript("huh")
            jarvis._submit_router_voice_transcript("huh")
            jarvis._submit_router_voice_transcript("huh")

        self.assertEqual(handled, ["huh", "huh"])
        self.assertEqual(jarvis.ui.write_log.call_count, 2)

    def test_voice_transcript_is_ignored_while_tts_is_speaking(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis._is_speaking = True
        jarvis._speaking_lock = threading.Lock()
        jarvis._voice_input_block_until = 0.0
        jarvis._router_stt_lock = threading.Lock()
        jarvis._router_stt_partial = "echo"
        jarvis._local_stt = mock.Mock()
        jarvis._last_voice_text = ""
        jarvis._last_voice_time = 0.0
        jarvis._last_user_speech = 0.0
        jarvis.ui = mock.Mock()
        jarvis._handle_router_text_command = mock.Mock()

        jarvis._submit_router_voice_transcript("open the tools")

        jarvis._handle_router_text_command.assert_not_called()
        jarvis._local_stt.reset.assert_called_once()
        self.assertEqual(jarvis._router_stt_partial, "")

    def test_get_local_stt_creates_vosk_engine(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        fake_stt = mock.Mock()

        with mock.patch("main._load_runtime_config", return_value={"voice_enabled": True, "stt_engine": "vosk", "stt_language": "en-us"}), \
             mock.patch("core.stt.VoskSTT", return_value=fake_stt) as vosk:
            result = jarvis._get_local_stt()

        self.assertIs(result, fake_stt)
        vosk.assert_called_once_with(model_path=None, language="en-us")

    def test_mute_changed_flushes_pending_partial_transcript(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._local_stt = mock.Mock()
        jarvis._local_stt.final_result.return_value = ""
        jarvis._router_stt_lock = threading.Lock()
        jarvis._router_stt_partial = "mark status report"
        jarvis._submit_router_voice_transcript = mock.Mock()

        jarvis._on_mute_changed(True)

        jarvis._submit_router_voice_transcript.assert_called_once_with("mark status report")
        jarvis._local_stt.reset.assert_called_once()
        self.assertEqual(jarvis._router_stt_partial, "")

    def test_unmute_resets_router_stt_and_returns_to_listening(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._local_stt = mock.Mock()
        jarvis._router_stt_lock = threading.Lock()
        jarvis._router_stt_partial = "stale phrase"
        jarvis._speaking_lock = threading.Lock()
        jarvis._is_speaking = False

        jarvis._on_mute_changed(False)

        jarvis._local_stt.reset.assert_called_once()
        self.assertEqual(jarvis._router_stt_partial, "")
        jarvis.ui.set_state.assert_called_once_with("LISTENING")


class RouterModeSttRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_router_stt_retries_after_stream_timeout(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis.ui.muted = False
        jarvis._reset_router_stt = mock.Mock()
        jarvis._listen_router_stt_once = mock.AsyncMock(
            side_effect=[TimeoutError("no microphone audio callbacks for 18s"), asyncio.CancelledError()]
        )

        async def fake_sleep(_seconds):
            return None

        with mock.patch("main.sd", object()), mock.patch("asyncio.sleep", side_effect=fake_sleep) as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await jarvis._listen_router_stt()

        self.assertEqual(jarvis._listen_router_stt_once.await_count, 2)
        jarvis._reset_router_stt.assert_called_once()
        jarvis.ui.set_state.assert_called_once_with("LISTENING")
        jarvis.ui.write_log.assert_called_once()
        sleep.assert_awaited_once_with(1.0)


class InputDeviceSelectionTests(unittest.TestCase):
    def test_named_input_prefers_wasapi_over_mme(self):
        import main

        fake_sd = mock.Mock()
        fake_sd.query_devices.return_value = [
            {"name": "Microphone (Jabra Evolve2 40)", "max_input_channels": 1, "hostapi": 0},
            {"name": "Microphone (Jabra Evolve2 40)", "max_input_channels": 2, "hostapi": 1},
        ]
        fake_sd.query_hostapis.return_value = [
            {"name": "MME"},
            {"name": "Windows WASAPI"},
        ]

        self.assertEqual(main._select_input_device(fake_sd, None, "Jabra Evolve2 40"), 1)

    def test_named_input_avoids_host_api_with_invalid_sample_rate(self):
        import main

        fake_sd = mock.Mock()
        fake_sd.query_devices.return_value = [
            {"name": "Microphone (Jabra Evolve2 40)", "max_input_channels": 1, "hostapi": 0},
            {"name": "Microphone (Jabra Evolve2 40)", "max_input_channels": 2, "hostapi": 1},
        ]
        fake_sd.query_hostapis.return_value = [
            {"name": "Windows DirectSound"},
            {"name": "Windows WASAPI"},
        ]

        def check_input_settings(device, **_kwargs):
            if device == 1:
                raise RuntimeError("Invalid sample rate")

        fake_sd.check_input_settings.side_effect = check_input_settings

        self.assertEqual(main._select_input_device(fake_sd, None, "Jabra Evolve2 40"), 0)

    def test_explicit_input_device_wins_over_name(self):
        import main

        fake_sd = mock.Mock()

        self.assertEqual(main._select_input_device(fake_sd, "6", "Jabra Evolve2 40"), 6)


class SpeechConfigDefaultTests(unittest.TestCase):
    def test_setup_merge_defaults_to_windows_tts_and_vosk_stt(self):
        from ui import _merge_setup_config

        cfg = _merge_setup_config({}, "", "windows", "sk-test")

        self.assertTrue(cfg["voice_enabled"])
        self.assertEqual(cfg["tts_engine"], "windows")
        self.assertEqual(cfg["stt_engine"], "vosk")

    def test_dependency_check_script_includes_speech_modules(self):
        from pathlib import Path

        text = Path("scripts/check-mark-dependencies.ps1").read_text(encoding="utf-8")

        self.assertIn("comtypes", text)
        self.assertIn("vosk", text)
        self.assertIn("miniaudio", text)


if __name__ == "__main__":
    unittest.main()
