# Google Sheet queue - schema

One spreadsheet `marketing-queue`, shared with the Google account n8n's Sheets
credential uses. Every row moves `status = review -> approved -> posted/sent`.

| tab | columns |
|---|---|
| `social` | id, brand, channel (x/ig/ig_reel/tiktok), text, image_url, video_url, scheduled_at, status, posted_at, post_id |
| `newsletter` | id, subject, html_body, send_after, status, sent_at |
| `outreach` | id, venue, contact_name, role, email, source_url, why_relevant, subject, body, status, sent_at |
| `config` | key, value (e.g. ig_user_id, x_paused=false) |

The `channel` column carries the video extension: `ig_reel` and `tiktok` rows set
`video_url` (see `video-pipeline.md`). Cowork/agents write only this sheet; they hold no keys.
