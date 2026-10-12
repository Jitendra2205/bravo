"""Tools the built-in agent can call. Everything is confined to the AgentWork folder."""
import datetime as dt
import importlib.util
import json
import os
import re
import urllib.parse
import webbrowser
from pathlib import Path

WORKSPACE = Path(os.getenv("AWAAZ_WORKSPACE") or r"C:\AgentWork")
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
    spec = importlib.util.spec_from_file_location("awaaz_brief", _BRIEF)
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
