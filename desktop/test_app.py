"""Engine logic with the Windows-only pieces (keyboard, mic, webview, Whisper) stubbed out."""
import json
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import numpy as np

sent, clip = [], {"v": "old clipboard"}
stubs = {
    "keyboard": types.SimpleNamespace(unhook_all=lambda: None, on_press_key=lambda *a, **k: None,
                                      on_release_key=lambda *a, **k: None, send=lambda k: sent.append(k)),
    "pyperclip": types.SimpleNamespace(paste=lambda: clip["v"], copy=lambda t: clip.update(v=t), PyperclipException=Exception),
    "sounddevice": types.SimpleNamespace(InputStream=None),
    "webview": types.SimpleNamespace(),
    "faster_whisper": types.SimpleNamespace(WhisperModel=None),
}
sys.modules.update(stubs)
sys.path.insert(0, str(Path(__file__).parent))
import app   # noqa: E402
import core  # noqa: E402


class FakeWindow:
    def __init__(self):
        self.js = []
    def evaluate_js(self, s):
        self.js.append(s)
    def show(self):
        pass
    def restore(self):
        pass


class FakeModel:
    def transcribe(self, audio, **kw):
        return [types.SimpleNamespace(text=" um send the invoice to awaz team")], None


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with mock.patch.object(core, "APP_DIR", Path(self.tmp.name)):
            self.e = app.Engine()
        self.e.history = core.History(Path(self.tmp.name) / "h.jsonl")
        self.e.hub, self.e.pill = FakeWindow(), FakeWindow()
        self.e.model = FakeModel()
        self.e.settings["speak_replies"] = False
        sent.clear()
        clip["v"] = "old clipboard"

    def tearDown(self):
        self.tmp.cleanup()

    def events(self, kind):
        return [s for s in self.e.hub.js if f'emit("{kind}"' in s]

    def test_dictate_pastes_cleaned_text_and_logs_it(self):
        with mock.patch.object(threading, "Timer", lambda t, f: types.SimpleNamespace(start=f)):
            self.e.handle("dictate", np.zeros(16000, dtype="float32"), 1.0)
        self.assertEqual(sent, ["ctrl+v"])
        self.assertEqual(clip["v"], "old clipboard")            # clipboard restored after paste
        h = self.e.history.list()
        self.assertEqual(h[0]["text"], "Send the invoice to Awaaz team")
        self.assertTrue(self.events("history_added"))

    def test_agent_voice_goes_to_hub(self):
        self.e.handle("agent", np.zeros(16000, dtype="float32"), 2.5)
        self.assertIn("Send the invoice to Awaaz team", self.events("voice_ask")[0])
        self.assertEqual(self.e.voice_secs, 2.5)

    def test_builtin_agent_runs_tool_then_answers(self):
        rounds = iter([
            [("tool_calls", [{"function": {"name": "add_reminder", "arguments": {"date": "2026-10-13", "time": "09:00", "text": "Send invoice"}}}])],
            [("delta", "Done, "), ("delta", "reminder added.")],
        ])
        seen = []
        def fake_stream(url, model, msgs, tools_, **kw):
            seen.append([m["role"] for m in msgs])
            return iter(next(rounds))
        with tempfile.TemporaryDirectory() as ws, mock.patch.object(app.tools, "WORKSPACE", Path(ws)), \
                mock.patch.object(core, "ollama_chat_stream", fake_stream):
            self.e.chat([{"role": "user", "content": "kal 9 baje invoice reminder"}])
            self.assertIn("- 2026-10-13 09:00 Send invoice", (Path(ws) / "reminders.md").read_text())
        self.assertEqual(seen[1][-2:], ["assistant", "tool"])          # tool result fed back to the model
        self.assertEqual(self.e.history.list()[0]["reply"], "Done, reminder added.")
        self.assertTrue(self.events("chat_done"))

    def test_brief_fast_path_skips_the_model(self):
        def must_not_call(*a, **k):
            raise AssertionError("model should not be called for the brief")
        with tempfile.TemporaryDirectory() as ws, mock.patch.object(app.tools, "WORKSPACE", Path(ws)), \
                mock.patch.object(core, "ollama_chat_stream", must_not_call):
            (Path(ws) / "reminders.md").write_text("- 2000-01-01 pay rent\n", encoding="utf-8")
            self.e.chat([{"role": "user", "content": "Run my daily brief"}])
        reply = self.e.history.list()[0]["reply"]
        self.assertTrue(reply.startswith("1 overdue, 0 due today"), reply)
        self.assertIn("pay rent", reply)

    def test_prime_uses_same_prefix_as_chat(self):
        seen = []
        def fake(url, model, msgs, tools_, **kw):
            seen.append((msgs[0]["content"], len(tools_), kw.get("max_tokens")))
            return iter([("delta", "ok")])
        with mock.patch.object(core, "ollama_chat_stream", fake):
            self.e.prime()
            self.e.chat([{"role": "user", "content": "hello"}])
        self.assertEqual(seen[0][:2], seen[1][:2])     # identical system prompt + tools -> cache hit
        self.assertEqual((seen[0][2], seen[1][2]), (1, None))

    def test_builtin_offline_message(self):
        def offline(*a, **k):
            raise urllib.error.URLError("refused")
            yield
        with mock.patch.object(core, "ollama_chat_stream", offline):
            self.e.chat([{"role": "user", "content": "hi"}])
        self.assertIn("Can't reach Ollama", self.events("chat_error")[-1])

    def test_chat_success_and_errors(self):
        self.e.settings["agent_engine"] = "hermes"
        with mock.patch.object(core, "chat_stream", lambda *a, **k: iter(["Hi", " there"])):
            self.e.chat([{"role": "user", "content": "hello"}])
        self.assertEqual(len(self.events("chat_delta")), 2)
        self.assertEqual(self.e.history.list()[0]["reply"], "Hi there")

        def boom(*a, **k):
            raise urllib.error.HTTPError("u", 401, "no", {}, None)
            yield
        with mock.patch.object(core, "chat_stream", boom):
            self.e.chat([{"role": "user", "content": "hello"}])
        self.assertIn("Hermes rejected the key", self.events("chat_error")[-1])

        def offline(*a, **k):
            raise urllib.error.URLError("refused")
            yield
        with mock.patch.object(core, "chat_stream", offline):
            self.e.chat([{"role": "user", "content": "hello"}])
        self.assertIn("Can't reach Hermes", self.events("chat_error")[-1])

    def test_short_tap_and_api_validation(self):
        self.e.mode, self.e.frames = "dictate", [np.zeros((800, 1), dtype="float32")]
        self.e.stream = types.SimpleNamespace(stop=lambda: None, close=lambda: None)
        self.e.stop("dictate")
        self.assertIn('"state": "idle"', self.e.pill.js[-1])     # 0.05 s tap ignored
        api = app.Api(self.e)
        self.assertFalse(api.send_chat("not a list"))
        self.assertEqual(json.loads(json.dumps(api.get_bootstrap()))["stats"]["words_total"], 0)


if __name__ == "__main__":
    unittest.main()
