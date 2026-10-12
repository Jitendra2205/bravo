"""python -m unittest discover desktop — runs anywhere, no mic or GUI needed."""
import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core  # noqa: E402


class FakeHermes(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        if body.get("stream"):
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for chunk in ["Na", "mas", "te"]:
                self.wfile.write(f'data: {json.dumps({"choices": [{"delta": {"content": chunk}}]})}\n\n'.encode())
            self.wfile.write(b"data: {bad json}\n\ndata: [DONE]\n\n")
        else:
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": "<think>x</think>Clean text."}}]}).encode())

    def log_message(self, *a):
        pass


class Core(unittest.TestCase):
    def test_log_redacts_secrets(self):
        import tempfile
        from unittest import mock
        log = Path(tempfile.mkdtemp()) / "a.log"
        with mock.patch.object(core, "LOG", log):
            core.log("url https://api.telegram.org/bot123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawx/getUpdates "
                     "key AIzaSyD-1234567890abcdefghijklm sk-proj-abcdefghijklmnop1234 Bearer ya29.abc.def ok")
        text = log.read_text()
        self.assertNotIn("AAHdq", text); self.assertNotIn("AIzaSy", text); self.assertNotIn("sk-proj", text)
        self.assertNotIn("ya29", text); self.assertIn("ok", text)

    def test_old_awaaz_data_is_copied_once(self):
        import tempfile
        from unittest import mock
        root = Path(tempfile.mkdtemp())
        (root / "Awaaz").mkdir()
        (root / "Awaaz" / "settings.json").write_text('{"cloud_model": "m"}')
        with mock.patch.object(core, "APP_DIR", root / "Bravo"), mock.patch.object(core, "OLD_APP_DIR", root / "Awaaz"), \
                mock.patch.dict("os.environ", {}, clear=False) as env:
            env.pop("BRAVO_HOME", None)
            core.migrate_old_data()
            self.assertEqual(core.load_settings(root / "Bravo" / "settings.json")["cloud_model"], "m")
            (root / "Awaaz" / "settings.json").write_text('{"cloud_model": "changed"}')
            core.migrate_old_data()                                   # never overwrites Bravo's own settings
            self.assertEqual(core.load_settings(root / "Bravo" / "settings.json")["cloud_model"], "m")
        self.assertTrue((root / "Awaaz").is_dir())                    # old folder kept

    def test_clean_text(self):
        d = {"hermes": "Hermes"}
        self.assertEqual(core.clean_text("um so uh open hermes , please", d), "So open Hermes, please")
        self.assertEqual(core.clean_text("", d), "")
        self.assertEqual(core.clean_text("umbrella is fine"), "Umbrella is fine")  # 'um' inside a word stays

    def test_strip_markdown(self):
        self.assertEqual(core.strip_markdown("## Hi\n- **one** [link](http://x)\n`code`"), "Hi one link code")

    def test_settings_roundtrip_and_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            s = core.save_settings({**core.DEFAULTS, "whisper_model": "base", "speak_replies": "yes", "junk": 1}, p)
            self.assertEqual(s["whisper_model"], "base")
            self.assertTrue(s["speak_replies"])           # wrong type ignored, default kept
            self.assertNotIn("junk", s)
            p.write_text("{not json", encoding="utf-8")
            self.assertEqual(core.load_settings(p), core.DEFAULTS)  # corrupt file falls back

    def test_history(self):
        with tempfile.TemporaryDirectory() as d:
            h = core.History(Path(d) / "h.jsonl")
            a = h.add("dictate", "one two three four", 2.0)
            h.add("agent", "what is due", 1.0, reply="Rent")
            with h.path.open("a") as f:
                f.write("corrupt line\n")
            self.assertEqual(len(h.list()), 2)
            self.assertEqual(h.list(query="rent")[0]["mode"], "agent")
            st = h.stats()
            self.assertEqual((st["words_total"], st["wpm"], st["agent_turns"]), (4, 120, 1))
            h.delete(a["id"])
            self.assertEqual([e["mode"] for e in h.list()], ["agent"])
            h.clear()
            self.assertEqual(h.list(), [])

    def test_chat_stream_and_polish(self):
        srv = HTTPServer(("127.0.0.1", 0), FakeHermes)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_port}/v1"
        try:
            self.assertEqual("".join(core.chat_stream(url, "k", [{"role": "user", "content": "hi"}])), "Namaste")
            self.assertEqual(core.polish(url, "m", "raw"), "Clean text.")
            self.assertEqual(core.polish("http://127.0.0.1:1/v1", "m", "raw", timeout=1), "raw")  # offline -> unchanged
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
