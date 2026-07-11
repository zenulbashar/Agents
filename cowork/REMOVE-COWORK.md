# Removing Claude Cowork (and staying 24/7)

Before removing Cowork, confirm the company runs **without** it:

1. **foundryd loaded:** `launchctl list | grep com.foundry.daemon`
2. **n8n up:** `docker ps | grep n8n` (http://127.0.0.1:5678)
3. **Ollama up:** `curl -s http://127.0.0.1:11434/api/tags`
4. **Telegram works:** you got the CEO test message; `/status` replies
5. **Activity logging:** `logs/activity/*.jsonl` is growing
6. **Secrets** are in n8n/Keychain (not in any Cowork file)

If all six pass, quit and uninstall the Claude Desktop app. The agents keep running:

- **24/7 work:** n8n (marketing daemon) + foundryd (agent runtime), both under launchd / `restart: always`.
- **You approve gates and get reports on Telegram** - no desktop needed.
- Supervised deep sessions you used to run in Cowork can later be run by foundryd **headless**
  (Claude Agent SDK) - see `docs/19`.

**To pause everything:** `/pause` on Telegram, or
`launchctl unload ~/Library/LaunchAgents/com.foundry.daemon.plist` and
`docker compose -f marketing/docker-compose.yml down`.
