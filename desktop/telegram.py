"""Minimal Telegram Bot API client (stdlib). Long polling, so no public server or open port is needed."""
import json
import secrets
import urllib.parse
import urllib.request

API = "https://api.telegram.org"


def call(token, method, http_timeout=40, **params):
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    with urllib.request.urlopen(f"{API}/bot{token}/{method}", data=data, timeout=http_timeout) as r:
        out = json.load(r)
    if not out.get("ok"):
        raise OSError(out.get("description", "Telegram error"))
    return out["result"]


def updates(token, offset):
    # Telegram holds the request up to 30 s until a message arrives (long polling).
    return call(token, "getUpdates", http_timeout=45, offset=offset, timeout=30, allowed_updates='["message"]')


def send(token, chat_id, text):
    for i in range(0, max(len(text), 1), 4000):      # Telegram's limit is 4096 characters per message
        call(token, "sendMessage", chat_id=chat_id, text=text[i:i + 4000] or "(empty)")


def typing(token, chat_id):
    try:
        call(token, "sendChatAction", chat_id=chat_id, action="typing")
    except OSError:
        pass


def download(token, file_id, dest):
    path = call(token, "getFile", file_id=file_id)["file_path"]
    with urllib.request.urlopen(f"{API}/file/bot{token}/{path}", timeout=60) as r:
        dest.write_bytes(r.read())
    return dest


def send_photo(token, chat_id, path):
    """multipart/form-data upload, built by hand to avoid a dependency."""
    boundary = secrets.token_hex(16)
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{path.name}\"\r\n"
            "Content-Type: image/png\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{API}/bot{token}/sendPhoto", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        r.read()
