"""Tools the built-in agent can call. Everything is confined to the AgentWork folder."""
import datetime as dt
import importlib.util
import json
import os
import re
import urllib.parse
import webbrowser
from pathlib import Path

import core

WORKSPACE = Path(os.getenv("BRAVO_WORKSPACE") or r"C:\AgentWork")
_BRIEF = Path(__file__).resolve().parents[1] / "skills" / "daily-brief" / "brief.py"

SITES = {"youtube": "https://www.youtube.com", "gmail": "https://mail.google.com", "google": "https://www.google.com",
         "whatsapp": "https://web.whatsapp.com", "linkedin": "https://www.linkedin.com", "github": "https://github.com",
         "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai", "maps": "https://maps.google.com",
         "calendar": "https://calendar.google.com", "drive": "https://drive.google.com", "amazon": "https://www.amazon.in"}
# Allowlist: the model can only start these, never an arbitrary program or command.
APPS = {"chrome": "chrome.exe", "edge": "msedge.exe", "notepad": "notepad.exe", "calculator": "calc.exe",
        "file explorer": "explorer.exe", "explorer": "explorer.exe", "paint": "mspaint.exe", "word": "winword.exe",
        "excel": "excel.exe", "powerpoint": "powerpnt.exe", "settings": "ms-settings:", "agentwork": str(WORKSPACE)}

