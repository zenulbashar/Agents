# The four n8n workflows (+ video branches)

Build in the n8n UI (each 4-7 nodes). No inbound webhooks - schedules/polls only.

**WF1 - Social poster.** Hourly 07:00-21:00 Brisbane -> read `social` where
`status=approved` and `scheduled_at <= now` -> per channel:
- **X:** HTTP POST `https://api.x.com/2/tweets` `{"text": ...}` (OAuth 1.0a). No URL unless `link_post`.
- **IG image:** POST `graph.facebook.com/v23.0/{IG_ID}/media` (image_url, caption) -> `/media_publish`.
- **IG Reel:** create container `media_type=REELS` + `video_url` -> poll container status until
  `FINISHED` -> `media_publish`.
- **TikTok (Phase 1 draft):** `POST /v2/post/publish/inbox/video/init/` with `PULL_FROM_URL`
  from the verified media domain -> poll `status/fetch` -> mark `in_drafts` (you finish in-app).
Write back `status=posted`/`in_drafts`, `posted_at`, `post_id`. On failure: `status=error` + email you (never retry-spam).

**WF2 - Newsletter.** Monday 07:30 -> `newsletter` where `status=approved` -> Brevo create
campaign -> send to `p2e-newsletter` -> mark sent. Footer (hard-coded): legal name + ABN + address + unsubscribe.

**WF3 - Outreach dripper.** Weekdays 09:00 -> `outreach` where `status=approved`, **max 10** ->
send individually via Brevo with the identification footer + unsubscribe -> mark sent.

**WF4 - IG token refresh.** Monthly -> call the refresh endpoint -> email you the new token to
paste into the n8n credential. Also set a calendar reminder - an expired token is the most common silent failure.

Reference `{{ $env.AI_BASE_URL }}` / `{{ $env.AI_MODEL }}` in any HTTP node that calls the model.
