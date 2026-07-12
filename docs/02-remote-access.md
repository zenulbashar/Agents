# 02 — Remote Access

> **Goal:** reach the Foundry control plane and agents securely from iPhone, iPad,
> Windows PC, MacBook, and a web browser — without ever exposing the Mac Mini to
> the public internet.

---

## 1. The threat we're designing against

The Mac Mini holds your code, your secrets, your customer data, and agents that
can *execute code and spend money*. If a remote-access path is compromised, the
blast radius is the whole company. So the bar is high:

- **No open inbound ports** on the home/office router. Port-forwarding a service
  to the internet is the thing we are explicitly avoiding.
- **Identity-based access** — every connection tied to an authenticated user/device,
  not just "knows the URL/IP".
- **Least privilege** — a phone that only needs the dashboard shouldn't be able to
  reach Postgres.
- **Defence in depth** — network layer *and* application layer auth.

---

## 2. The options, compared

| Option | What it is | Inbound ports? | Identity / ACLs | Client effort | Best for |
|---|---|---|---|---|---|
| **Tailscale** | Managed WireGuard **mesh** with SSO, MagicDNS, ACLs | **None** (NAT traversal) | **Strong** — per-user/device ACLs, SSO, device posture | Install app, log in | **Operator access to the control plane** |
| **Raw WireGuard** | The underlying VPN protocol, self-managed | 1 UDP port (or via relay) | DIY — manual keys, no built-in identity | Manual key exchange per device | Purists who want zero third parties |
| **Cloudflare Tunnel** | Outbound-only tunnel to Cloudflare edge; optional **Access** (Zero Trust) in front | **None** (outbound only) | **Strong** *with Access* — SSO, policies, MFA | Nothing (it's a URL) | **Intentionally-public surfaces** (a customer app, a shared status page) |
| **Traditional VPN** (OpenVPN/IPsec) | Full network VPN to home | Usually 1 port | Moderate; heavier to run | Client config profiles | Legacy/corporate setups |
| **Reverse proxy** (Caddy/Traefik/nginx) | TLS termination + routing | **Yes if internet-facing** | Only what you add (basic-auth/oauth2-proxy) | Browser only | **Internal** routing *behind* Tailscale |

### Why not the others as the primary path
- **Raw WireGuard** gives you Tailscale's transport without its identity layer,
  ACLs, MagicDNS, or key rotation. You'd rebuild all of that by hand. Use it only
  if you refuse any coordination server — and even then, Tailscale can run on your
  own coordination server (**Headscale**) to remove the third party while keeping
  the ergonomics.
- **Traditional VPN** requires an open inbound port and is heavier to administer
  per-device than Tailscale, with weaker per-resource ACLs.
- **A public reverse proxy** (port-forward 443 to Caddy) puts your box directly on
  the internet. Even with TLS + auth, you now own patching an internet-facing
  attack surface. We use a reverse proxy **internally** (for TLS + clean routing),
  never as the front door.

---

## 3. Recommended architecture

**Two layers, each for what it's best at:**

```mermaid
flowchart TB
    subgraph You["Your devices"]
        OP[iPhone · iPad · Windows · MacBook · operator]:::dev
        PUB[Public web browser · a customer / teammate]:::dev
    end

    subgraph TSnet["Tailnet (WireGuard mesh, identity + ACLs)"]
        TSACL{{Tailscale ACLs · user/device to resource}}:::sec
    end

    CFE[[Cloudflare edge · Tunnel + Access (Zero Trust)]]:::sec

    subgraph Mac["Mac Mini — all ports on 127.0.0.1"]
        CADDY[Caddy reverse proxy · TLS + routing, internal only]:::svc
        UI[Control-plane UI / API :8800]:::core
        GRAF[Grafana :3002]:::core
        GIT[Gitea :3000]:::core
        DBS[(Postgres / Qdrant / Redis · NEVER remotely reachable)]:::data
        APP[A shipped customer app · optional, public]:::work
    end

    OP -->|MagicDNS over WireGuard| TSACL --> CADDY
    CADDY --> UI & GRAF & GIT
    TSACL -. denied .-x DBS
    PUB -->|HTTPS| CFE -->|outbound tunnel| APP

    classDef dev fill:#e8f0fe,stroke:#4285f4,color:#111
    classDef sec fill:#fce8e6,stroke:#ea4335,color:#111
    classDef core fill:#e6f4ea,stroke:#34a853,color:#111
    classDef svc fill:#fff,stroke:#333,color:#111
    classDef data fill:#f3e8fd,stroke:#a142f4,color:#111
    classDef work fill:#fef7e0,stroke:#fbbc04,color:#111
```

### Layer 1 — Tailscale for the operator control plane (primary)
- Install Tailscale on the Mac Mini and on each of your devices; they form a private
  encrypted mesh. **No router ports are opened** — Tailscale does NAT traversal.
- Reach services by MagicDNS name over HTTPS, e.g. `https://foundry.<tailnet>.ts.net`.
  Use **Tailscale Serve** + a small **Caddy** reverse proxy on the box to give clean
  hostnames and automatic TLS for each internal service.
- **Tailscale ACLs** enforce least privilege: your phone tag can reach the UI and
  Grafana; only your laptop (admin tag) can reach Gitea; **nothing** on the tailnet
  can reach the database ports.
- Turn on **MFA**, **device authorization** (you approve each new device), and
  consider **tailnet lock** so a compromised coordination server can't add nodes.
- **Privacy option:** run **Headscale** (self-hosted control server) to keep even
  the coordination metadata on your own infrastructure.

### Layer 2 — Cloudflare Tunnel + Access for anything intentionally public
- When the company *ships a product* that real users hit (or you want a public
  status page), run `cloudflared` to open an **outbound-only** tunnel. Cloudflare
  serves the public hostname; the origin (your app on the mini) is **never directly
  reachable** and has **no inbound ports**.
- Put **Cloudflare Access (Zero Trust)** in front of anything not meant for the
  whole world (e.g., a beta) — SSO + MFA + per-email/group policies at the edge,
  plus WAF and DDoS protection for free.
- This keeps the *operator* plane (Tailscale) and the *public* plane (Cloudflare)
  cleanly separated, with different trust models.

### Always-on application auth (defence in depth)
Network access != app access. Behind both layers, the control-plane UI authenticates
every request via **Authentik (OIDC)** with RBAC ([11](11-security-architecture.md)).
So even *on the tailnet*, a user still logs in and only sees what their role allows.

---

## 4. Per-device setup

| Device | How you connect |
|---|---|
| **iPhone / iPad** | Tailscale app (App Store) -> sign in -> open `https://foundry.<tailnet>.ts.net` in Safari. Add to Home Screen for an app-like PWA. Mobile push for approval gates via the UI's web-push. |
| **MacBook** | Tailscale app -> sign in. Full access (admin tag): UI, Grafana, Gitea, and `ssh` over Tailscale SSH for maintenance. |
| **Windows PC** | Tailscale for Windows -> sign in -> browser to the MagicDNS URL. Same RBAC applies. |
| **Web browser (operator, off-tailnet)** | Prefer joining the tailnet. If you truly can't install Tailscale, expose **only the UI** via Cloudflare Access (SSO+MFA) — never the admin services. |
| **Web browser (a customer)** | Hits the public product via Cloudflare Tunnel; never touches the operator plane. |

---

## 5. Hard rules

1. **Zero inbound ports** on the router. If you ever feel the urge to port-forward,
   use Tailscale or a Cloudflare Tunnel instead.
2. **Databases and secrets are never on the tailnet ACL** for client devices —
   only the orchestrator (local) talks to them.
3. **Two auth layers**: network (Tailscale/Cloudflare) **and** application (OIDC/RBAC).
4. **MFA everywhere**, device authorization on, keys rotated, ephemeral keys for
   any short-lived access.
5. **Public != operator.** Customer-facing surfaces go through Cloudflare with their
   own trust model and never share a path with the control plane.

---

## 6. TL;DR

> **Use Tailscale as the front door for you, the operator** (WireGuard security,
> zero open ports, identity ACLs, trivial on every device). **Use Cloudflare
> Tunnel + Access only for things you intentionally publish.** Use a reverse proxy
> (Caddy) **internally** for TLS/routing, never as an internet-facing entry point.
> Raw WireGuard and traditional VPNs are strictly worse versions of layer 1;
> a public reverse proxy is the thing we're avoiding.
