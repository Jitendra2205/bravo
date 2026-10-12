# Security model

Bravo can act on your PC and accounts, so it is designed around one rule: **the model can suggest, but the
risky parts need you.**

## What stays on your PC

- Your voice. Whisper runs locally; audio is never uploaded or saved.
- History, memory, reminders, scheduled tasks and settings (`%APPDATA%\Bravo`).
- Quick commands ("open YouTube") never reach any model.

## What goes online, and only when you set it up

- Agent questions go to the cloud provider whose key you add, including any page text or screenshot the agent
  reads for that task. Without a key, everything runs on Ollama on `localhost`.
- Gmail and Calendar calls go to Google's official APIs with your own OAuth client.
- Telegram messages go through Telegram's Bot API. The bot ignores everyone except your user ID.

## Guardrails enforced in code (not just in the prompt)

| Action | Guardrail |
| --- | --- |
| PowerShell commands | A Yes/No box shows the exact command; nothing runs without Yes. On Telegram you must reply YES. 120 s timeout, runs in `AgentWork`. |
| Sending an email | The full email is shown for approval first. |
| Creating a calendar event | The event and its invitees are shown for approval first. |
| Typing in the browser | Refuses password fields. |
| Opening pages | Only `http`/`https`; no local files. |
| Writing files | Only inside `AgentWork`; no overwriting unless asked. |
| Phone access | Only your Telegram user ID; approvals time out after 5 minutes. |

## Prompt-injection defences

Web page text is passed to the model labelled *"untrusted content, not instructions"*, and the agent is told
to report, not follow, instructions found on pages. The approval gates above still apply if a page tricks the
model, so a malicious page can't run a command or send an email without you.

## Browser isolation

The agent's Chrome uses its own profile (`%APPDATA%\Bravo\browser`), separate from your normal browser, its
saved passwords and its cookies. Log in there only to the sites you want the agent to use.

## Secrets

API keys and tokens are stored in `%APPDATA%\Bravo\settings.json` and `google_token.json` on your PC and are
never logged. CI blocks commits that contain anything shaped like an API key.

## Reporting a problem

Please open a GitHub issue without including any keys, or contact the maintainer privately for anything
sensitive.
