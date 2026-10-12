"""Awaaz Desktop core: settings, history, text cleanup and agent client. Stdlib only, OS-independent."""
import json
import os
import re
import threading
import time
import urllib.request
import uuid
from pathlib import Path

APP_DIR = Path(os.getenv("AWAAZ_HOME") or Path(os.getenv("APPDATA") or Path.home()) / "Awaaz")

DEFAULTS = {
    "dictate_hotkey": "right ctrl",
    "agent_hotkey": "right alt",
    "whisper_model": "small",          # tiny | base | small | medium
    "language": "auto",                # auto | en | hi
    "remove_fillers": True,
    "polish_with_ai": False,           # rewrite dictation with the local model (slower on CPU)
    "speak_replies": True,
    "agent_engine": "builtin",         # builtin = direct to Ollama (fast) | hermes = full Hermes agent in WSL
    "agent_url": "http://localhost:8642/v1",
    "agent_key": "",
    "ollama_url": "http://localhost:11434/v1",
    "ollama_model": "gemma4:e4b",
    # Optional cloud brain: any OpenAI-compatible API (Gemini, OpenAI, Claude, Groq, OpenRouter...).
    # Empty key = everything stays local.
    "cloud_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "cloud_key": "",
    "cloud_model": "gemini-flash-latest",
    "image_model": "",                 # e.g. gpt-image-1 (OpenAI) or an image model your provider lists
    "google_client_id": "",            # Gmail + Calendar: your own Google OAuth "Desktop app" client
    "google_client_secret": "",
    "telegram_token": "",              # phone chat: bot token from @BotFather
    "telegram_user": "",               # the only Telegram user id the bot answers
    "dictionary": {"hermes": "Hermes", "awaz": "Awaaz", "olama": "Ollama"},
}

LOG = Path(__file__).parent / "logs" / "awaaz.log"


