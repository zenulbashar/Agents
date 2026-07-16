"""Foundry Support API — multi-app AI support chat (Contract v1).

FastAPI service exposing POST /v1/chat (SSE, AI SDK UI Message Stream v1),
GET /v1/conversations/{id}, POST /v1/feedback, plus escalation -> tickets ->
Telegram + outbound signed webhooks. Foundry is the system of record for
conversations, with hard app_id + tenant_id isolation (Postgres RLS).
"""
