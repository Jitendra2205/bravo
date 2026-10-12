"""Floating Wispr Flow-style status pill, drawn with tkinter (bundled with Windows Python).

Runs its own Tk thread; other threads talk to it only through a queue.
"""
import queue
import threading
import tkinter as tk

KEY = "#010203"   # pixels in this colour are made see-through, which gives the pill its rounded ends
BG, INK, MUTED = "#161412", "#f4f1ec", "#a39d93"
ACCENT = {"dictate": "#fb923c", "agent": "#a78bfa"}
STATE_COLOR = {"done": "#4ade80", "error": "#f87171", "idle": "#6b665e"}
LABELS = {
    ("listening", "dictate"): "Dictating", ("listening", "agent"): "Ask Bravo",
    ("working", "dictate"): "Transcribing", ("working", "agent"): "Thinking",
    ("done", "dictate"): "Pasted", ("done", "agent"): "Reply ready",
    ("error", "dictate"): "Something went wrong", ("error", "agent"): "Something went wrong",
}
BARS = 14


def label_for(state, mode, text=""):
    """Main label for a state (pure, so it can be tested without a display)."""
    if text:
        return text
    if state == "idle":
        return "Bravo"
    return LABELS.get((state, mode), "")


def hint_for(state, sub=""):
    if sub:
        return sub
    return {"listening": "release to finish", "idle": "hold your key to talk"}.get(state, "")


class Pill:
    W, H = 320, 36

    def __init__(self):
        self.q = queue.Queue()
        self.levels = [0.0] * BARS
        self.state = ("idle", "dictate", "", "")
        self.tick = 0
        threading.Thread(target=self._run, daemon=True, name="pill").start()

    # ---- thread-safe API
    def set_state(self, state, mode="dictate", text="", sub=""):
        self.q.put(("state", (state, mode, text, sub)))

    def set_level(self, value):
        self.q.put(("level", float(value)))

    # ---- Tk thread
    def _run(self):
        self.root = r = tk.Tk()
        r.overrideredirect(True)                 # no title bar, never in the taskbar
        r.attributes("-topmost", True)
        try:
            r.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass                                  # non-Windows: square corners, still works
        r.configure(bg=KEY)
        x = (r.winfo_screenwidth() - self.W) // 2
        y = r.winfo_screenheight() - self.H - 64  # just above the taskbar
        r.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self.c = tk.Canvas(r, width=self.W, height=self.H, bg=KEY, highlightthickness=0)
        self.c.pack()
        r.after(40, self._pump)
        r.mainloop()

    def _pump(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "state":
                    self.state = val
                    if val[0] != "listening":
                        self.levels = [0.0] * BARS
                else:
                    self.levels = self.levels[1:] + [min(1.0, val * 6)]
        except queue.Empty:
            pass
        self.tick += 1
        self._draw()
        self.root.after(40, self._pump)

    def _draw(self):
        c, W, H = self.c, self.W, self.H
        state, mode, text, sub = self.state
        accent = STATE_COLOR.get(state) or ACCENT.get(mode, ACCENT["dictate"])
        c.delete("all")
        c.create_oval(0, 0, H, H, fill=BG, outline=BG)
        c.create_oval(W - H, 0, W, H, fill=BG, outline=BG)
        c.create_rectangle(H / 2, 0, W - H / 2, H, fill=BG, outline=BG)
        x, mid = 18, H / 2
        pulse = state in ("listening", "working") and (self.tick // 8) % 2
        r = 4 if pulse else 5
        c.create_oval(x - r, mid - r, x + r, mid + r, fill=accent, outline=accent)
        x += 14
        if state == "listening":
            for lv in self.levels:
                h = 3 + lv * 18
                c.create_rectangle(x, mid - h / 2, x + 3, mid + h / 2, fill=accent, outline=accent)
                x += 6
            x += 6
        label = label_for(state, mode, text)
        item = c.create_text(x, mid, text=label, anchor="w", fill=INK if state != "idle" else MUTED,
                             font=("Segoe UI", 10, "bold"))
        hint = hint_for(state, sub)
        if hint:
            x2 = c.bbox(item)[2] + 8
            c.create_text(x2, mid, text=hint, anchor="w", fill=MUTED, font=("Segoe UI", 9))