SPECS = [
    {"type": "function", "function": {
        "name": "daily_brief",
        "description": "Reminders due and files changed today.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "add_reminder",
        "description": "Add a reminder.",
        "parameters": {"type": "object", "required": ["date", "text"], "properties": {
            "date": {"type": "string", "description": "Due date as YYYY-MM-DD"},
            "time": {"type": "string", "description": "Optional time as HH:MM, 24-hour"},
            "text": {"type": "string", "description": "What to do"}}}}},
    {"type": "function", "function": {
        "name": "open_website",
        "description": "Open a website in the browser.",
        "parameters": {"type": "object", "required": ["url"], "properties": {
            "url": {"type": "string", "description": "Full URL or a site name like youtube or gmail"}}}}},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search Google or YouTube in the browser.",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string"},
            "site": {"type": "string", "enum": ["google", "youtube"]}}}}},
    {"type": "function", "function": {
        "name": "open_app",
        "description": "Open a desktop app: " + ", ".join(sorted(APPS)) + ".",
        "parameters": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List AgentWork files, newest first.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file in AgentWork.",
        "parameters": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string", "description": "File name or relative path inside AgentWork"}}}}},
]


def _safe(name):
    """Resolve a path inside the workspace or raise; blocks ../ and absolute paths."""
    p = (WORKSPACE / str(name)).resolve()
    if p != WORKSPACE.resolve() and WORKSPACE.resolve() not in p.parents:
        raise ValueError("That file is outside the AgentWork folder.")
    return p


def daily_brief(today=None):
    spec = importlib.util.spec_from_file_location("bravo_brief", _BRIEF)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    return mod.brief(WORKSPACE, 24, today=today)


def add_reminder(date, text, time=""):
    dt.date.fromisoformat(str(date))                     # raises on a bad date
    text = re.sub(r"\s+", " ", str(text)).strip()
    if not text:
        raise ValueError("Reminder text is empty.")
    if time and not re.fullmatch(r"\d{2}:\d{2}", str(time)):
        raise ValueError("Time must be HH:MM.")
    line = f"- {date} {time + ' ' if time else ''}{text}"
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    path = WORKSPACE / "reminders.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Reminders\n"
    path.write_text(existing.rstrip("\n") + "\n" + line + "\n", encoding="utf-8")
    return f"Added: {line[2:]}"


def open_website(url):
    url = str(url).strip()
    key = url.lower().removesuffix(".com").strip()
    url = SITES.get(key) or (url if re.match(r"https?://", url, re.I) else "https://" + url)
    if not re.fullmatch(r"https?://[\w.-]+\.[a-z]{2,}(/\S*)?", url, re.I):
        raise ValueError(f"Not a website: {url}")
    webbrowser.open(url)
    return f"Opened {url}"


def web_search(query, site="google"):
    q = urllib.parse.quote_plus(str(query))
    url = (f"https://www.youtube.com/results?search_query={q}" if site == "youtube"
           else f"https://www.google.com/search?q={q}")
    webbrowser.open(url)
    return f"Searched {'YouTube' if site == 'youtube' else 'Google'} for {query}"


def open_app(name):
    target = APPS.get(str(name).lower().strip())
    if not target:
        raise ValueError(f"I can open: {', '.join(sorted(APPS))}.")
    os.startfile(target)  # Windows shell finds chrome.exe, winword.exe etc. via App Paths
    return f"Opened {name}"


def list_files():
    if not WORKSPACE.exists():
        return "AgentWork folder is empty."
    files = sorted((p for p in WORKSPACE.rglob("*") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    return "\n".join(str(p.relative_to(WORKSPACE)) for p in files[:50]) or "AgentWork folder is empty."


def read_file(name):
    p = _safe(name)
    if not p.is_file():
        return f"No file named {name} in AgentWork."
    return p.read_text(encoding="utf-8", errors="replace")[:20000]


FUNCS = {"daily_brief": daily_brief, "add_reminder": add_reminder, "open_website": open_website,
         "web_search": web_search, "open_app": open_app, "list_files": list_files, "read_file": read_file}


# ---------- cloud-only tools (each extra tool slows the CPU model, so the local brain keeps the short list)
MEMORY = core.APP_DIR / "memory.md"
TASKS = core.APP_DIR / "tasks.json"
ALERTED = core.APP_DIR / "alerted.json"
REPEATS = ("none", "daily", "weekdays", "weekly")

CLOUD_SPECS = [
    {"type": "function", "function": {
        "name": "remember",
        "description": "Save a lasting fact or preference about the owner (name, work, people, likes) for future chats.",
        "parameters": {"type": "object", "required": ["fact"], "properties": {"fact": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "forget",
        "description": "Delete saved memories that contain this text.",
        "parameters": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create a text file in AgentWork (notes, drafts, lists). overwrite=true only after the owner agreed.",
        "parameters": {"type": "object", "required": ["name", "text"], "properties": {
            "name": {"type": "string"}, "text": {"type": "string"}, "overwrite": {"type": "boolean"}}}}},
    {"type": "function", "function": {
        "name": "read_clipboard",
        "description": "Read the text the owner last copied.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "copy_to_clipboard",
        "description": "Put text on the owner's clipboard so they can paste it anywhere.",
        "parameters": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "schedule_task",
        "description": "Run an instruction for the owner later, once or repeating (e.g. every weekday 09:00 'give me my brief and top AI news').",
        "parameters": {"type": "object", "required": ["at", "prompt"], "properties": {
            "at": {"type": "string", "description": "First run, local time YYYY-MM-DD HH:MM"},
            "repeat": {"type": "string", "enum": list(REPEATS)},
            "prompt": {"type": "string", "description": "What to do, written as the owner would ask it"}}}}},
    {"type": "function", "function": {
        "name": "list_tasks",
        "description": "List scheduled tasks.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "cancel_task",
        "description": "Cancel a scheduled task by its id.",
        "parameters": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}}},
]


def memories():
    return MEMORY.read_text(encoding="utf-8").strip() if MEMORY.exists() else ""


def remember(fact):
    fact = re.sub(r"\s+", " ", str(fact)).strip()
    if not fact:
        raise ValueError("Nothing to remember.")
    MEMORY.parent.mkdir(parents=True, exist_ok=True)
    with MEMORY.open("a", encoding="utf-8") as f:
        f.write(f"- {fact}\n")
    return f"Remembered: {fact}"


def forget(text):
    lines = memories().splitlines()
    keep = [l for l in lines if str(text).lower() not in l.lower()]
    MEMORY.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    return f"Forgot {len(lines) - len(keep)} memory line(s)."


def write_file(name, text, overwrite=False):
    p = _safe(name)
    if p.exists() and not overwrite:
        raise ValueError(f"{name} already exists. Ask the owner before overwriting it.")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(text), encoding="utf-8")
    return f"Saved {p.relative_to(WORKSPACE)} in AgentWork."


def read_clipboard():
    import pyperclip
    return pyperclip.paste()[:20000] or "The clipboard is empty."


def copy_to_clipboard(text):
    import pyperclip
    pyperclip.copy(str(text))
    return "Copied to the clipboard."


def _tasks():
    try:
        return json.loads(TASKS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_tasks(items):
    TASKS.parent.mkdir(parents=True, exist_ok=True)
    tmp = TASKS.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(TASKS)


def schedule_task(at, prompt, repeat="none"):
    when = dt.datetime.strptime(str(at).strip()[:16].replace("T", " "), "%Y-%m-%d %H:%M")
    if repeat not in REPEATS:
        raise ValueError(f"repeat must be one of {', '.join(REPEATS)}")
    items = _tasks()
    task = {"id": f"t{int(dt.datetime.now().timestamp())}{len(items)}", "at": when.isoformat(timespec="minutes"),
            "repeat": repeat, "prompt": str(prompt).strip()}
    _save_tasks(items + [task])
    return f"Scheduled {task['id']}: {task['prompt']} at {when:%Y-%m-%d %H:%M}" + ("" if repeat == "none" else f", {repeat}")


def list_tasks():
    items = _tasks()
    return "\n".join(f"{t['id']}: {t['at'].replace('T', ' ')} ({t['repeat']}) {t['prompt']}" for t in items) or "No scheduled tasks."


def cancel_task(id):
    items = _tasks()
    keep = [t for t in items if t["id"] != id]
    _save_tasks(keep)
    return "Cancelled." if len(keep) < len(items) else f"No task {id}."


def _next(when, repeat, now):
    step = {"daily": 1, "weekdays": 1, "weekly": 7}[repeat]
    while when <= now or (repeat == "weekdays" and when.weekday() > 4):
        when += dt.timedelta(days=step)   # missed runs while the PC was off are skipped, not replayed
    return when


def due_tasks(now=None):
    """Prompts whose time has come; one-off tasks are removed, repeating ones move to their next run."""
    now = now or dt.datetime.now()
    due, keep = [], []
    for t in _tasks():
        when = dt.datetime.fromisoformat(t["at"])
        if when <= now:
            due.append(t["prompt"])
            if t["repeat"] == "none":
                continue
            t["at"] = _next(when, t["repeat"], now).isoformat(timespec="minutes")
        keep.append(t)
    if due:
        _save_tasks(keep)
    return due


def due_reminders(now=None):
    """Timed reminders (- YYYY-MM-DD HH:MM text) that just came due, each announced once, within 12 hours."""
    now = now or dt.datetime.now()
    path = WORKSPACE / "reminders.md"
    if not path.exists():
        return []
    try:
        done = set(json.loads(ALERTED.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        done = set()
    out = []
    for m in re.finditer(r"^- (\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+(.+)$", path.read_text(encoding="utf-8"), re.M):
        when = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
        if m.group(0) not in done and now - dt.timedelta(hours=12) <= when <= now:
            out.append(m.group(2).strip())
            done.add(m.group(0))
    if out:
        ALERTED.parent.mkdir(parents=True, exist_ok=True)
        ALERTED.write_text(json.dumps(sorted(done)[-500:]), encoding="utf-8")
    return out


FUNCS.update(remember=remember, forget=forget, write_file=write_file, read_clipboard=read_clipboard,
             copy_to_clipboard=copy_to_clipboard, schedule_task=schedule_task, list_tasks=list_tasks,
             cancel_task=cancel_task)

# Actions whose result already says what happened, so the agent replies without a second model pass.
ACTIONS = {"add_reminder", "open_website", "web_search", "open_app"}
OPEN_RE = re.compile(r"^\s*(?:please\s+)?(?:open|launch|start|khol(?:o|na|\s+do)?)\s+(?:the\s+|my\s+)?(.+?)\s*$"
                     r"|^\s*(?:please\s+)?(?:my\s+)?(.+?)\s+(?:khol(?:o|\s+do|na)?|open\s+karo|chalao)\s*$", re.I)


def quick(text):
    """'open youtube' / 'notepad kholo' -> instant tool run without the model; None if not that simple."""
    m = OPEN_RE.match(text.strip(" .!?"))
    name = (m.group(1) or m.group(2)).lower().strip() if m else ""
    name = re.sub(r"\s+(app|website|site)$", "", name)
    if name in APPS:
        return run("open_app", {"name": name})
    if name.removesuffix(".com") in SITES or re.fullmatch(r"[\w-]+\.[a-z]{2,}", name):
        return run("open_website", {"url": name})
    return None


def run(name, args):
    """Run a tool call from the model; always returns text (errors included) so the model can recover."""
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            args = {}
    fn = FUNCS.get(name)
    if not fn:
        return f"Unknown tool {name}."
    try:
        return str(fn(**{k: v for k, v in (args or {}).items() if k in fn.__code__.co_varnames}))
    except (ValueError, TypeError, OSError) as e:
        return f"Error: {e}"
