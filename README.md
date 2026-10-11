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

1. **Windows side** (PowerShell): `powershell -ExecutionPolicy Bypass -File setup\windows-setup.ps1`
   — checks the machine, installs Ollama, pulls the model, creates `C:\AgentWork`, installs WSL2.
2. **WSL side** (Ubuntu shell, after the restart): `bash setup/wsl-setup.sh`
   — installs Hermes from the official script, points it at local Ollama, installs the skills and persona.
3. **Dictation:** install Handy from its official GitHub releases and pick a local Whisper model.
4. **Lock it down:** walk through [config/SECURITY-PRESET.md](config/SECURITY-PRESET.md).

## Repo map

| Path | What it is |
| --- | --- |
| `setup/` | Windows and WSL setup scripts |
| `config/` | Agent persona and the security preset |
| `skills/daily-brief/` | Custom skill: morning summary of reminders and changed files |
| `eval/` | Task-level and speech-to-text evaluation harness |
| `site/`, `render.yaml` | Case-study page on Render's free static hosting |
| `docs/` | Case-study draft and demo video script |

## License

MIT for the code in this repo. Third-party projects keep their own licences — see [NOTICE.md](NOTICE.md).
