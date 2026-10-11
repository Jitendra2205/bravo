# Case study: a private voice agent for $0

_Draft. Fill the bracketed parts with your real numbers and experience._

## The problem
I wanted an always-on assistant I could talk to: reminders, drafts, file work, a morning brief.
The leading options in late 2026 — ChatGPT dots and Grok Bot — cost $100+ a month, run in their cloud,
and my dictation app (Wispr Flow) is another subscription that sends my voice to a server.

## Constraints
- A 16 GB Windows laptop, CPU only [update if you have a GPU]
- $0 running cost
- Nothing leaves the laptop by default
- Safe enough that a wrong command can't damage my files

## Options considered
| Option | Why not (or why) |
| --- | --- |
| ChatGPT dots / Grok Bot | Best capability, but $100+/month and cloud-only |
| Wispr Flow | Excellent dictation incl. Hinglish, but paid and cloud |
| Build an agent from scratch | Months of work for what open source already does |
| Existing one-click installers (5 found) | Duplicating them adds nothing; none hardened by default |
| **Hermes Agent + Ollama + Whisper, hardened and measured** | Chosen: free, local, voice built in; my work goes into security, custom skills and evaluation |

## Key decisions
1. **WSL2 + Docker sandbox** instead of native Windows: the agent can only see one folder.
2. **One ~8B model** (`gemma4:e4b`) instead of the biggest that loads: 16 GB is shared with Windows and Whisper.
3. **Cloud models off by default**, enabled per task only when local fails.
4. **Measure before claiming:** 30 real tasks, local vs cloud; 30 voice clips, local Whisper vs Wispr Flow.

## Results
[Paste the tables printed by `eval/run_eval.py` and `eval/stt_eval.py`.]

- Where local was good enough: [e.g. rewriting, summaries, extraction]
- Where it fell short: [e.g. long multi-step tasks, Hinglish transcription vs Wispr Flow]
- Cost: $0 local vs $[x] for the same run in the cloud

## What I'd do next
[e.g. move to a mini PC for always-on, add one more skill, contribute a Hinglish voice guide upstream]
