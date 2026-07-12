# Free branded-video pipeline (TikTok + IG Reels)

The best prompt2eat demo is the product doing its thing - a scripted browser session,
recorded automatically. All free.

```
Playwright  -> records the real concierge flow (mobile viewport) to .webm
FFmpeg      -> normalise to 1080x1920 MP4
Remotion    -> wrap in the BRAND KIT: intro, caption bar, end card (logo + locked pricing + CTA)
Cloudflare R2 -> public bucket (free tier), TikTok-verified domain media.prompt2eat.com
Google Sheet -> rows channel=ig_reel / tiktok, video_url, status=review
n8n WF1      -> IG Reels publish (existing Meta app); TikTok push to drafts (Phase 1)
```

**Brand kit as code = the always-on-brand guarantee.** A `p2e-video/` Remotion project with
`src/brand.ts` as the single source of truth (colours, fonts, end-card pricing transcribed from the
Claude Design export). Every render is `DemoVideo` with different props (`clip`, `headline`). Nobody -
including the AI writing captions - can put the wrong colour, font, or price on screen, because those
are compiled in, not inputs. Caption *text* still obeys `guardrails.md`.

**Licences (verified):** Playwright/FFmpeg free; **Remotion free** incl. commercial use for individuals
and companies **up to 3 people** (sole trader qualifies); R2 free tier; TikTok API free (draft mode).

Rendering lives in the **supervised** session (Cowork/agent), not the n8n daemon - every video passes
your eyes (which Phase-1 TikTok requires anyway). Seed a **demo venue** with a real-looking menu so
nothing customer-facing is touched.
