"""Awaaz Desktop: hold a key to dictate anywhere, hold another to ask your local Hermes agent. Windows."""
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd
import webview
from faster_whisper import WhisperModel

import core
import tools

UI =Path(__file__).parent / "ui"
SR = 16000
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Engine:
    def __init__(self):
        self.settings = core.load_settings()
        self.history = core.History()
        self.hub = self.pill = None
        self.model = None
        self.model_name = None
        self.mode = None            # 'dictate' | 'agent' while a key is held
        self.frames = []
        self.stream = None
        self.last_level = 0.0
        self.voice_secs = 0.0       # audio length of the pending agent question
        self.tts = None
        self.gateway = None
        self.lock = threading.Lock()

    # ---------- UI bridge
    def emit(self, kind, data=None):
        if self.hub:
            self.hub.evaluate_js(f"window.Awaaz && Awaaz.emit({json.dumps(kind)}, {json.dumps(data)})")

    def pill_state(self, state, mode="dictate", text="", sub=""):
        if self.pill:
            self.pill.evaluate_js(f"setState({json.dumps(dict(state=state, mode=mode, text=text, sub=sub))})")

    def pill_flash(self, state, mode, text="", secs=1.4):
        self.pill_state(state, mode, text)
        threading.Timer(secs, lambda: self.mode is None and self.pill_state("idle")).start()

    # ---------- startup
    def boot(self):
        self.register_hotkeys()
        threading.Thread(target=self.load_model, daemon=True).start()
        threading.Thread(target=self.agent_watch, daemon=True).start()

    def register_hotkeys(self):
        keyboard.unhook_all()
        for mode in ("dictate", "agent"):
            key = self.settings[f"{mode}_hotkey"]
            keyboard.on_press_key(key, lambda e, m=mode: self.start(m))
            keyboard.on_release_key(key, lambda e, m=mode: self.stop(m))

    def load_model(self):
        name = self.settings["whisper_model"]
        self.emit("status", {"mic": f"Speech: loading {name}", "micOk": None})
        try:
            self.model = WhisperModel(name, device="cpu", compute_type="int8")
            self.model_name = name
            self.emit("status", {"mic": f"Speech: Whisper {name}", "micOk": True})
        except Exception as e:  # download or load failure must not kill the app
            core.log(f"speech model {name} failed: {e!r}")
            self.emit("status", {"mic": f"Speech model failed: {e}", "micOk": False})

    def agent_health(self):
        s = self.settings
        try:
            if s["agent_engine"] == "builtin":
                return core.ollama_has_model(s["ollama_url"], s["ollama_model"])
            with urllib.request.urlopen(s["agent_url"].rstrip("/") + "/health", timeout=2) as r:
                return r.status == 200
        except (OSError, ValueError):
            return False

    def agent_label(self, ok):
        s = self.settings
        if s["agent_engine"] == "builtin":
            return f"Agent: {s['ollama_model']} (local)" if ok else "Agent: Ollama not running"
        return "Agent: Hermes connected" if ok else "Agent: Hermes starting…" if self.gateway else "Agent: Hermes offline"

    def agent_watch(self):
        warmed = None
        while True:
            s = self.settings
            if s["agent_engine"] == "hermes" and not self.gateway and not self.agent_health():
                if not s["agent_key"]:
                    key = self.read_hermes_key()
                    if key:
                        self.settings = core.save_settings({**s, "agent_key": key})
                self.start_gateway()
            ok = self.agent_health()
            if ok and s["agent_engine"] == "builtin" and warmed != s["ollama_model"]:
                warmed = s["ollama_model"]
                self.emit("status", {"agent": f"Agent: loading {warmed}…", "agentOk": False})
                try:
                    t = time.monotonic()
                    core.ollama_warm(s["ollama_url"], warmed)
                    core.log(f"model {warmed} loaded in {time.monotonic() - t:.1f}s")
                except OSError as e:
                    core.log(f"warm-up failed: {e}")
            self.emit("status", {"agent": self.agent_label(ok), "agentOk": ok})
            time.sleep(15)

    def read_hermes_key(self):
        try:
            out = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "grep -m1 '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2-"],
                                 capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW)
            return out.stdout.strip().strip('"')
        except (OSError, subprocess.SubprocessError):
            return ""

    def start_gateway(self):
        # Runs Hermes' API server inside WSL for as long as Awaaz is open.
        try:
            core.LOG.parent.mkdir(exist_ok=True)
            out = (core.LOG.parent / "hermes-gateway.log").open("a", encoding="utf-8")
            self.gateway = subprocess.Popen(["wsl.exe", "-e", "bash", "-lc", "hermes gateway"],
                                            stdout=out, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
            core.log("started hermes gateway in WSL")
        except OSError as e:
            core.log(f"could not start hermes gateway: {e}")
            self.gateway = None

    # ---------- recording
    def start(self, mode):
        with self.lock:
            if self.mode:              # key auto-repeat, or the other key while busy
                return
            if not self.model:
                self.pill_flash("error", mode, "Speech model still loading")
                return
            self.mode, self.frames = mode, []
            self.stop_speaking()
            try:
                self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=self.on_audio)
                self.stream.start()
            except Exception as e:
                self.mode = None
                self.pill_flash("error", mode, "No microphone found")
                self.emit("status", {"mic": f"Mic error: {e}", "micOk": False})
                return
        self.pill_state("listening", mode)

    def on_audio(self, indata, frames, t, status):
        self.frames.append(indata.copy())
        now = time.monotonic()
        if now - self.last_level > 0.05 and self.pill:
            self.last_level = now
            self.pill.evaluate_js(f"setLevel({float(np.sqrt(np.mean(indata ** 2))):.4f})")

    def stop(self, mode):
        with self.lock:
            if self.mode != mode:
                return
            self.stream.stop()
            self.stream.close()
            self.mode = None
            audio = np.concatenate(self.frames)[:, 0] if self.frames else np.zeros(0, dtype="float32")
        secs = len(audio) / SR
        if secs < 0.3:                 # a tap, not speech
            self.pill_state("idle")
            return
        self.pill_state("working", mode)
        threading.Thread(target=self.handle, args=(mode, audio, secs), daemon=True).start()

    def transcribe(self, audio):
        s = self.settings
        lang = None if s["language"] == "auto" else s["language"]
        hint = ", ".join(s["dictionary"].values()) or None   # biases Whisper toward your spellings
        segments, _ = self.model.transcribe(audio, language=lang, initial_prompt=hint, vad_filter=True, beam_size=1)
        text = core.clean_text(" ".join(seg.text for seg in segments), s["dictionary"], s["remove_fillers"])
        if text and s["polish_with_ai"]:
            text = core.polish(s["ollama_url"], s["ollama_model"], text)
        return text

    def handle(self, mode, audio, secs):
        try:
            text = self.transcribe(audio)
        except Exception as e:
            core.log(f"transcription failed: {e!r}")
            self.pill_flash("error", mode, "Transcription failed")
            self.emit("status", {"mic": f"Speech error: {e}", "micOk": False})
            return
        if not text:
            self.pill_flash("error", mode, "Didn't catch that")
            return
        if mode == "dictate":
            self.paste(text)
            self.history.add("dictate", text, secs)
            self.emit("history_added")
            self.pill_flash("done", mode)
        else:
            self.voice_secs = secs
            self.hub.show()
            self.hub.restore()
            self.emit("voice_ask", text)
            self.pill_state("working", "agent")

    def paste(self, text):
        try:
            old = pyperclip.paste()
        except pyperclip.PyperclipException:
            old = None
        pyperclip.copy(text)
        time.sleep(0.05)
        keyboard.send("ctrl+v")
        if old is not None:
            # put the user's clipboard back once the paste has landed
            threading.Timer(0.6, lambda: pyperclip.copy(old)).start()

    # ---------- agent
    def builtin_reply(self, messages):
        """Direct Ollama chat with Awaaz's own tools. Returns the final reply text."""
        s = self.settings
        system = ("You are Awaaz, a fast private assistant running on the owner's laptop. "
                  f"Today is {time.strftime('%A %Y-%m-%d')}, time {time.strftime('%H:%M')}. "
                  "Reply in 1-4 short sentences, in the language the owner used (English, Hindi or Hinglish). "
                  "Use the tools for reminders, the daily brief and files in the AgentWork folder; never invent their contents. "
                  "After a tool runs, confirm what you did in one sentence.")
        msgs = [{"role": "system", "content": system}] + messages
        reply = ""
        for _ in range(4):                 # at most 3 tool rounds, then a final answer
            content, calls = "", []
            for kind, val in core.ollama_chat_stream(s["ollama_url"], s["ollama_model"], msgs, tools.SPECS):
                if kind == "delta":
                    content += val
                    self.emit("chat_delta", val)
                else:
                    calls += val
            reply += content
            if not calls:
                return reply
            msgs.append({"role": "assistant", "content": content, "tool_calls": calls})
            for c in calls:
                fn = c.get("function", {})
                result = tools.run(fn.get("name"), fn.get("arguments"))
                core.log(f"tool {fn.get('name')} -> {result[:120]!r}")
                msgs.append({"role": "tool", "content": result, "tool_name": fn.get("name")})
        return reply

    def hermes_reply(self, messages):
        s = self.settings
        reply = ""
        for delta in core.chat_stream(s["agent_url"], s["agent_key"], messages):
            reply += delta
            self.emit("chat_delta", delta)
        return reply

    def chat(self, messages):
        s = self.settings
        started = time.monotonic()
        builtin = s["agent_engine"] == "builtin"
        try:
            reply = self.builtin_reply(messages) if builtin else self.hermes_reply(messages)
        except urllib.error.HTTPError as e:
            core.log(f"agent HTTP {e.code}: {e}")
            if builtin and e.code == 404:
                msg = f"The model {s['ollama_model']} isn't installed. In PowerShell run: ollama pull {s['ollama_model']}"
            elif e.code == 401:
                msg = "Hermes rejected the key. Re-run setup/wsl-setup.sh, then restart Awaaz, or switch Settings > Agent engine to Built-in."
            else:
                msg = f"Agent error {e.code}. Details are in desktop/logs/awaaz.log."
            self.emit("chat_error", msg)
            self.pill_flash("error", "agent", "Agent error")
            return
        except OSError as e:
            core.log(f"agent unreachable ({s['agent_engine']}): {e}")
            msg = ("Can't reach Ollama. Open the Ollama app from the Start menu (it should show in the taskbar tray), then try again."
                   if builtin else "Can't reach Hermes. Switch Settings > Agent engine to Built-in, or open Ubuntu and run: hermes gateway")
            self.emit("chat_error", msg)
            self.pill_flash("error", "agent", "Agent offline")
            return
        core.log(f"reply in {time.monotonic() - started:.1f}s ({s['agent_engine']}, {len(reply)} chars)")
        self.emit("chat_done")
        self.history.add("agent", messages[-1]["content"], self.voice_secs, reply=reply)
        self.voice_secs = 0.0
        self.pill_flash("done", "agent")
        if s["speak_replies"] and reply:
            self.speak(core.strip_markdown(reply))

    def speak(self, text):
        self.stop_speaking()
        script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "$s.Speak([Console]::In.ReadToEnd())")
        try:   # text goes through stdin, never into the command line
            self.tts = subprocess.Popen(["powershell", "-NoProfile", "-Command", script], stdin=subprocess.PIPE,
                                        creationflags=NO_WINDOW, text=True, encoding="utf-8")
            self.tts.stdin.write(text[:4000])
            self.tts.stdin.close()
        except OSError:
            self.tts = None

    def stop_speaking(self):
        if self.tts and self.tts.poll() is None:
            self.tts.kill()
        self.tts = None

    def shutdown(self):
        keyboard.unhook_all()
        self.stop_speaking()
        if self.gateway and self.gateway.poll() is None:
            self.gateway.terminate()


