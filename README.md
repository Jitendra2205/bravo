<img src="desktop/ui/bravo-logo.svg" alt="Bravo puppy logo" width="96">

# Bravo — a free AI agent that runs on your own PC

Bravo is a personal AI agent that does things for you: it browses the web in a real Chrome window, researches
and reports back, runs scheduled jobs, reads your screen, handles Gmail and Calendar, runs commands on your PC,
makes images, and keeps working while you're away, reachable from your phone.

It is an open-source alternative to always-on agents like **ChatGPT dots** and **Grok Bot**, which come with
plans of $100 a month and up. Bravo runs on a normal Windows laptop (no GPU), costs nothing by default, and
asks before it does anything risky.

Named after my dog, Bravo: loyal, quick, and happy to fetch things for you.

**Talk to it however you like:** type in the app, hold a key and speak (English or Hindi), or message it on
Telegram from your phone. As a bonus, the same hotkey gives you free, private dictation into any app.

- **Free:** the local model, speech recognition and quick commands run on your PC. For faster and smarter
  agent work, plug in any OpenAI-compatible key: a free tier (Groq, Gemini, OpenRouter) or a paid one
  (OpenAI, Claude).
- **Private by default:** history, memory and settings live on your PC. Your voice never leaves it. Nothing goes
  online until you add a cloud key.
- **Safe to hand the keys to:** commands, emails and calendar invites need your Yes every time, enforced in
  code. It never types passwords and treats web pages as untrusted text. See [SECURITY.md](SECURITY.md).

## What it can do

| You ask | What Bravo does | Needs |
| --- | --- | --- |
| "Find the top 3 AI models this week" | Searches in its own Chrome window, reads the pages, answers with what they say | Cloud key |
| "Every weekday at 9, give me the top AI news" | Creates a scheduled job that runs on its own | Cloud key |
| "Summarise my unread emails" / "Add a call tomorrow at 3 pm" | Gmail and Calendar through Google's official sign-in; sends **only after you click Yes** | Cloud key + Google sign-in |
| "How much disk space is free?" | Runs a PowerShell command **after you click Yes** | Cloud key |
| "What's on my screen?" | Looks at your screen and explains it | Cloud key with vision |
| "Remind me to send the invoice tomorrow at 9 am" | Saves the reminder and says it out loud when it's due | Local model or cloud key |
| "Remember that I prefer short answers" | Keeps it in memory across chats | Cloud key |
| "Make an image of a cup of tea at sunrise" | Generates it and saves it to `AgentWork\images` | Key with an image model |
| A message or voice note from your phone | Answered by your PC, wherever you are | Telegram bot token |
| "Open YouTube", "open Notepad", "daily brief" | Done in under a second, no AI model involved | Nothing |
| *(hold Right Ctrl and speak)* | Dictation: typed into whatever app has your cursor | Nothing |

## Quick start (Windows 10/11, 8–16 GB RAM, no GPU needed)

1. Download this repo (green **Code** button → Download ZIP) and unzip it.
2. Double-click `desktop\Run-Bravo.cmd`. The first run installs Python packages (about 300 MB) and starts
   the app.
