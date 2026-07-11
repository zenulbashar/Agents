# Zale IT

#business/zaleit

The parent business. Already runs a Brevo weekly email and Cloudflare / Restic / R2 infra.

- **Shared Brevo 300/day cap** if the same account - never schedule everything Monday.
- **Separate DKIM/SPF** for the prompt2eat sending domain so outreach cannot damage
  `mail.zaleit.com.au` reputation.
- Every commercial email carries legal name + ABN + postal address + unsubscribe
  (Spam Act 2003). See `marketing/content/outreach-rules.md`.

Related: [[prompt2eat]], [[roster]].
