"""Tools the built-in agent can call. Everything is confined to the AgentWork folder."""
import datetime as dt
import importlib.util
import json
import os
import re
from pathlib import Path

WORKSPACE = Path(os.getenv("AWAAZ_WORKSPACE") or r"C:\AgentWork")
_BRIEF = Path(__file__).resolve().parents[1] / "skills" / "daily-brief" / "brief.py"

SPECS = [
    {"type": "function", "function": {
        "name": "daily_brief",
        "description": "Get the owner's reminders (overdue, today, next 7 days) and files changed in the last 24 hours.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "add_reminder",
        "description": "Add a reminder. Use when the owner asks to be reminded of something.",
        "parameters": {"type": "object", "required": ["date", "text"], "properties": {
            "date": {"type": "string", "description": "Due date as YYYY-MM-DD"},
            "time": {"type": "string", "description": "Optional time as HH:MM, 24-hour"},
            "text": {"type": "string", "description": "What to do"}}}}},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List files in the owner's AgentWork folder, newest first.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file from the AgentWork folder.",
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


FUNCS = {"daily_brief": daily_brief, "add_reminder": add_reminder, "list_files": list_files, "read_file": read_file}


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
