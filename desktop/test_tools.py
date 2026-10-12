"""Agent tools: workspace confinement, reminders, brief, and the real Ollama stream parser."""
import datetime as dt
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import core   # noqa: E402
import tools  # noqa: E402


class FakeOllama(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).last = body
        self.send_response(200)
        self.end_headers()
        if self.path == "/api/chat":
            lines = [{"message": {"tool_calls": [{"function": {"name": "daily_brief", "arguments": {}}}]}, "done": False},
                     {"message": {"content": "Na"}, "done": False}, {"message": {"content": "maste"}, "done": False}, {"done": True}]
            self.wfile.write(b"".join(json.dumps(l).encode() + b"\n" for l in lines))
        else:
            self.wfile.write(b'{"done": true}')

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"models": [{"name": "gemma4:e4b"}]}).encode())

    def log_message(self, *a):
        pass


class Tools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name) / "AgentWork"
        self.ws.mkdir()
        self.p = mock.patch.object(tools, "WORKSPACE", self.ws)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_reminder_and_brief(self):
        self.assertIn("Added", tools.run("add_reminder", '{"date": "2026-10-12", "text": "pay  rent"}'))
        self.assertIn("Error", tools.run("add_reminder", {"date": "12/10/2026", "text": "x"}))
        self.assertIn("Error", tools.run("add_reminder", {"date": "2026-10-12", "time": "9am", "text": "x"}))
        brief = tools.daily_brief(today=dt.date(2026, 10, 12))
        self.assertIn("**Today** (1)", brief)
        self.assertIn("pay rent", brief)

    def test_files_are_confined(self):
        (self.ws / "notes.txt").write_text("hello", encoding="utf-8")
        self.assertEqual(tools.run("read_file", {"name": "notes.txt"}), "hello")
        self.assertIn("outside the AgentWork", tools.run("read_file", {"name": "../secret.txt"}))
        self.assertIn("outside the AgentWork", tools.run("read_file", {"name": str(Path(self.tmp.name) / "x")}))
        self.assertIn("notes.txt", tools.run("list_files", {}))
        self.assertIn("Unknown tool", tools.run("rm_rf", {}))

    def test_ollama_stream_and_settings(self):
        srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_port}/v1"
        try:
            out = list(core.ollama_chat_stream(url, "gemma4:e4b", [{"role": "user", "content": "hi"}], tools.SPECS))
            self.assertEqual(out[0][0], "tool_calls")
            self.assertEqual("".join(v for k, v in out if k == "delta"), "Namaste")
            sent = FakeOllama.last
            self.assertIs(sent["think"], False)                       # no slow hidden reasoning
            self.assertEqual((sent["keep_alive"], sent["options"]["num_ctx"]), ("30m", 4096))
            self.assertTrue(core.ollama_has_model(url, "gemma4:e4b"))
            self.assertFalse(core.ollama_has_model(url, "gemma4:e2b"))
            core.ollama_warm(url, "gemma4:e4b")
            self.assertEqual(FakeOllama.last["options"], sent["options"])   # same ctx: no reload between warm-up and chat
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(core.ollama_root("http://localhost:11434/v1/"), "http://localhost:11434")


class OpenToolsTest(unittest.TestCase):
    def setUp(self):
        self.opened = []
        self.p = [mock.patch.object(tools.webbrowser, "open", self.opened.append),
                  mock.patch.object(tools.os, "startfile", self.opened.append, create=True)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_quick_open_in_english_and_hinglish(self):
        self.assertEqual(tools.quick("Open YouTube"), "Opened https://www.youtube.com")
        self.assertEqual(tools.quick("notepad kholo"), "Opened notepad")
        self.assertEqual(tools.quick("open flipkart.com"), "Opened https://flipkart.com")
        self.assertEqual(self.opened, ["https://www.youtube.com", "notepad.exe", "https://flipkart.com"])

    def test_quick_leaves_real_questions_to_the_model(self):
        self.assertIsNone(tools.quick("open the newest file and summarise it"))
        self.assertIsNone(tools.quick("kal 9 baje reminder lagao"))
        self.assertEqual(self.opened, [])

    def test_search_and_allowlist(self):
        self.assertEqual(tools.run("web_search", {"query": "lofi beats", "site": "youtube"}), "Searched YouTube for lofi beats")
        self.assertEqual(self.opened, ["https://www.youtube.com/results?search_query=lofi+beats"])
        self.assertIn("Error: I can open", tools.run("open_app", {"name": "cmd.exe /c del *"}))
        self.assertIn("Error: Not a website", tools.run("open_website", {"url": "javascript:alert(1)"}))


class AgentFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.p = [mock.patch.object(tools, "MEMORY", self.tmp / "memory.md"),
                  mock.patch.object(tools, "TASKS", self.tmp / "tasks.json"),
                  mock.patch.object(tools, "ALERTED", self.tmp / "alerted.json"),
                  mock.patch.object(tools, "WORKSPACE", self.tmp / "ws")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_memory_remember_and_forget(self):
        tools.run("remember", {"fact": "Prefers  Hinglish replies"})
        tools.run("remember", {"fact": "Works on Parakh"})
        self.assertEqual(tools.memories(), "- Prefers Hinglish replies\n- Works on Parakh")
        self.assertEqual(tools.run("forget", {"text": "parakh"}), "Forgot 1 memory line(s).")
        self.assertEqual(tools.memories(), "- Prefers Hinglish replies")

    def test_write_file_never_overwrites_silently_or_escapes(self):
        self.assertIn("Saved notes/plan.md", tools.run("write_file", {"name": "notes/plan.md", "text": "v1"}))
        self.assertIn("already exists", tools.run("write_file", {"name": "notes/plan.md", "text": "v2"}))
        tools.run("write_file", {"name": "notes/plan.md", "text": "v2", "overwrite": True})
        self.assertEqual((self.tmp / "ws/notes/plan.md").read_text(), "v2")
        self.assertIn("outside the AgentWork", tools.run("write_file", {"name": "../evil.txt", "text": "x"}))

    def test_scheduled_tasks_run_once_or_repeat(self):
        tools.run("schedule_task", {"at": "2026-10-16 09:00", "prompt": "AI news", "repeat": "weekdays"})
        tools.run("schedule_task", {"at": "2026-10-16 18:00", "prompt": "call mom"})
        self.assertEqual(tools.due_tasks(dt.datetime(2026, 10, 16, 8, 59)), [])
        self.assertEqual(tools.due_tasks(dt.datetime(2026, 10, 16, 9, 0)), ["AI news"])   # Friday
        self.assertIn("2026-10-19 09:00 (weekdays) AI news", tools.list_tasks())          # skips the weekend
        self.assertEqual(tools.due_tasks(dt.datetime(2026, 10, 16, 18, 5)), ["call mom"])
        self.assertNotIn("call mom", tools.list_tasks())                                   # one-off removed
        self.assertIn("repeat must be", tools.run("schedule_task", {"at": "2026-10-16 09:00", "prompt": "x", "repeat": "hourly"}))

    def test_timed_reminders_announced_once(self):
        (self.tmp / "ws").mkdir()
        (self.tmp / "ws/reminders.md").write_text("- 2026-10-13 09:00 Invoice bhejna\n- 2026-10-13 Untimed\n- 2026-10-01 09:00 Old one\n")
        now = dt.datetime(2026, 10, 13, 9, 0, 30)
        self.assertEqual(tools.due_reminders(now), ["Invoice bhejna"])
        self.assertEqual(tools.due_reminders(now), [])


if __name__ == "__main__":
    unittest.main()
