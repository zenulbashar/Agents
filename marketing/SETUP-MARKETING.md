# Marketing setup - the operator's runbook

Everything here is yours to do: it is all credentials, spend, or publishing. Follow it in
order. Each step is verifiable before you move on.

**The safety property, stated once:** agents write rows to a Google Sheet and hold no API
keys. n8n holds every key and only ever acts on rows a human set to `status = approved`.
Nothing can post because a model decided to.

---

## Step 1 - Create the Sheet (10 minutes)

`marketing/marketing-queue.xlsx` is a ready-made template: five tabs, exact headers,
dropdown validation, and one example row per tab.

1. Go to **drive.google.com** -> **New -> File upload** -> pick `marketing-queue.xlsx`.
2. In Drive, **right-click the uploaded file -> Open with -> Google Sheets**.
3. **File -> Save as Google Sheets.** This matters: n8n's Sheets node cannot read an
   `.xlsx` sitting in Drive, only a real Google Sheet.
4. Delete the leftover `.xlsx` copy in Drive to avoid picking the wrong one later.
5. Rename the sheet to **`marketing-queue`**.
6. Copy the **spreadsheet ID** from the URL - the long string between `/d/` and `/edit`.
   You need it in Step 4.

Read the `_README` tab first. It states who writes what, which is the thing people get
wrong. Then fill the two yellow cells on the `config` tab:

- `ig_user_id` - your numeric Instagram **Business Account ID** (Step 2), not your @handle
- `brevo_list_id` - numeric ID of your Brevo list (Step 3), only needed for the newsletter

Leave `x_paused = true`. X bills **$0.015 per post, $0.20 if it contains a URL**. Nothing
should reach X until you have deliberately chosen to spend.

The example rows are grey italic and set to `status = review`, so they cannot send. Edit or
delete them once you understand the format.

---

## Step 2 - Instagram access (the long pole - allow a couple of hours)

In this order, because each step depends on the one before:

1. **Instagram app -> Settings -> Account type -> switch to Professional** (Business or Creator).
2. **Link it to a Facebook Page.** Publishing through the API requires the Page link. A
   standalone Instagram account cannot publish, no matter what permissions you hold.
3. **developers.facebook.com -> My Apps -> Create App** (Business type).
4. **Add the Instagram product** to that app.
5. Request these permissions: `instagram_basic`, `instagram_content_publish`,
   `pages_show_list`, `pages_read_engagement`, `business_management`.
6. **Get a long-lived access token (~60 days).** A short-lived token from the Graph API
   Explorer must be exchanged for a long-lived one - the short one expires in about an hour
   and will look like a mysterious failure tomorrow.
7. **Find your Instagram Business Account ID** (numeric). That is `ig_user_id`.

**Verify before moving on.** Paste this into the Graph API Explorer - it should return your
account, not an error:

```
GET /v23.0/<IG_USER_ID>?fields=username,followers_count
```

**Public image hosting.** Instagram fetches the media itself, so `image_url` must be a
publicly reachable **JPEG** over HTTPS. Not PNG, not WebP, not a Google Drive link, not a
signed or expiring URL. `video-pipeline.md` sets up Cloudflare R2 on
`media.prompt2eat.com`; the same bucket serves images.

Limits: **<=100 API posts per 24h**, Reels must be MP4 (1080x1920), and **the token expires
every 60 days** - which is what WF4 exists to warn you about.

Meta renames things between API versions. Treat the above as the shape of the task and
follow the current console. The workflows target Graph **v23.0**.

---

## Step 3 - Brevo (only for newsletter/outreach; skip if starting with Instagram)

1. Create a Brevo account; **verify a sender domain and set up DKIM** or everything lands
   in spam.
2. Create the list `p2e-newsletter`; note its **numeric list ID** -> `brevo_list_id`.
3. Generate an **API key** (Account -> SMTP & API).

Free tier is **300 emails/day shared** across newsletter, outreach, and Zale IT. No rollover.

**Australian law applies:** the Spam Act 2003 (ACMA), not CAN-SPAM or GDPR. Every commercial
email needs consent, accurate sender identification (legal name + ABN + postal address), and
a functional unsubscribe honoured within 5 business days. The placeholders in WF2 and WF3 are
there because of this - they are not optional.

---

## Step 4 - Wire up n8n

Open **http://127.0.0.1:5678**.

**a. Create credentials** (Credentials -> New) with **exactly these names**, so the imported
workflows bind automatically:

| Name | Type |
|---|---|
| `Google Sheets - marketing-queue` | Google Sheets OAuth2 API |
| `Meta Graph - prompt2eat` | Facebook Graph API |
| `Brevo - prompt2eat` | Brevo (SendinBlue) API |
| `X - prompt2eat` | Twitter OAuth1 API |
| `TikTok - Authorization Bearer` | Header Auth |

Create only the ones you need now. Instagram-first means Google Sheets + Meta Graph.

**Share the Sheet with the Google account behind the Sheets credential**, or every read
returns empty rows with no error message.

**b. Import the workflows.** Workflows -> Import from File, one at a time, from
`marketing/workflows/`. Start with `wf1-social-poster.json`.

**c. Fill the placeholders.** Search each workflow for `REPLACE_`. The full table is in
`marketing/workflows/README.md`. For WF1 you need only the spreadsheet ID and to pick your
credentials from the dropdowns.

---

## Step 5 - First post (do not skip the manual run)

1. In the `social` tab, put **one** row: `channel = ig`, a real public JPEG in `image_url`,
   short `text`, `scheduled_at` blank, `link_post = false`, and **`status = approved`**.
2. Open WF1 in n8n and click **Execute Workflow** manually. **Do not activate it yet.**
3. Watch the nodes light up one by one. On success the post is live and the row flips to
   `posted` with a `post_id`.
4. Only after a clean manual run, toggle the workflow **Active**. From then on it runs
   hourly, 07:00-21:00 Brisbane.

**When `IG create image container` fails**, it is nearly always one of:

| Symptom | Cause |
|---|---|
| `Invalid parameter` on image_url | Not publicly reachable, or not a real JPEG |
| `(#190)` / OAuth error | Token expired, or still the short-lived one |
| Empty rows read from Sheet | Sheet not shared with the credential's Google account |
| Nothing selected to post | `status` is not exactly `approved`, or `scheduled_at` is future |
| `(#100)` on the publish call | `ig_user_id` is the @handle, not the numeric ID |

---

## Step 6 - Then, and only then, add channels

Add one at a time, repeating Step 5's manual run for each:

- **Instagram Reels** - needs the video pipeline first (`video-pipeline.md`).
- **TikTok** - draft-only. WF1 pushes to your inbox and marks the row `in_drafts`; you finish
  in the app. Auto-publish requires TikTok's audit.
- **X** - set `x_paused = false` in the config tab. **This starts costing money.**
- **Newsletter / outreach** - needs Step 3, and the Spam Act placeholders filled in.

---

## What still has no owner

- **Nothing generates content into the Sheet yet.** The marketing-director agent is
  scheduled for Monday 06:00 (`config/schedule.yaml`), but writing Sheet rows from the agent
  side is not built - the sheet-writing tool does not exist. Today you write rows by hand.
- **Guardrails are not enforced in code.** `content/guardrails.md` is meant to go verbatim
  into every generation prompt. Until the agent-side writer exists, that is a convention,
  not a mechanism.
