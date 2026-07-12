# Marketing subsystem (prompt2eat + Roster + Zale IT)

Productionised from your **verified July-2026 brief**. This is the review-mode
marketing machine the marketing agents operate: Cowork/agents generate content into a
Google Sheet review queue; you approve; **n8n** (the 24/7 daemon) posts/sends. Nothing
unreviewed reaches a brand account.

## Verified facts this subsystem respects (do not regress)

| Claim | Verified fact |
|---|---|
| X API | Free tier discontinued for new devs **6 Feb 2026**. Pay-per-use **$0.015/post**, **$0.20 if it has a URL**. Check for a grandfathered pre-Feb-2026 account. |
| Instagram | Professional account; **60-day** long-lived token (WF4 refreshes); JPEG at a **public URL**; <=100 API posts/24h. |
| TikTok | Content Posting API is free; **unaudited clients are draft-only (Phase 1)** - finish in-app. Public auto-post needs TikTok's audit (Phase 2). |
| Brevo | Free **300 emails/day shared** across marketing + transactional; no rollover. |
| Email law | Australia: **Spam Act 2003 (ACMA)**, not CAN-SPAM/GDPR. Consent, ABN sender ID, functional unsubscribe in 5 business days. |
| AI | OpenAI-compatible base URL: **Ollama** local (free) today; OpenRouter/Anthropic by config change. |
| Cost | ~**$0/month except X** (~under $3/mo). |

## Architecture

- **Cowork/agents** (supervised) generate content + research prospects -> write ONLY the
  Google Sheet queue. Hold **no** API keys.
- **Google Sheet `marketing-queue`** (cloud) - tabs: social | newsletter | outreach | config.
  Every row: `status = review -> approved -> posted/sent`.
- **n8n in Docker** (`marketing/docker-compose.yml`) - the 24/7 poster. WF1 social, WF2
  newsletter, WF3 outreach dripper, WF4 IG token refresh. All keys live in n8n's
  encrypted credential store. No inbound webhooks (polls/schedules only) -> trivially portable.

## Files

- `docker-compose.yml`, `.env.example` - the portable n8n stack.
- `content/brand-voice.md`, `content-pillars.md`, `guardrails.md`, `outreach-rules.md`,
  `approved-proof.md` - what the machine may say (guardrails go verbatim into every prompt).
- `sheet-schema.md`, `workflows.md`, `video-pipeline.md` - the queue, the four workflows,
  and the free branded-video pipeline (Playwright + FFmpeg + Remotion + R2).
- `cowork-playbooks.md` - the paste-ready weekly playbook.

**Brand scope:** prompt2eat first; Roster piggybacks (one newsletter section) until Wave 3
pricing is validated; Zale IT shares the Brevo cap (separate DKIM). See `config/businesses.yaml`.

**Start in review mode; earn full-auto.** An 8B local model will occasionally write a dud;
your 10-minute Monday approval is the safety net.
