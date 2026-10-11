---
name: daily-brief
description: Morning summary of the owner's reminders (overdue, today, next 7 days) and files changed in the workspace in the last day. Use when the owner asks for their brief, their day, or what's due.
---

# Daily brief

1. Run the helper; it reads only the workspace and prints a Markdown brief:

   ```bash
   python3 ~/.hermes/skills/daily-brief/brief.py --workspace /mnt/c/AgentWork --hours 24
   ```

2. Reply with the brief. For a spoken reply, say only the counts and the first two due items,
   then offer to read the rest.
3. Do not edit `reminders.md` unless the owner asks. To add a reminder, append a line in the form
   `- YYYY-MM-DD what to do` and confirm the exact line first.

## Schedule it

Ask Hermes once: "Every weekday at 9 am, run my daily brief and tell me the result."
