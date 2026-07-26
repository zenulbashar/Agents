# n8n workflows - import and setup

Generated from `marketing/workflows.md` (the spec). Four importable workflows:

| File | What it does | Schedule (Brisbane) |
|---|---|---|
| `wf1-social-poster.json` | IG image, IG Reel, X, TikTok draft | hourly, 07:00-21:00 |
| `wf2-newsletter.json` | Brevo campaign to the list | Monday 07:30 |
| `wf3-outreach-dripper.json` | Max 10 individual emails | weekdays 09:00 |
| `wf4-ig-token-refresh.json` | Refresh IG token, email you | 1st of month 09:00 |

**Nothing posts until you activate a workflow.** They import inactive. Every row must
also be set to `status = approved` by a human in the Sheet first - review mode is
enforced in the code, not just by convention.

---

## Order of operations

Do these in order. Each step is testable on its own; do not skip ahead.

### 1. Create the Google Sheet

One spreadsheet named `marketing-queue`, four tabs, with **the exact column names**
from `../sheet-schema.md` in row 1:

- **social** - `id, brand, channel, text, image_url, video_url, scheduled_at, status, posted_at, post_id`
- **newsletter** - `id, subject, html_body, send_after, status, sent_at`
- **outreach** - `id, venue, contact_name, role, email, source_url, why_relevant, subject, body, status, sent_at`
- **config** - `key, value`

In the `config` tab add these rows:

| key | value |
|---|---|
| `ig_user_id` | your Instagram Business Account ID (step 2) |
| `x_paused` | `true` |
| `tiktok_paused` | `true` |
| `ig_paused` | `false` |

Starting X paused matters: X bills **$0.015 per post and $0.20 if it contains a URL**.
Leave it paused until you have deliberately decided to spend.

WF1 also refuses to post an X row containing a URL unless that row sets `link_post = true`,
so an accidental link cannot cost you 13x.

### 2. Instagram prerequisites (the long pole)

This is the part that takes real time. In order:

1. **Instagram account -> Professional** (Business or Creator) in the IG app.
2. **Link it to a Facebook Page.** Publishing via the API requires the Page link; a
   standalone IG account cannot publish through Graph.
3. **Meta Developer account** at developers.facebook.com, then **create an App**
   (Business type).
4. Add the **Instagram** product to the app.
5. Request permissions: `instagram_basic`, `instagram_content_publish`,
   `pages_show_list`, `pages_read_engagement`, `business_management`.
6. **Generate a long-lived access token** (~60 days). A short-lived token from the
   Graph API Explorer must be exchanged for a long-lived one.
7. **Get your Instagram Business Account ID** - that is the `ig_user_id` value for the
   config tab, not your @handle.
8. **Public image hosting.** Instagram fetches the media itself, so `image_url` must be
   a publicly reachable **JPEG** over HTTPS - not PNG, not WebP, not a signed or expiring
   URL. `../video-pipeline.md` uses Cloudflare R2 on `media.prompt2eat.com`; the same
   bucket serves images.

Limits that will bite: **<=100 API posts per 24h**, Reels must be MP4 (1080x1920 per the
video pipeline), and **the token expires every 60 days** - which is what WF4 exists for.

Meta reorganises this console frequently and permission names change between API
versions. Treat the list above as the shape of the task, and follow whatever the current
console tells you. The workflows target Graph **v23.0**; if that version is retired,
update the URLs in WF1 and WF4.

### 3. Create the n8n credentials

