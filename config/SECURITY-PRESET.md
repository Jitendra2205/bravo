# Security preset

The agent can run commands and touch files, so it gets the least access that still lets it work.
Tick each item after setup; re-check monthly.

## Isolation
- [ ] Agent runs inside WSL2, not directly on Windows
- [ ] Hermes terminal backend set to Docker (Hermes docs → terminal backends), so commands run in a container
- [ ] The only Windows folder the agent uses is `C:\AgentWork` (`/mnt/c/AgentWork` in WSL); no other drives are mounted into the container

## Approvals
- [ ] Command approval is on; no auto-approve or "yolo" mode
- [ ] Test: ask it to delete `C:\AgentWork\test.txt` — it must ask first
- [ ] Persona rules from `config/SOUL.md` are installed at `~/.hermes/SOUL.md`

## Network
- [ ] Ollama listens on localhost only (default). Test from another device on your Wi-Fi: `http://<laptop-ip>:11434` must NOT respond
- [ ] No ports forwarded on the router; no remote dashboard enabled
- [ ] Cloud model keys absent from `~/.hermes/.env` unless deliberately added for hard tasks

## Secrets
- [ ] API keys only in `~/.hermes/.env`, with `chmod 600 ~/.hermes/.env`
- [ ] No keys in skills, prompts, this repo or screenshots (`git grep -i "key\|token"` before every push)

## Browser and accounts
- [ ] Agent uses a separate browser profile with no saved passwords or banking logins
- [ ] Connectors (email, calendar) added one at a time, read-only first

## Optional phone access (Telegram)
- [ ] Bot restricted to your own Telegram user ID
- [ ] Accept that messages pass through Telegram's servers

## Skills and MCP servers
- [ ] Installed only from official sources; code read before enabling
- [ ] Nothing installed that asks for your passwords

## Laptop
- [ ] BitLocker on
- [ ] Windows and `sudo apt upgrade` monthly; `hermes update` and Ollama updates monthly
- [ ] Weekly backup of `~/.hermes` (memory, skills, config)
