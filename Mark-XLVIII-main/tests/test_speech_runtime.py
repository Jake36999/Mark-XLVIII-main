import unittest
import asyncio
import threading
import time
from pathlib import Path
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

    def test_tts_player_suppresses_duplicate_active_utterance(self):
        from core.tts import TTSPlayer

        started = threading.Event()
        release = threading.Event()
        calls = []

        class SlowEngine:
            def speak(self, text):
                calls.append(text)
                started.set()
                release.wait(2)

        player = TTSPlayer(SlowEngine(), duplicate_window_seconds=20)
        thread = threading.Thread(target=lambda: player.speak("same reply"))
        thread.start()
        self.assertTrue(started.wait(2))

        player.speak("same reply")
        release.set()
        thread.join(2)

        self.assertEqual(calls, ["same reply"])


class OpenAICompatibleTtsTests(unittest.TestCase):
    def test_create_tts_player_supports_openai_compatible_engine(self):
        from core import tts

        with mock.patch("core.tts.warm_local_tts_service", return_value={"warming": False}):
            player = tts.create_tts_player({"tts_engine": "orpheus", "tts_auto_start_bridge": False})

        self.assertIsInstance(player._engine, tts.ResilientTTSEngine)
        self.assertIsInstance(player._engine.primary, tts.OpenAICompatibleTTSEngine)
        self.assertEqual(player._engine.primary.base_url, "http://localhost:5005/v1")
        self.assertEqual(player._engine.primary.model, "orpheus")
        self.assertEqual(player._engine.primary.voice, "tara")
        self.assertTrue(player._engine.primary.chunking_enabled)
        self.assertEqual(player._engine.primary.chunk_workers, 1)

    def test_resilient_tts_uses_windows_fallback_when_orpheus_is_not_ready(self):
        from core import tts

        calls = []

        class Engine:
            def __init__(self, name):
                self.name = name

            def speak(self, text):
                calls.append((self.name, text))

        engine = tts.ResilientTTSEngine(Engine("primary"), Engine("fallback"), {"tts_engine": "orpheus"})
        with mock.patch("core.tts.tts_runtime_status", return_value={"primary_ready": False}), mock.patch(
            "core.tts.warm_local_tts_service", return_value={"warming": True}
        ):
            engine.speak("hello")

        self.assertEqual(calls, [("fallback", "hello")])
        self.assertEqual(engine.last_backend, "windows")

    def test_resilient_tts_prefers_orpheus_after_bounded_warmup(self):
        from core import tts

        calls = []

        class Engine:
            def __init__(self, name):
                self.name = name

            def speak(self, text):
                calls.append((self.name, text))

        engine = tts.ResilientTTSEngine(
            Engine("primary"),
            Engine("fallback"),
            {"tts_engine": "orpheus", "tts_orpheus_first_turn_wait_seconds": 7},
        )
        with mock.patch(
            "core.tts.tts_runtime_status",
            side_effect=[{"primary_ready": False}, {"primary_ready": True}],
        ), mock.patch(
            "core.tts.warm_local_tts_service",
            return_value={"ready": True, "warming": False},
        ) as warm:
            engine.speak("hello")

        warm.assert_called_once_with(engine.config, wait_seconds=7.0)
        self.assertEqual(calls, [("primary", "hello")])
        self.assertEqual(engine.last_backend, "orpheus")

    def test_resilient_tts_falls_back_when_primary_raises(self):
        from core import tts

        calls = []

        class Primary:
            def speak(self, text):
                raise RuntimeError("bridge failed")

        class Fallback:
            def speak(self, text):
                calls.append(text)

        engine = tts.ResilientTTSEngine(Primary(), Fallback(), {"tts_engine": "orpheus"})
        with mock.patch("core.tts.tts_runtime_status", return_value={"primary_ready": True}):
            engine.speak("hello")

        self.assertEqual(calls, ["hello"])
        self.assertIn("bridge failed", engine.last_error)

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

    def test_openai_compatible_engine_chunks_text_and_plays_in_order(self):
        from core import tts

        engine = tts.OpenAICompatibleTTSEngine(
            base_url="http://localhost:5005/v1/",
            model="tts-1",
            voice="leah",
            chunk_chars=90,
            chunk_workers=2,
        )
        text = (
            "First sentence is deliberately long enough to form the opening audio chunk for the test. "
            "Second sentence is also long enough to be a separate synthesis request for speech. "
            "Third sentence completes the ordered playback check cleanly."
        )
        synth_calls = []

        def fake_synth(chunk):
            synth_calls.append(chunk)
            return f"audio-{len(synth_calls)}:{chunk[:5]}".encode("utf-8")

        played = []
        with mock.patch.object(engine, "_synth_chunk", side_effect=fake_synth), \
             mock.patch("core.tts._play_audio_bytes", side_effect=played.append):
            engine.speak(text)

        self.assertGreater(len(synth_calls), 1)
        self.assertNotIn(text, synth_calls)
        self.assertEqual(len(played), len(synth_calls))
        self.assertTrue(played[0].startswith(b"audio-1:First"))

    def test_orpheus_releases_idle_specialist_before_speech(self):
        from core import tts

        engine = tts.OpenAICompatibleTTSEngine(
            lifecycle_config={"tts_release_idle_task_models": True}
        )
        with mock.patch(
            "actions.model_lifecycle.unload_non_baseline",
            return_value={"ok": True, "unloaded": [{"model_key": "deepseek"}]},
        ) as unload, mock.patch.object(
            engine, "_synth_for_turn", return_value=b"RIFF....WAVE"
        ), mock.patch("core.tts._play_audio_bytes"):
            engine.speak("hello")

        unload.assert_called_once_with(
            engine.lifecycle_config,
            timeout=10,
            force=False,
        )

    def test_openai_compatible_engine_never_synthesizes_two_chunks_at_once(self):
        from core import tts

        engine = tts.OpenAICompatibleTTSEngine(chunk_chars=80, chunk_workers=4)
        active = 0
        max_active = 0
        state_lock = threading.Lock()

        def fake_synth(chunk):
            nonlocal active, max_active
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with state_lock:
                active -= 1
            return chunk.encode("utf-8")

        text = "First sentence is long enough to split cleanly. Second sentence also forms a chunk."
        with mock.patch.object(engine, "_synth_chunk", side_effect=fake_synth), \
             mock.patch("core.tts._play_audio_bytes"):
            first = threading.Thread(target=lambda: engine.speak(text))
            second = threading.Thread(target=lambda: engine.speak(text + " Another sentence."))
            first.start()
            second.start()
            first.join(3)
            second.join(3)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(max_active, 1)
        self.assertEqual(engine.chunk_workers, 1)

    def test_openai_compatible_engine_cancel_discards_remaining_chunks(self):
        from core import tts

        engine = tts.OpenAICompatibleTTSEngine(chunk_chars=80)
        started = threading.Event()
        release = threading.Event()
        synth_calls = []
        played = []

        def fake_synth(chunk):
            synth_calls.append(chunk)
            started.set()
            release.wait(2)
            return chunk.encode("utf-8")

        text = "First sentence creates work. Second sentence must be cancelled. Third must never submit."
        with mock.patch.object(engine, "_synth_chunk", side_effect=fake_synth), \
             mock.patch("core.tts._play_audio_bytes", side_effect=played.append):
            thread = threading.Thread(target=lambda: engine.speak(text))
            thread.start()
            self.assertTrue(started.wait(2))
            engine.cancel()
            release.set()
            thread.join(3)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(synth_calls), 1)
        self.assertEqual(played, [])

    def test_tts_player_bounds_pending_utterances(self):
        from core.tts import TTSPlayer

        started = threading.Event()
        release = threading.Event()
        calls = []

        class SlowEngine:
            def speak(self, text):
                calls.append(text)
                started.set()
                release.wait(2)

        player = TTSPlayer(SlowEngine(), max_pending_utterances=1)
        first = threading.Thread(target=lambda: player.speak("first"))
        second = threading.Thread(target=lambda: player.speak("second"))
        first.start()
        self.assertTrue(started.wait(2))
        second.start()
        time.sleep(0.05)
        player.speak("third")
        release.set()
        first.join(2)
        second.join(2)

        self.assertEqual(calls, ["first", "second"])

    def test_tts_player_stop_cancels_waiting_utterance(self):
        from core.tts import TTSPlayer

        started = threading.Event()
        release = threading.Event()
        calls = []

        class SlowEngine:
            def speak(self, text):
                calls.append(text)
                started.set()
                release.wait(2)

            def cancel(self):
                calls.append("cancel")

        player = TTSPlayer(SlowEngine(), max_pending_utterances=1)
        first = threading.Thread(target=lambda: player.speak("first"))
        second = threading.Thread(target=lambda: player.speak("second"))
        first.start()
        self.assertTrue(started.wait(2))
        second.start()
        time.sleep(0.05)
        with mock.patch("core.tts.sd.stop"):
            player.stop()
        release.set()
        first.join(2)
        second.join(2)

        self.assertEqual(calls, ["first", "cancel"])


