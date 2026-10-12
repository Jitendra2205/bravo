"""Integrations with Google, Telegram and the image API faked out."""
import base64
import email
import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import integrations  # noqa: E402
import telegram      # noqa: E402
import tools         # noqa: E402


class FakeResp:
    def __init__(self, obj):
        self.obj = obj
    def __enter__(self):
        return self
    def __exit__(self, *a):
        pass
    def read(self):
        return json.dumps(self.obj).encode()


class IntegrationsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.p = [mock.patch.object(tools, "WORKSPACE", self.tmp / "ws"),
                  mock.patch.object(integrations, "GOOGLE_TOKEN", self.tmp / "tok.json")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_run_command_uses_powershell_in_agentwork(self):
        seen = {}
        def fake_run(cmd, **kw):
            seen.update(cmd=cmd, cwd=kw["cwd"])
            return types.SimpleNamespace(returncode=0, stdout="42\n", stderr="")
        with mock.patch.object(integrations.subprocess, "run", fake_run):
            self.assertEqual(integrations.run("run_command", {"command": "6*7"}), "Exit code 0\n42")
        self.assertEqual(seen["cmd"][0], "powershell")
        self.assertEqual(seen["cwd"], self.tmp / "ws")

    def test_not_connected_message(self):
        self.assertIn("Connect", integrations.run("gmail_search", {"query": "is:unread"}))

    def test_token_refresh_then_gmail_send(self):
        integrations.GOOGLE_TOKEN.write_text(json.dumps({"access_token": "old", "refresh_token": "r", "expires_at": 0,
                                                         "client_id": "c", "client_secret": "s"}))
        sent = {}
        def fake_urlopen(req, timeout=0):
            sent["auth"] = req.headers["Authorization"]
            sent["body"] = json.loads(req.data)
            return FakeResp({"id": "m1"})
        with mock.patch.object(integrations, "_form", lambda url, data: {"access_token": "new", "expires_in": 3600}), \
                mock.patch.object(integrations.urllib.request, "urlopen", fake_urlopen):
            self.assertEqual(integrations.run("gmail_send", {"to": "a@b.c", "subject": "Hi", "body": "Namaste"}), "Email sent to a@b.c.")
        self.assertEqual(sent["auth"], "Bearer new")
        msg = email.message_from_bytes(base64.urlsafe_b64decode(sent["body"]["raw"]))
        self.assertEqual((msg["To"], msg["Subject"], msg.get_payload().strip()), ("a@b.c", "Hi", "Namaste"))
        self.assertGreater(json.loads(integrations.GOOGLE_TOKEN.read_text())["expires_at"], time.time())

    def test_email_body_prefers_plain_text(self):
        b64 = lambda t: base64.urlsafe_b64encode(t.encode()).decode()
        payload = {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/html", "body": {"data": b64("<p>Hello <b>there</b></p>")}},
            {"mimeType": "text/plain", "body": {"data": b64("Hello there")}}]}
        self.assertEqual(integrations._body(payload), "Hello there")
        self.assertEqual(integrations._body({"mimeType": "text/html", "body": {"data": b64("<p>Hi <b>you</b></p>")}}), "Hi you")

    def test_calendar_create_invites_only_with_attendees(self):
        calls = []
        with mock.patch.object(integrations, "_google", lambda m, url, body=None: calls.append((url, body)) or {}):
            integrations.run("calendar_create", {"title": "Demo", "start": "2026-10-14 15:00"})
            integrations.run("calendar_create", {"title": "Sync", "start": "2026-10-14 16:00", "attendees": "a@x.com, b@y.com"})
        self.assertTrue(calls[0][0].endswith("sendUpdates=none"))
        self.assertEqual(calls[1][1]["attendees"], [{"email": "a@x.com"}, {"email": "b@y.com"}])
        self.assertEqual(calls[0][1]["end"]["dateTime"][11:16], "16:00")      # default 1 hour

    def test_google_sign_in_loopback_flow(self):
        import threading, urllib.parse, urllib.request
        def fake_browser(url):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
            self.assertIn("gmail.send", q["scope"])
            self.assertEqual(q["code_challenge_method"], "S256")
            back = f"{q['redirect_uri']}/?code=abc&state={q['state']}"
            threading.Thread(target=lambda: urllib.request.urlopen(back, timeout=5).read()).start()
        exchanged = {}
        def fake_form(url, data):
            exchanged.update(data)
            return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}
        with mock.patch.object(integrations.webbrowser, "open", fake_browser), mock.patch.object(integrations, "_form", fake_form), \
                mock.patch.dict("os.environ", {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
            self.assertEqual(integrations.google_connect("cid", "sec", timeout=20), "Google connected.")
        self.assertEqual((exchanged["code"], exchanged["client_id"]), ("abc", "cid"))
        self.assertEqual(json.loads(integrations.GOOGLE_TOKEN.read_text())["refresh_token"], "r")

    def test_generate_image_saves_png(self):
        s = {"image_model": "img", "cloud_url": "https://api.x/v1", "cloud_key": "k"}
        png = b"\x89PNG fake"
        with mock.patch.object(integrations.core, "_post", lambda *a, **k: FakeResp({"data": [{"b64_json": base64.b64encode(png).decode()}]})):
            path = integrations.generate_image("A chai cup at sunrise", s)
        self.assertEqual(path.read_bytes(), png)
        self.assertTrue(path.name.endswith("-a-chai-cup-at-sunrise.png"))
        with self.assertRaises(ValueError):
            integrations.generate_image("x", {**s, "image_model": ""})


class TelegramClientTest(unittest.TestCase):
    def test_long_messages_are_split(self):
        sent = []
        with mock.patch.object(telegram, "call", lambda *a, **k: sent.append(k["text"])):
            telegram.send("t", 1, "x" * 9000)
        self.assertEqual([len(t) for t in sent], [4000, 4000, 1000])


if __name__ == "__main__":
    unittest.main()
