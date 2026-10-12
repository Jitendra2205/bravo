"""Engine logic with the Windows-only pieces (keyboard, mic, webview, Whisper) stubbed out."""
import io
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
    "tkinter": types.SimpleNamespace(Tk=None, Canvas=None, TclError=Exception),
}
sys.modules.update(stubs)
sys.path.insert(0, str(Path(__file__).parent))
import app   # noqa: E402
import core  # noqa: E402


class FakePill:
    def __init__(self):
        self.states, self.levels = [], []
    def set_state(self, state, mode="dictate", text="", sub=""):
        self.states.append(state)
    def set_level(self, v):
        self.levels.append(v)


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
        self.e.hub, self.e.pill = FakeWindow(), FakePill()
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
            [("tool_calls", [{"function": {"name": "list_files", "arguments": {}}}])],
            [("delta", "Done, "), ("delta", "reminder added.")],
        ])
        seen = []
        def fake_stream(url, model, msgs, tools_, **kw):
            seen.append([m["role"] for m in msgs])
            return iter(next(rounds))
        with tempfile.TemporaryDirectory() as ws, mock.patch.object(app.tools, "WORKSPACE", Path(ws)), \
                mock.patch.object(core, "ollama_chat_stream", fake_stream):
            self.e.chat([{"role": "user", "content": "what files do I have"}])
        self.assertEqual(seen[1][-2:], ["assistant", "tool"])          # tool result fed back to the model
        self.assertEqual(self.e.history.list()[0]["reply"], "Done, reminder added.")
        self.assertTrue(self.events("chat_done"))

    def test_reminder_confirms_without_second_model_pass(self):
        calls = []
        def fake_stream(*a, **kw):
            calls.append(1)
            return iter([("tool_calls", [{"function": {"name": "add_reminder", "arguments": {"date": "2026-10-13", "time": "09:00", "text": "Send invoice"}}}])])
        with tempfile.TemporaryDirectory() as ws, mock.patch.object(app.tools, "WORKSPACE", Path(ws)), \
                mock.patch.object(core, "ollama_chat_stream", fake_stream):
            self.e.chat([{"role": "user", "content": "kal 9 baje invoice reminder"}])
            self.assertIn("- 2026-10-13 09:00 Send invoice", (Path(ws) / "reminders.md").read_text())
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.e.history.list()[0]["reply"], "Reminder set: 2026-10-13 09:00 Send invoice")

    def cloud(self):
        self.e.settings.update(cloud_key="k", cloud_url="https://api.example/v1", cloud_model="m")

    def test_cloud_runs_browser_steps_and_keeps_raw_messages(self):
        self.cloud()
        turns = iter([
            {"role": "assistant", "content": "", "extra_content": {"sig": "x"},
             "tool_calls": [{"id": "c1", "function": {"name": "browser_open", "arguments": '{"url": "news.ycombinator.com"}'}}]},
            {"role": "assistant", "content": "Top story is about Awaaz."},
        ])
        sent_msgs = []
        def fake_cloud(url, key, model, msgs, tools_, **kw):
            sent_msgs.append(list(msgs))
            return next(turns)
        fake_browser = types.SimpleNamespace(run=lambda name, args: f"PAGE {name} {args['url']}")
        self.e.browser = fake_browser
        with mock.patch.object(core, "cloud_chat", fake_cloud):
            self.e.chat([{"role": "user", "content": "HN pe top story kya hai"}])
        self.assertEqual(self.e.history.list()[0]["reply"], "Top story is about Awaaz.")
        second = sent_msgs[1]
        self.assertEqual(second[-2]["extra_content"], {"sig": "x"})        # provider extras sent back
        self.assertEqual(second[-1], {"role": "tool", "tool_call_id": "c1", "content": "PAGE browser_open news.ycombinator.com"})

    def test_cloud_rate_limit_message(self):
        self.cloud()
        def limited(*a, **k):
            raise urllib.error.HTTPError("u", 429, "slow down", {}, io.BytesIO(b"quota"))
        with mock.patch.object(core, "cloud_chat", limited):
            self.e.chat([{"role": "user", "content": "find flights"}])
        self.assertIn("rate limit", self.events("chat_error")[-1])

    def test_cloud_offline_falls_back_to_local(self):
        self.cloud()
        def offline(*a, **k):
            raise urllib.error.URLError("no internet")
        with mock.patch.object(core, "cloud_chat", offline), \
                mock.patch.object(core, "ollama_chat_stream", lambda *a, **k: iter([("delta", "local answer")])):
            self.e.chat([{"role": "user", "content": "hello"}])
        self.assertEqual(self.e.history.list()[0]["reply"], "local answer")

    def test_quick_commands_never_reach_the_cloud(self):
        self.cloud()
        def must_not(*a, **k):
            raise AssertionError("cloud called")
        with mock.patch.object(core, "cloud_chat", must_not), mock.patch.object(app.tools.webbrowser, "open", lambda u: None):
            self.e.chat([{"role": "user", "content": "YouTube kholo"}])
        self.assertEqual(self.e.history.list()[0]["reply"], "Opened https://www.youtube.com")

    def test_cloud_look_at_screen_sends_image_and_memory_in_prompt(self):
        self.cloud()
        turns = iter([{"role": "assistant", "content": "", "tool_calls": [{"id": "s1", "function": {"name": "look_at_screen", "arguments": "{}"}}]},
                      {"role": "assistant", "content": "It's a Python error."}])
        sent_msgs = []
        def fake_cloud(url, key, model, msgs, tools_, **kw):
            sent_msgs.append(list(msgs))
            return next(turns)
        shot = {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AA"}}]}
        with mock.patch.object(core, "cloud_chat", fake_cloud), mock.patch.object(app.tools, "memories", lambda: "- Name is Jitendra"), \
                mock.patch.object(self.e, "screenshot_message", lambda: shot):
            self.e.chat([{"role": "user", "content": "mere screen pe kya hai"}])
        self.assertIn("Name is Jitendra", sent_msgs[0][0]["content"])
        self.assertEqual(sent_msgs[1][-1], shot)                         # image follows the tool result
        self.assertEqual(sent_msgs[1][-2]["role"], "tool")

    def test_new_chat_stops_a_long_task(self):
        self.cloud()
        calls = []
        def looping(*a, **k):
            calls.append(1)
            self.e.cancel = True                                          # owner pressed New chat mid-task
            return {"role": "assistant", "content": "", "tool_calls": [{"id": "x", "function": {"name": "list_tasks", "arguments": "{}"}}]}
        with mock.patch.object(core, "cloud_chat", looping):
            self.e.chat([{"role": "user", "content": "do 20 things"}])
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.e.history.list()[0]["reply"], "Stopped.")
        self.assertFalse(self.e.busy)

    def test_risky_actions_need_the_owners_yes(self):
        self.cloud()
        ran = []
        def turns():
            yield {"role": "assistant", "content": "", "tool_calls": [{"id": "r", "function": {"name": "run_command", "arguments": '{"command": "Remove-Item *"}'}}]}
            yield {"role": "assistant", "content": "Okay, not done."}
        for answer in (False, True):
            it = turns()
            ch = app.Channel(lambda t: None, lambda q: answer)
            with mock.patch.object(core, "cloud_chat", lambda *a, **k: next(it)), \
                    mock.patch.object(app.integrations, "run", lambda n, a: ran.append(a["command"]) or "Exit code 0"):
                self.e.builtin_reply([{"role": "user", "content": "clean up"}], ch)
        self.assertEqual(ran, ["Remove-Item *"])                     # only the approved run happened

    def test_telegram_private_and_answers_owner(self):
        self.e.settings.update(telegram_token="T", telegram_user="111")
        sent = []
        batches = iter([[{"update_id": 1, "message": {"chat": {"id": 9}, "from": {"id": 222}, "text": "hi"}},
                         {"update_id": 2, "message": {"chat": {"id": 5}, "from": {"id": 111}, "text": "YouTube kholo"}}]])
        def fake_updates(token, offset):
            try:
                return next(batches)
            except StopIteration:
                raise SystemExit                                      # end the poll loop for the test
        with mock.patch.object(app.telegram, "updates", fake_updates), \
                mock.patch.object(app.telegram, "send", lambda t, c, text: sent.append((c, text))), \
                mock.patch.object(app.telegram, "typing", lambda *a: None), \
                mock.patch.object(app.tools.webbrowser, "open", lambda u: None), \
                mock.patch.object(threading, "Thread", lambda target, args, daemon: types.SimpleNamespace(start=lambda: target(*args))):
            with self.assertRaises(SystemExit):
                self.e.telegram_loop()
        self.assertIn("This Awaaz is private", sent[0][1])
        self.assertIn("222", sent[0][1])                              # stranger only learns their own id
        self.assertEqual(sent[1], (5, "Opened https://www.youtube.com"))
        self.assertEqual(self.e.history.list()[0]["text"], "[Phone] YouTube kholo")

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

    def test_close_previous_copy_only_kills_python(self):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd[0])
            out = "notepad.exe 4242" if cmd[0] == "tasklist" else ""
            return types.SimpleNamespace(stdout=out)
        pid = Path(self.tmp.name) / "awaaz.pid"
        pid.write_text("4242")
        with mock.patch.object(app.subprocess, "run", fake_run):
            app.close_previous_copy(pid)
        self.assertEqual(calls, ["tasklist"])                    # not python -> left alone
        self.assertEqual(pid.read_text(), str(app.os.getpid()))

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
        self.assertEqual(self.e.pill.states[-1], "idle")          # 0.05 s tap ignored
        api = app.Api(self.e)
        self.assertFalse(api.send_chat("not a list"))
        self.assertEqual(json.loads(json.dumps(api.get_bootstrap()))["stats"]["words_total"], 0)


if __name__ == "__main__":
    unittest.main()