3. **Make it fast (recommended, free):** get a free key at [console.groq.com](https://console.groq.com/keys),
   then in Bravo go to **Settings → Cloud model**, choose **Groq**, paste the key and press **Save**.
4. **Optional fully offline brain:** install [Ollama](https://ollama.com/download) and Bravo downloads the
   local model (`gemma4:e4b`) by itself. For more speed on older laptops, set the local model to `gemma4:e2b`.

Then give Bravo a task: type it in the **Agent** tab, or hold **Right Alt** and say it. (**Right Ctrl** is dictation.)

## How fast is it?

Measured on the author's laptop (16 GB RAM, CPU only), October 2026:

| Task | Time |
| --- | --- |
| Instant command ("Open YouTube") | 0.4 s |
| Local model loaded, ready to answer | 2 s after start |
| Simple question, local model only | 13–20 s |
| Local model using a tool (e.g. a reminder) | 20–100 s |
| Web research in Chrome (3–4 pages), cloud model | 23–34 s before the latest speed work |

The local model works, but slowly on a CPU, so a free cloud key is the fast path. While it works, the chat
shows each step live ("Opening html.duckduckgo.com…").

## How it works

```
You: type in the app ───┐
     hold a key, speak ─┼─► (speech → text with Whisper, on your PC)
     Telegram message ──┘                      │
                                               ▼
                             instant commands (no model needed)
                                               │
                         cloud key set? ───────┼── yes ─► your provider (Groq, Gemini, OpenAI, Claude…)
                                               │            │  agent tools: Chrome, screen, files, memory,
                                               no           │  schedules, PowerShell*, Gmail*, Calendar*, images
                                               ▼            ▼
                                   Ollama on localhost   * = asks you first, every time
```

- **Desktop app:** Python + pywebview, a floating pill and a hub window (chat, history, dictionary, settings).
- **Browser:** Playwright drives your installed Chrome (or Edge) with a separate Bravo profile, so your
  normal browser, its logins and its passwords are never touched.
- **Phone:** Telegram long polling, so no server and no open port. The bot only answers your user ID.
- **Google:** the official installed-app OAuth flow (PKCE). The token stays on your PC.

## Connect Gmail, Calendar, images and your phone (optional)

**Gmail + Google Calendar** (one-time, about 10 minutes, free):
1. Open console.cloud.google.com and create a project (e.g. "Bravo").
2. APIs & Services → Library: enable **Gmail API** and **Google Calendar API**.
3. APIs & Services → OAuth consent screen: User type **External**, fill in the app name and your email, add
   yourself under **Test users**, then press **Publish app** so sign-in doesn't expire every 7 days. Google
   will warn that the app is unverified; that's expected for a personal app.
4. Credentials → Create credentials → **OAuth client ID** → Application type **Desktop app**. Copy the client
   ID and secret.
5. In Bravo: Settings → Gmail and Google Calendar, paste both and press **Connect Google**.

Scopes used: read Gmail, send Gmail, manage calendar events.

**Images:** set Settings → Image model to a model your provider offers (for example `gpt-image-1` on OpenAI).

**Phone (Telegram):**
1. In Telegram, message **@BotFather**, send `/newbot`, pick a name and copy the token.
2. Paste it in Bravo Settings → Phone and press **Save**.
3. Message your new bot. It replies with your Telegram ID; paste that in **Your Telegram ID** and Save.
4. Text or send voice notes from anywhere. Your PC must be on with Bravo open.

WhatsApp isn't supported: the official API needs a Meta business account and a public server, and unofficial
WhatsApp bots get numbers banned.

## Honest limits

- Windows only for now.
- The local model is slow on a CPU; agent tasks feel snappy only with a cloud key.
- Telegram and scheduled tasks need the PC on with Bravo running.
- Sites with CAPTCHAs or logins may need you to step in. Bravo will never type a password for you.
- Hindi recognition is good but not perfect; add names and brands in **Dictionary**.

## Run the tests

```
cd desktop
.venv\Scripts\python.exe -m unittest
```

## Repo map

| Path | What it is |
| --- | --- |
| `desktop/` | The app: hotkeys, Whisper, agent loop, browser, integrations, Telegram, hub UI, tests |
| `skills/daily-brief/` | Morning summary of reminders and changed files |
| `setup/` | Optional: Windows setup for Ollama, and the WSL setup for the Hermes agent engine |
| `config/` | Agent persona and the security checklist for the Hermes setup |
| `eval/` | Task and speech-to-text evaluation harness |
| `site/` | One-page project site |

## License

MIT. Built on open-source projects that keep their own licences; see [NOTICE.md](NOTICE.md).
