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


if __name__ == "__main__":
    unittest.main()
