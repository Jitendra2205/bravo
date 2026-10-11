"""python -m unittest discover eval  — no model or network needed."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_eval  # noqa: E402
import stt_eval  # noqa: E402

CANNED = {"Extract": '```json\n{"name": "Kavya Traders", "date": "2026-10-03", "amount": 18450}\n```',
          "Bhai": "225"}


class FakeOllama(BaseHTTPRequestHandler):
    def do_POST(self):
        prompt = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["messages"][0]["content"]
        text = next((v for k, v in CANNED.items() if prompt.startswith(k)), "no idea")
        body = json.dumps({"choices": [{"message": {"content": text}}],
                           "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Checks(unittest.TestCase):
    def test_checks(self):
        self.assertEqual(run_eval.check("See you Monday", {"contains_any": ["monday"], "max_words": 5}), [])
        self.assertIn("over 2 words", run_eval.check("one two three", {"max_words": 2}))
        self.assertIn("invalid json", run_eval.check("nope", {"json_keys": ["a"]}))
        self.assertEqual(run_eval.check('Sure: {"a": 1}', {"json_keys": ["a"]}), [])
        self.assertIn("contains 'tmrw'", run_eval.check("by tmrw", {"not_contains": ["tmrw"]}))

    def test_wer(self):
        self.assertEqual(stt_eval.wer("kal subah invoice bhejo", "Kal subah, invoice bhejo!"), 0.0)
        self.assertAlmostEqual(stt_eval.wer("a b c d", "a x c"), 0.5)
        self.assertEqual(stt_eval.wer("नमस्ते दोस्त", "नमस्ते दोस्त"), 0.0)


class EndToEnd(unittest.TestCase):
    def test_run_against_fake_server(self):
        server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        os.environ["LOCAL_BASE_URL"] = f"http://127.0.0.1:{server.server_port}/v1"
        tasks = json.loads((Path(__file__).parent / "tasks.json").read_text(encoding="utf-8"))["tasks"]
        picked = [t for t in tasks if t["id"] in ("s1", "h4", "w1")]
        with tempfile.TemporaryDirectory() as d:
            rows, path = run_eval.run("local", picked, Path(d))
            self.assertTrue(path.exists())
        server.shutdown()
        server.server_close()
        result = {r["id"]: r["passed"] for r in rows}
        self.assertEqual(result, {"s1": True, "h4": True, "w1": False})
        self.assertIn("| all | 2/3 |", run_eval.summary(rows))


if __name__ == "__main__":
    unittest.main()