In n8n (http://127.0.0.1:5678) -> **Credentials -> New**. Create these with **exactly
these names**, so the imported workflows bind to them automatically:

| Credential name | Type | Needed by |
|---|---|---|
| `Google Sheets - marketing-queue` | Google Sheets OAuth2 API | all four |
| `Meta Graph - prompt2eat` | Facebook Graph API | WF1, WF4 |
| `Brevo - prompt2eat` | Brevo (SendinBlue) API | WF2, WF3, WF4 |
| `X - prompt2eat` | Twitter OAuth1 API | WF1 |
| `TikTok - Authorization Bearer` | Header Auth | WF1 |

Share the Sheet with the Google account behind the Sheets credential, or every read
returns empty with no obvious error.

Credentials are encrypted with `N8N_ENCRYPTION_KEY` from `marketing/.env`. If you lose
that key, every credential here becomes unrecoverable and must be re-entered.

### 4. Import and fill placeholders

n8n -> **Workflows -> Import from File**, one at a time.

Then search each workflow for `REPLACE_` and fill it in. Every placeholder:

| Placeholder | Where | What |
|---|---|---|
| `REPLACE_WITH_SPREADSHEET_ID` | WF1-3 | Sheet ID from its URL (`/d/<THIS>/edit`) |
| `REPLACE_WITH_CREDENTIAL_ID` | all | auto-resolves when you pick the credential in the node |
| `REPLACE_LEGAL_NAME` | WF2, WF3 | registered legal name - Spam Act requirement |
| `REPLACE_ABN` | WF2, WF3 | your ABN - Spam Act requirement |
| `REPLACE_POSTAL_ADDRESS` | WF2, WF3 | postal address - Spam Act requirement |
| `REPLACE_SENDER_NAME` / `REPLACE_SENDER_EMAIL` | WF2-4 | verified Brevo sender |
| `REPLACE_BREVO_LIST_ID` | WF2 | numeric list ID of `p2e-newsletter` |
| `REPLACE_UNSUB_EMAIL` | WF3 | inbox that receives unsubscribe requests |
| `REPLACE_OPERATOR_EMAIL` | WF4 | where token warnings go - an inbox you actually read |
| `REPLACE_WITH_CURRENT_LONG_LIVED_TOKEN` | WF4 | current IG long-lived token |

The three Spam Act fields are not optional. Australian commercial email requires accurate
sender identification and a functional unsubscribe honoured within 5 business days;
ACMA enforces it, and the penalties are real.

### 5. First safe test

Do this before activating anything:

1. Put **one** row in the `social` tab: `channel = ig`, a real public JPEG `image_url`,
   short `text`, blank `scheduled_at`, `status = approved`.
2. Open WF1 and click **Execute Workflow** manually. Do not activate it yet.
3. Watch the node-by-node output. If it succeeds, the post is live on Instagram and the
   Sheet row flips to `posted` with a `post_id`.
4. Only once a manual run works end to end, toggle the workflow **Active**.

If `IG create image container` fails, the cause is almost always one of: image not
publicly reachable, not actually a JPEG, token expired, or `ig_user_id` being the handle
instead of the numeric Business Account ID.

---

## Design notes

- **Agents never touch these workflows or any credential.** They write Sheet rows only.
  That separation is the reason a bad model output cannot post by itself.
- **Errors do not retry.** Any failure writes `status = error` to the row and stops.
  Retry storms against a rate-limited API are worse than a missed post; fix the row and
  set it back to `approved`.
- **TikTok is draft-only.** WF1 pushes to your TikTok inbox and marks the row
  `in_drafts`. You finish the post in the app. Auto-publish needs TikTok's audit.
- **Brevo's free tier is 300 emails/day shared** across newsletter, outreach, and Zale IT.
  WF3's cap of 10/weekday is deliberate; raising it eats the shared quota.
- **WF4 does not update the credential for you.** It refreshes the token and emails it to
  you to paste in. Automating that would mean giving the daemon write access to its own
  credential store, which is exactly the thing you do not want it to have.

## Provenance

Generated 2026-07-26 by Cowork from `marketing/workflows.md`, against n8n 1.x node
schemas (`scheduleTrigger` 1.2, `googleSheets` 4.5, `httpRequest` 4.2, `switch` 3.2,
`if` 2.2, `code` 2, `wait` 1.1, `splitInBatches` 3). All four validated as parseable JSON
with every connection and cross-node expression resolving to a real node, and no
credentials embedded. **They have not been executed** - no account existed to run them
against. Expect to adjust node parameters on first run.
