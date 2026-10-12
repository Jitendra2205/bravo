# Awaaz — a private voice agent that runs on my laptop for $0

I replaced a $100+/month always-on AI agent and a paid dictation app with a system that runs on a
16 GB Windows laptop, works offline, and never sends my data anywhere unless I turn that on.
Then I measured where it holds up and where it doesn't.

> **What I built vs. what I assembled.** The agent framework (Hermes Agent), model runtime (Ollama),
> speech models (Whisper, NeuTTS) and dictation app (Handy) are open-source projects by others.
> I designed the system, chose and secured the stack, wrote the setup scripts, the custom skills
> and the evaluation harness, and ran the comparison. Credits in [NOTICE.md](NOTICE.md).

## What it does

- Talk to it, get spoken replies — fully offline
- Dictate into any Windows app (Wispr Flow-style) with a hotkey
- Remembers context across sessions; runs scheduled jobs like a 9 am brief
- Works on files, reminders and (when I enable them) email, calendar and the browser
- Asks before anything irreversible; every command runs in a sandbox that sees one folder

## Architecture

```
You (voice / hotkey / keyboard)
   │
   ├── Handy ── local Whisper ── types into any Windows app
   │
   └── Hermes Agent (WSL2) ── local Whisper (speech in) / NeuTTS (speech out)
          │      memory, scheduled jobs, approvals
          ├── Ollama on localhost:11434 ── gemma4:e4b
          └── Docker sandbox ── sees only C:\AgentWork

Optional, off by default: Telegram bot (phone access), Claude/Gemini API (hard tasks)
```

## Results

Local vs cloud on 30 of my own tasks, and local speech-to-text vs my own recordings.
Run `eval/` to reproduce; numbers below are filled in by `eval/run_eval.py` and `eval/stt_eval.py`.

| Measure | Local (gemma4:e4b) | Cloud | Notes |
| --- | --- | --- | --- |
| Task success | _pending_ | _pending_ | 30 tasks, automatic checks |
| Median seconds per task | _pending_ | _pending_ | 16 GB laptop, CPU only |
| Cost for the full run | $0 | _pending_ | |
| Voice word error rate (English) | _pending_ | — | 15 clips |
| Voice word error rate (Hinglish) | _pending_ | — | 15 clips |

## Reproduce it

Requirements: Windows 10 22H2+ or 11, 16 GB RAM, ~40 GB free disk.

1. **Windows side:** double-click `setup\Run-Windows-Setup.cmd`
   — checks the machine, installs Ollama, pulls the model, creates `C:\AgentWork`, installs WSL2.
2. **WSL side** (Ubuntu shell, after the restart): `bash setup/wsl-setup.sh`
   — installs Hermes from the official script, points it at local Ollama, installs the skills and persona.
3. **Dictation:** install Handy from its official GitHub releases and pick a local Whisper model.
4. **Lock it down:** walk through [config/SECURITY-PRESET.md](config/SECURITY-PRESET.md).

## Awaaz Desktop (Wispr Flow-style app)

A small Windows app on top of the agent: a floating pill at the bottom of the screen and a hub window.

- **Hold Right Ctrl** anywhere: speak, release, and the text is typed where your cursor is (local Whisper, filler words removed, your custom spellings applied).
- **Hold Right Alt**: ask your agent by voice; the answer streams into the hub and is read aloud with the offline Windows voice.
- **Hub:** stats (words, speaking speed, minutes saved), agent chat, searchable history, a custom dictionary, and settings (hotkeys, speech model, language, AI polish).
- **Instant commands, no model:** "open YouTube", "notepad kholo", "daily brief" run in under a second, fully offline.
- **Local-first, cloud optional:** with no key, the agent runs on Gemma via Ollama. Add any OpenAI-compatible key in Settings (Gemini free tier, Groq, OpenRouter, OpenAI, Claude) and bigger tasks go to that model, which can drive a real browser window: open pages, read them, click and type. Speech, history and quick commands never leave the PC.
- **Agent features (with a cloud key):** remembers facts about you across chats, looks at your screen when asked, writes files in AgentWork, reads and fills your clipboard, schedules tasks ("every weekday 9 AM, top AI news"), and announces timed reminders out loud. New chat stops a long task.
- **Browser guardrails:** it uses its own Chrome profile, never types passwords, labels page text as untrusted, and asks before anything that sends, posts, buys or submits.
- Start it by double-clicking `desktop\Run-Awaaz.cmd`.

## Repo map

| Path | What it is |
| --- | --- |
| `setup/` | Windows and WSL setup scripts |
| `desktop/` | Awaaz Desktop: floating pill, hub UI, hotkeys, local Whisper, agent chat |
| `config/` | Agent persona and the security preset |
| `skills/daily-brief/` | Custom skill: morning summary of reminders and changed files |
| `eval/` | Task-level and speech-to-text evaluation harness |
| `site/`, `render.yaml` | Case-study page on Render's free static hosting |
| `docs/` | Case-study draft and demo video script |

## License

MIT for the code in this repo. Third-party projects keep their own licences — see [NOTICE.md](NOTICE.md).
