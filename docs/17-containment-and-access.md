# 17 - Containment & access

The operator requirement: agents touch **only what you allow**, never the whole Mac Mini.
Source of truth: `config/access.yaml` (default-deny). Defense in depth:

## Layers

1. **Filesystem jail.** Every agent is confined to `~/foundry` - its department workspace
   (`workspaces/<domain>/`) and the shared `vault/`. `~/.ssh`, `~/.aws`, Keychains,
   `~/Documents`, `~/Desktop`, and the rest of the disk are denied. `.claude/settings.json`
   `permissions.deny` blocks `./.env`, `secrets/**`, `~/.ssh/**`, `~/.aws/**`.
2. **Per-agent tool allowlist.** Each subagent only holds the built-in tools its mission needs
   (generated from `config/agents.yaml`). Domain powers are MCP tools that themselves check authz.
3. **Network egress allowlist.** Default-deny. Each domain lists the hosts it may reach
   (`config/access.yaml`). Local models bind to `127.0.0.1` only (a bright line). The Firewall
   agent enforces this for daemon traffic; the PreToolUse hook ASKs on any non-allowlisted host.
4. **Secrets broker.** API keys live in n8n's encrypted store / macOS Keychain - **never** on
   disk, in Cowork files, or in the vault. Reading/rotating a secret is a bright line.
5. **Sandboxed execution.** Daemon work runs in Docker (CPU/mem/time limited); code execution
   is wrapped in macOS `sandbox-exec` profiles. Ephemeral agents inherit the tightest jail.
6. **Cowork jail.** Cowork runs confined to `~/foundry`, holds **no** credentials, and (in the
   marketing flow) writes only its workspace + the Google Sheet queue.

## Per-domain grants

`platform`, `prompt2eat`, `roster`, `zaleit`, `marketing`, `brain` each get an explicit
`fs_allow` + `egress_allow` + `credentials` set. Anything unlisted is denied. To give an agent
access to something new, add it to that domain in `config/access.yaml` - nothing else changes.

## Honest limit

This is strong defense-in-depth, not a hypervisor boundary. The real guarantees are: least
privilege, default-deny egress (kills most exfiltration), no keys outside the broker, and hard
human gates on anything irreversible. A determined prompt-injection still cannot deploy, spend,
delete, publish, or read a secret without you (bright lines).