class RouterModeSpeechTests(unittest.TestCase):
    def test_transcript_parts_merge_without_repeating_adjacent_results(self):
        import main

        merged = main._merge_transcript_parts(
            ["please update", "please update", "the research plan"]
        )

        self.assertEqual(merged, "please update the research plan")

    def test_vosk_final_segments_wait_for_turn_silence_and_merge(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._router_stt_lock = threading.Lock()
        jarvis._router_stt_partial = ""
        jarvis._router_stt_segments = []
        jarvis._router_stt_last_activity = 0.0
        jarvis._local_stt = mock.Mock()
        jarvis._local_stt.final_result.return_value = ""
        jarvis._submit_router_voice_transcript = mock.Mock()

        jarvis._record_router_stt_result("please update", True, now=100.0)
        self.assertFalse(jarvis._router_stt_turn_ready(2.5, now=101.0))
        jarvis._submit_router_voice_transcript.assert_not_called()

        jarvis._record_router_stt_result("the research plan", True, now=101.5)
        self.assertFalse(jarvis._router_stt_turn_ready(2.5, now=103.0))
        self.assertTrue(jarvis._router_stt_turn_ready(2.5, now=104.1))
        jarvis._flush_router_stt_turn()

        jarvis._submit_router_voice_transcript.assert_called_once_with(
            "please update the research plan"
        )

    def test_speech_level_audio_extends_the_active_turn(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis._router_stt_lock = threading.Lock()
        jarvis._router_stt_partial = "keep listening"
        jarvis._router_stt_segments = []
        jarvis._router_stt_last_activity = 100.0

        jarvis._note_router_stt_audio_activity(now=102.0)

        self.assertFalse(jarvis._router_stt_turn_ready(2.5, now=104.0))
        self.assertTrue(jarvis._router_stt_turn_ready(2.5, now=104.6))

    def test_flush_preserves_partial_after_an_earlier_final_segment(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._router_stt_lock = threading.Lock()
        jarvis._router_stt_partial = "the research plan"
        jarvis._router_stt_segments = ["please update"]
        jarvis._router_stt_last_activity = 100.0
        jarvis._local_stt = mock.Mock()
        jarvis._local_stt.final_result.return_value = ""
        jarvis._submit_router_voice_transcript = mock.Mock()

        jarvis._flush_router_stt_turn()

        jarvis._submit_router_voice_transcript.assert_called_once_with(
            "please update the research plan"
        )

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

    def test_interrupt_stops_local_tts(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis._interrupted = False
        jarvis._pending_plan_run_id = ""
        jarvis._active_plan_run_id = ""
        jarvis._local_tts = mock.Mock()
        jarvis.audio_in_queue = None
        jarvis._turn_done_event = None
        jarvis._voice_input_block_until = 0.0
        jarvis._is_speaking = True
        jarvis._speaking_lock = threading.Lock()
        jarvis._router_generation_lock = threading.Lock()
        jarvis._router_turn_seq = 0
        jarvis._router_latest_turn_id = 0
        jarvis._router_latest_turn_source = ""
        jarvis._local_stt = None
        jarvis._router_stt_lock = threading.Lock()
        jarvis.ui = mock.Mock()
        jarvis.ui.muted = False

        jarvis.interrupt()

        jarvis._local_tts.stop.assert_called_once_with()

    def test_speech_completion_waits_for_tail_guard_before_listening(self):
        import main

        callbacks = []

        class DeferredTimer:
            def __init__(self, delay, callback):
                self.delay = delay
                self.callback = callback
                self.daemon = False

            def start(self):
                callbacks.append(self.callback)

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis.ui.muted = False
        jarvis._is_speaking = True
        jarvis._speaking_lock = threading.Lock()
        jarvis._voice_input_generation = 1
        jarvis._speech_resume_generation = 1
        jarvis._voice_input_block_until = 0.0
        jarvis._router_turn_lock = threading.Lock()
        jarvis._pending_plan_run_id = ""
        jarvis._active_plan_run_id = ""
        jarvis._reset_router_stt = mock.Mock()

        with mock.patch("threading.Timer", DeferredTimer), mock.patch(
            "main._load_runtime_config", return_value={"stt_after_tts_cooldown_seconds": 3}
        ), mock.patch("time.monotonic", return_value=100.0):
            jarvis.set_speaking(False)

        jarvis.ui.set_state.assert_not_called()
        self.assertEqual(len(callbacks), 1)

        with mock.patch("time.monotonic", return_value=104.0):
            callbacks[0]()

        jarvis.ui.set_state.assert_called_once_with("LISTENING")

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
        jarvis._handle_router_text_command = lambda text, turn_id=None, source="text": handled.append(
            (text, turn_id, source)
        )

        class ImmediateThread:
            def __init__(self, target, args=(), daemon=None):
                self.target = target
                self.args = args

            def start(self):
                self.target(*self.args)

        with mock.patch("threading.Thread", ImmediateThread):
            jarvis._submit_router_voice_transcript(" Mark voice input ")

        self.assertEqual(handled[0][0], "Mark voice input")
        self.assertIsInstance(handled[0][1], int)
        self.assertEqual(handled[0][2], "voice")
        self.assertEqual(logs, ["YOU (voice): Mark voice input"])

    def test_voice_filler_requires_fifteen_minutes_of_user_idle_time(self):
        import main

        handled = []
        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis._is_speaking = False
        jarvis._speaking_lock = threading.Lock()
        jarvis._voice_input_block_until = 0.0
        jarvis._last_voice_text = ""
        jarvis._last_voice_time = 0.0
        jarvis._last_voice_filler_time = 0.0
        jarvis._last_user_speech = 1000.0
        jarvis._router_turn_lock = threading.Lock()
        jarvis._router_generation_lock = threading.Lock()
        jarvis._pending_plan_run_id = ""
        jarvis._active_plan_run_id = ""
        jarvis._local_tts = None
        jarvis.ui = mock.Mock()
        jarvis._handle_router_text_command = lambda text, turn_id=None, source="text": handled.append(
            (text, turn_id, source)
        )

        class ImmediateThread:
            def __init__(self, target, args=(), daemon=None):
                self.target = target
                self.args = args

            def start(self):
                self.target(*self.args)

        with mock.patch("threading.Thread", ImmediateThread), \
             mock.patch(
                 "main._load_runtime_config",
                 return_value={"stt_filler_cooldown_seconds": 900, "stt_filler_user_idle_seconds": 900},
             ), \
             mock.patch("time.monotonic", side_effect=[1200.0, 1901.0, 2200.0, 2802.0]):
            jarvis._submit_router_voice_transcript("huh")
            jarvis._submit_router_voice_transcript("huh")
            jarvis._submit_router_voice_transcript("huh")
            jarvis._submit_router_voice_transcript("huh")

        self.assertEqual([item[0] for item in handled], ["huh", "huh"])
        self.assertTrue(all(item[2] == "voice" for item in handled))
        self.assertEqual(jarvis.ui.write_log.call_count, 2)

    def test_voice_filler_is_suppressed_during_an_active_router_turn(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis._is_speaking = False
        jarvis._speaking_lock = threading.Lock()
        jarvis._voice_input_block_until = 0.0
        jarvis._last_voice_filler_time = 0.0
        jarvis._last_user_speech = 0.0
        jarvis._router_turn_lock = threading.Lock()
        jarvis._router_turn_lock.acquire()
        jarvis._router_generation_lock = threading.Lock()
        jarvis._pending_plan_run_id = ""
        jarvis._active_plan_run_id = ""
        jarvis._local_tts = None
        jarvis.ui = mock.Mock()
        jarvis._handle_router_text_command = mock.Mock()

        try:
            with mock.patch("time.monotonic", return_value=2000.0), mock.patch(
                "main._load_runtime_config",
                return_value={"stt_filler_cooldown_seconds": 900, "stt_filler_user_idle_seconds": 900},
            ):
                jarvis._submit_router_voice_transcript("huh")
        finally:
            jarvis._router_turn_lock.release()

        jarvis._handle_router_text_command.assert_not_called()
        jarvis.ui.write_log.assert_not_called()

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
        text = Path("scripts/check-mark-dependencies.ps1").read_text(encoding="utf-8")

        self.assertIn("comtypes", text)
        self.assertIn("vosk", text)
        self.assertIn("miniaudio", text)

    def test_orpheus_runtime_logging_is_ascii_safe(self):
        source = Path(
            "tools/Orpheus-FastAPI-LMStudio/tts_engine/inference.py"
        ).read_text(encoding="utf-8")

        source.encode("ascii")

    def test_orpheus_bridge_enforces_process_wide_single_flight(self):
        source = Path("tools/Orpheus-FastAPI-LMStudio/app.py").read_text(encoding="utf-8")
        launcher = Path("scripts/start-orpheus-tts-bridge.ps1").read_text(encoding="utf-8")
        inference = Path(
            "tools/Orpheus-FastAPI-LMStudio/tts_engine/inference.py"
        ).read_text(encoding="utf-8")

        self.assertIn("_SYNTHESIS_CONCURRENCY = 1", source)
        self.assertIn("_SYNTHESIS_THREAD_LOCK", source)
        self.assertIn('$env:ORPHEUS_CONCURRENCY = "1"', launcher)
        self.assertIn('ORPHEUS_MAX_RETRIES", "1"', inference)
        self.assertIn("token_budget_for_text", inference)
        self.assertIn("MAX_GENERATION_SECONDS", inference)
        self.assertIn("ORPHEUS_MAX_TOKENS", launcher)

    def test_runtime_config_allows_a_natural_pause_before_dispatch(self):
        import json

        cfg = json.loads(Path("config/runtime.json").read_text(encoding="utf-8"))

        self.assertGreaterEqual(cfg["stt_turn_silence_seconds"], 2.5)

    def test_runtime_config_preloads_orpheus_and_gates_filler_on_user_idle(self):
        import json

        cfg = json.loads(Path("config/runtime.json").read_text(encoding="utf-8"))

        self.assertEqual(cfg["tts_lmstudio_model"], "orpeus_text_to_speech")
        self.assertIn("orpeus_text_to_speech", cfg["baseline_models"])
        self.assertGreaterEqual(cfg["stt_filler_user_idle_seconds"], 900)
        self.assertGreaterEqual(cfg["stt_filler_cooldown_seconds"], 900)


if __name__ == "__main__":
    unittest.main()
