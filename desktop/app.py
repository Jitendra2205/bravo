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

UI = Path(__file__).parent / "ui"
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
            self.emit("status", {"mic": f"Speech model failed: {e}", "micOk": False})

    def agent_health(self):
        url = self.settings["agent_url"].rstrip("/") + "/health"
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return r.status == 200
        except OSError:
            return False

    def agent_watch(self):
        if not self.settings["agent_key"]:
            key = self.read_hermes_key()
            if key:
                self.settings = core.save_settings({**self.settings, "agent_key": key})
        if not self.agent_health():
            self.start_gateway()
        while True:
            ok = self.agent_health()
            self.emit("status", {"agent": "Agent: connected" if ok else "Agent: offline (starting…)" if self.gateway else "Agent: offline", "agentOk": ok})
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
            self.gateway = subprocess.Popen(["wsl.exe", "-e", "bash", "-lc", "hermes gateway"],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        except OSError:
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
    def chat(self, messages):
        s = self.settings
        reply = ""
        try:
            for delta in core.chat_stream(s["agent_url"], s["agent_key"], messages):
                reply += delta
                self.emit("chat_delta", delta)
        except urllib.error.HTTPError as e:
            msg = "Agent key rejected. Re-run setup/wsl-setup.sh, then restart Awaaz." if e.code == 401 else f"Agent error {e.code}."
            self.emit("chat_error", msg)
            self.pill_flash("error", "agent", "Agent error")
            return
        except OSError:
            self.emit("chat_error", "Can't reach your agent yet. It starts with Awaaz; wait a few seconds and try again. "
                                    "If it keeps failing, open Ubuntu and run: hermes gateway")
            self.pill_flash("error", "agent", "Agent offline")
            return
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