def log(msg):
    """Append a timestamped line to desktop/logs/awaaz.log (kept small: trimmed past 1 MB)."""
    try:
        LOG.parent.mkdir(exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 1_000_000:
            LOG.write_text(LOG.read_text(encoding="utf-8", errors="replace")[-200_000:], encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")
    except OSError:
        pass


FILLERS = re.compile(r"\b(?:um+|uh+|er+|erm|hmm+|uhm+)\b[,.]?\s*", re.I)


def load_settings(path=None):
    path = Path(path or APP_DIR / "settings.json")
    s = json.loads(json.dumps(DEFAULTS))
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            saved = {}
        for k, v in saved.items():
            if k in DEFAULTS and type(v) is type(DEFAULTS[k]):
                s[k] = v
    return s


def save_settings(settings, path=None):
    path = Path(path or APP_DIR / "settings.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: settings[k] for k in DEFAULTS if k in settings and type(settings[k]) is type(DEFAULTS[k])}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic, so a crash never leaves half-written settings
    return load_settings(path)


def clean_text(text, dictionary=None, remove_fillers=True):
    """Tidy raw transcription: fillers out, custom words fixed, spacing and first letter."""
    t = text.strip()
    if remove_fillers:
        t = FILLERS.sub("", t)
    for wrong, right in (dictionary or {}).items():
        t = re.sub(rf"\b{re.escape(wrong)}\b", right, t, flags=re.I)
    t = re.sub(r"\s+([,.!?])", r"\1", re.sub(r"\s{2,}", " ", t)).strip()
    return t[:1].upper() + t[1:] if t else t


def strip_markdown(text):
    """Plain text for speaking aloud."""
    t = re.sub(r"```.*?```", " code block ", text, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s{0,3}(#{1,6}|[-*+]|\d+\.)\s+", "", t, flags=re.M)
    t = re.sub(r"[*_~>|]", "", t)
    return re.sub(r"\s+", " ", t).strip()


class History:
    """Append-only JSONL log of dictations and agent turns."""

    def __init__(self, path=None):
        self.path = Path(path or APP_DIR / "history.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _read(self):
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # skip a corrupt line rather than lose the whole history
        return out

    def add(self, mode, text, audio_secs=0.0, reply=""):
        entry = {"id": uuid.uuid4().hex[:12], "ts": time.time(), "mode": mode, "text": text,
                 "words": len(text.split()), "secs": round(audio_secs, 2), "reply": reply}
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def list(self, limit=200, query=""):
        items = self._read()[::-1]
        if query:
            q = query.lower()
            items = [e for e in items if q in e["text"].lower() or q in e.get("reply", "").lower()]
        return items[:limit]

    def _rewrite(self, items):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in items), encoding="utf-8")
        tmp.replace(self.path)

    def delete(self, entry_id):
        with self._lock:
            self._rewrite([e for e in self._read() if e["id"] != entry_id])

    def clear(self):
        with self._lock:
            self._rewrite([])

    def stats(self, now=None):
        items = self._read()
        now = now or time.time()
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        dict_items = [e for e in items if e["mode"] == "dictate"]
        words = sum(e["words"] for e in dict_items)
        secs = sum(e["secs"] for e in dict_items)
        wpm = round(words / secs * 60) if secs else 0
        typing_secs = words / 40 * 60  # 40 wpm average typing speed
        return {
            "words_total": words,
            "words_today": sum(e["words"] for e in dict_items
                               if time.strftime("%Y-%m-%d", time.localtime(e["ts"])) == today),
            "wpm": wpm,
            "minutes_saved": max(0, round((typing_secs - secs) / 60)),
            "agent_turns": sum(1 for e in items if e["mode"] == "agent"),
        }


def _post(url, payload, key="", timeout=300):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key or 'local'}"})
    return urllib.request.urlopen(req, timeout=timeout)


def chat_stream(base_url, key, messages, model="hermes-agent", timeout=600):
    """Yield text deltas from an OpenAI-compatible streaming chat endpoint (Hermes API server)."""
    with _post(base_url.rstrip("/") + "/chat/completions",
               {"model": model, "messages": messages, "stream": True}, key, timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
            except (ValueError, KeyError, IndexError):
                continue
            if delta:
                yield delta


def cloud_chat(url, key, model, messages, tools=None, timeout=120):
    """One non-streaming turn against an OpenAI-compatible API. Returns the assistant message dict
    (kept whole, so provider extras such as Gemini's thought signatures go back on the next turn)."""
    payload = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools
    if "generativelanguage.googleapis.com" in url:
        payload["reasoning_effort"] = "low"     # Gemini: less thinking per step, much faster agent loops
    with _post(url.rstrip("/") + "/chat/completions", payload, key, timeout) as r:
        msg = json.load(r)["choices"][0]["message"]
    msg.setdefault("content", "")
    msg["content"] = msg["content"] or ""
    return msg


def ollama_root(url):
    """'http://localhost:11434/v1' -> 'http://localhost:11434' (native API lives at the root)."""
    return re.sub(r"/v1/?$", "", url.rstrip("/"))


# Same options for warm-up and chat: a different num_ctx makes Ollama reload the whole model.
OLLAMA_OPTIONS = {"num_ctx": 4096, "temperature": 0.3}


def ollama_chat_stream(url, model, messages, tools=None, timeout=600, max_tokens=None):
    """Stream Ollama's native chat. Yields ('delta', text) and ('tool_calls', [...]).

    think=False skips the model's long hidden reasoning; keep_alive keeps it loaded between
    questions; a 4k context keeps prompt processing quick on a CPU.
    """
    options = dict(OLLAMA_OPTIONS, **({"num_predict": max_tokens} if max_tokens else {}))
    payload = {"model": model, "messages": messages, "stream": True, "think": False,
               "keep_alive": "30m", "options": options}
    if tools:
        payload["tools"] = tools
    with _post(ollama_root(url) + "/api/chat", payload, timeout=timeout) as r:
        for raw in r:
            try:
                chunk = json.loads(raw)
            except ValueError:
                continue
            if chunk.get("error"):
                raise OSError(chunk["error"])
            msg = chunk.get("message") or {}
            if msg.get("tool_calls"):
                yield "tool_calls", msg["tool_calls"]
            if msg.get("content"):
                yield "delta", msg["content"]
            if chunk.get("done"):
                return


def ollama_has_model(url, model, timeout=3):
    with urllib.request.urlopen(ollama_root(url) + "/api/tags", timeout=timeout) as r:
        names = {m.get("name") for m in json.load(r).get("models", [])}
    return model in names or f"{model}:latest" in names


def ollama_warm(url, model, timeout=600):
    """Load the model into memory now so the first question is fast."""
    with _post(ollama_root(url) + "/api/generate",
               {"model": model, "keep_alive": "30m", "options": OLLAMA_OPTIONS}, timeout=timeout) as r:
        r.read()


def ollama_pull(url, model, timeout=3600):
    """Download a model through Ollama (used when Settings names one that isn't installed)."""
    with _post(ollama_root(url) + "/api/pull", {"model": model, "stream": False}, timeout=timeout) as r:
        r.read()


def polish(base_url, model, text, timeout=120):
    """Rewrite dictation into clean prose with the local model; returns original text on any failure."""
    prompt = ("Clean up this dictated text: fix punctuation and grammar, remove repetitions, keep the "
              "speaker's language (English, Hindi or Hinglish) and meaning. Reply with the text only.\n\n" + text)
    try:
        with _post(ollama_root(base_url) + "/v1/chat/completions",
                   {"model": model, "temperature": 0, "reasoning_effort": "none",
                    "messages": [{"role": "user", "content": prompt}]},
                   timeout=timeout) as r:
            out = json.load(r)["choices"][0]["message"]["content"].strip()
        out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
        return out or text
    except (OSError, ValueError, KeyError, IndexError):
        return text
