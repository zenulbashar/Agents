# Google Sheet queue - schema

One spreadsheet `marketing-queue`, shared with the Google account n8n's Sheets
credential uses. Every row moves `status = review -> approved -> posted/sent`.

| tab | columns |
|---|---|
| `social` | id, brand, channel (x/ig/ig_reel/tiktok), text, image_url, video_url, scheduled_at, status, posted_at, post_id, link_post |
| `newsletter` | id, subject, html_body, send_after, status, sent_at |
| `outreach` | id, venue, contact_name, role, email, source_url, why_relevant, subject, body, status, sent_at |
| `config` | key, value (e.g. ig_user_id, x_paused=false) |

The `channel` column carries the video extension: `ig_reel` and `tiktok` rows set
`video_url` (see `video-pipeline.md`). Cowork/agents write only this sheet; they hold no keys.

`link_post` (social, added 2026-07-26) is the deliberate-spend flag for X: a post with a URL
costs **$0.20 instead of $0.015**, so WF1 skips any X row whose `text` contains a URL unless
that row sets `link_post = true`. Leave it `false` for everything else.

The `config` tab carries `ig_user_id` (numeric Instagram Business Account ID, not the handle),
`brevo_list_id`, and per-channel kill switches `ig_paused` / `x_paused` / `tiktok_paused`.
`x_paused` ships as `true` so nothing bills until you decide otherwise.

A ready-to-upload template with these tabs, headers, validation, and one example row per tab
lives at `marketing/marketing-queue.xlsx`.
