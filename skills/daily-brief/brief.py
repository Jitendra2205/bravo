"""Daily brief: due reminders + recently changed files in the workspace. Stdlib only."""
import argparse
import datetime as dt
import re
import sys
import tempfile
import time
from pathlib import Path

LINE = re.compile(r"^\s*[-*]\s+(\d{4}-\d{2}-\d{2})\s+(.+)$")


def reminders(path, today):
    """Split dated reminder lines into overdue / today / next 7 days."""
    groups = {"overdue": [], "today": [], "next 7 days": []}
    if not path.exists():
        return groups
    for line in path.read_text(encoding="utf-8").splitlines():
        m = LINE.match(line)
        if not m:
            continue
        try:
            due = dt.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        item = f"{due.isoformat()}  {m.group(2).strip()}"
        if due < today:
            groups["overdue"].append(item)
        elif due == today:
            groups["today"].append(item)
        elif (due - today).days <= 7:
            groups["next 7 days"].append(item)
    return groups


def changed_files(workspace, hours, now):
    cutoff = now - hours * 3600
    hits = [p for p in workspace.rglob("*") if p.is_file() and p.stat().st_mtime >= cutoff]
    return sorted(str(p.relative_to(workspace)) for p in hits)


def brief(workspace, hours=24, today=None, now=None):
    today = today or dt.date.today()
    now = now or time.time()
    out = [f"# Brief for {today:%A, %d %B %Y}", ""]
    for name, items in reminders(workspace / "reminders.md", today).items():
        out.append(f"**{name.capitalize()}** ({len(items)})")
        out += [f"- {i}" for i in items] or ["- nothing"]
        out.append("")
    files = changed_files(workspace, hours, now)
    out.append(f"**Files changed in the last {hours} h** ({len(files)})")
    out += [f"- {f}" for f in files[:20]] or ["- none"]
    if len(files) > 20:
        out.append(f"- …and {len(files) - 20} more")
    return "\n".join(out)


def self_test():
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d)
        (ws / "reminders.md").write_text(
            "# Reminders\n- 2026-10-10 pay rent\n- 2026-10-11 call Sharma ji\n"
            "- 2026-10-15 send invoice\n- 2026-11-30 far away\n- not a dated line\n- 2026-13-01 bad date\n",
            encoding="utf-8",
        )
        (ws / "notes").mkdir()
        (ws / "notes" / "a.txt").write_text("x")
        text = brief(ws, today=dt.date(2026, 10, 11))
        assert "**Overdue** (1)" in text and "pay rent" in text
        assert "**Today** (1)" in text and "Sharma ji" in text
        assert "**Next 7 days** (1)" in text and "far away" not in text
        assert "notes/a.txt" in text.replace("\\", "/")
    print("self-test passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default="/mnt/c/AgentWork")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        self_test()
        sys.exit(0)
    ws = Path(a.workspace)
    if not ws.is_dir():
        sys.exit(f"Workspace not found: {ws}")
    print(brief(ws, a.hours))