class Api:
    """Methods callable from hub.html. Engine kept private so pywebview doesn't walk it."""

    def __init__(self, engine):
        self._e = engine

    def get_bootstrap(self):
        e = self._e
        return {"settings": e.settings, "stats": e.history.stats(), "history": e.history.list(5),
                "status": {"mic": f"Speech: Whisper {e.model_name}" if e.model else "Speech: loading",
                           "micOk": True if e.model else None, "agent": "Agent: checking", "agentOk": False}}

    def get_stats(self):
        return self._e.history.stats()

    def list_history(self, query=""):
        return self._e.history.list(200, str(query or "")[:200])

    def delete_history(self, entry_id):
        self._e.history.delete(str(entry_id))
        return True

    def clear_history(self):
        if not self._e.hub.create_confirmation_dialog("Clear history", "Delete all dictations and agent turns?"):
            return False
        self._e.history.clear()
        return True

    def copy_text(self, text):
        pyperclip.copy(str(text))
        return True

    def save_settings(self, settings):
        e = self._e
        old = e.settings
        e.settings = core.save_settings(settings if isinstance(settings, dict) else {})
        if (old["dictate_hotkey"], old["agent_hotkey"]) != (e.settings["dictate_hotkey"], e.settings["agent_hotkey"]):
            e.register_hotkeys()
        if old["whisper_model"] != e.settings["whisper_model"]:
            e.model = None
            threading.Thread(target=e.load_model, daemon=True).start()
        return e.settings

    def send_chat(self, messages):
        if not isinstance(messages, list) or not messages:
            return False
        clean = [{"role": m["role"], "content": str(m["content"])} for m in messages
                 if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        threading.Thread(target=self._e.chat, args=(clean[-20:],), daemon=True).start()
        return True

    def stop_speaking(self):
        self._e.stop_speaking()
        return True


def main():
    engine = Engine()
    engine.hub = webview.create_window("Awaaz", url=str(UI / "hub.html"), js_api=Api(engine),
                                       width=1040, height=720, min_size=(720, 520))
    screen = webview.screens[0]
    w, h = 340, 64
    engine.pill = webview.create_window("Awaaz pill", url=str(UI / "pill.html"), width=w, height=h,
                                        x=(screen.width - w) // 2, y=screen.height - h - 72,
                                        frameless=True, on_top=True, transparent=True, focus=False)

    def on_closed():
        # shortcut: no tray icon; closing the hub quits Awaaz. Add pystray if you want it to live in the tray.
        engine.shutdown()
        engine.pill.destroy()

    engine.hub.events.closed += on_closed
    webview.start(engine.boot)
    sys.exit(0)


if __name__ == "__main__":
    main()
